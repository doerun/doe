"""Runner helpers for compare_dawn_vs_doe."""

import json
import subprocess
import time
import resource as py_resource
import tempfile
import shlex
import shutil
from pathlib import Path
from typing import Any

from compare_dawn_vs_doe_modules.timing_selection import (
    pick_measured_timing_ms,
    maybe_adjust_timing_for_ignored_first_ops,
)

MAX_RSS_MARKER = "__DOE_MAXRSS_KB__:"

def file_sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(value: Any) -> str:
    import hashlib
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def collect_trace_meta_hashes(command_samples: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_path: dict[str, str] = {}
    for sample in command_samples:
        if not isinstance(sample, dict):
            continue
        raw_path = sample.get("traceMetaPath")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        path = raw_path.strip()
        if path in by_path:
            continue
        trace_meta_path = Path(path)
        if not trace_meta_path.exists():
            continue
        by_path[path] = file_sha256(trace_meta_path)
    return [{"path": path, "sha256": by_path[path]} for path in sorted(by_path.keys())]

def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            try:
                return int(text)
            except ValueError:
                return None
    return None

def dawn_metric_median_ms(trace_meta: dict[str, Any], metric_name: str) -> float | None:
    medians = trace_meta.get("dawnMetricMediansMs")
    if not isinstance(medians, dict):
        return None
    value = safe_float(medians.get(metric_name))
    if value is None or value < 0.0:
        return None
    return value

def extract_timing_metrics_ms(
    trace_meta: dict[str, Any],
    *,
    wall_ms: float,
    cpu_ms: float,
) -> dict[str, float | None]:
    dawn_wall_ms = dawn_metric_median_ms(trace_meta, "wall_time")
    dawn_cpu_ms = dawn_metric_median_ms(trace_meta, "cpu_time")
    dawn_gpu_ms = dawn_metric_median_ms(trace_meta, "gpu_time")

    fawn_gpu_total_ns = int(trace_meta.get("executionGpuTimestampTotalNs") or 0)
    fawn_gpu_ms = (
        float(fawn_gpu_total_ns) / 1_000_000.0
        if fawn_gpu_total_ns > 0
        else None
    )

    return {
        "wall_time": dawn_wall_ms if dawn_wall_ms is not None else wall_ms,
        "cpu_time": dawn_cpu_ms if dawn_cpu_ms is not None else cpu_ms,
        "gpu_time": dawn_gpu_ms if dawn_gpu_ms is not None else fawn_gpu_ms,
    }

def normalize_timing_metrics_ms(
    metrics_ms: dict[str, float | None],
    divisor: float,
) -> dict[str, float | None]:
    normalized: dict[str, float | None] = {}
    for key, value in metrics_ms.items():
        if value is None:
            normalized[key] = None
            continue
        normalized[key] = value / divisor if divisor > 0.0 else value
    return normalized

def read_process_rss_kb(pid: int) -> int:
    status_path = Path("/proc") / str(pid) / "status"
    try:
        lines = status_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        if not line.startswith("VmRSS:"):
            continue
        parts = line.split()
        if len(parts) < 2:
            return 0
        parsed = parse_int(parts[1])
        return parsed if parsed is not None else 0
    return 0

def read_rocm_vram_snapshot() -> tuple[dict[str, int] | None, str | None]:
    cmd = ["rocm-smi", "--showmeminfo", "vram", "--json"]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            timeout=2.0,
        )
    except FileNotFoundError:
        return None, "rocm-smi not found"
    except subprocess.TimeoutExpired:
        return None, "rocm-smi timeout"

    if proc.returncode != 0:
        err = proc.stderr.strip() or f"rocm-smi exited with rc={proc.returncode}"
        return None, err

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, "rocm-smi returned invalid JSON"

    if not isinstance(payload, dict):
        return None, "rocm-smi returned non-object payload"

    used_total = 0
    total_total = 0
    card_count = 0
    for card_payload in payload.values():
        if not isinstance(card_payload, dict):
            continue
        used = parse_int(card_payload.get("VRAM Total Used Memory (B)"))
        total = parse_int(card_payload.get("VRAM Total Memory (B)"))
        if used is None or total is None:
            continue
        used_total += used
        total_total += total
        card_count += 1

    if card_count == 0:
        return None, "rocm-smi payload missing VRAM totals"

    return {
        "usedBytes": used_total,
        "totalBytes": total_total,
        "cardCount": card_count,
    }, None

def assert_json_object(payload: Any, *, context: str, path: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context}: invalid JSON object in {path}")
    return payload

def parse_trace_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return assert_json_object(json.load(f), context="trace-meta", path=path)
    except (json.JSONDecodeError, ValueError):
        return {}

def materialize_repeated_commands(
    commands_path: str,
    *,
    repeat: int,
    out_dir: Path,
    side_name: str,
) -> str:
    if repeat <= 1:
        return commands_path

    source_path = Path(commands_path)
    if not source_path.exists():
        raise ValueError(f"command repeat requested but commands file does not exist: {commands_path}")

    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid commands JSON for repeat expansion ({commands_path}): {exc}") from exc

    if not isinstance(payload, list):
        raise ValueError(f"command repeat requires a JSON array of commands, got {type(payload).__name__} in {commands_path}")

    expanded = payload * repeat
    generated = out_dir / f"{side_name}.commands.repeat{repeat}.json"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(json.dumps(expanded, indent=2) + "\\n", encoding="utf-8")
    return str(generated)

def command_for(
    template: str,
    *,
    workload: Any,
    workload_id: str,
    commands_path: str,
    trace_jsonl: Path,
    trace_meta: Path,
    queue_sync_mode: str,
    upload_buffer_usage: str,
    upload_submit_every: int,
    extra_args: list[str],
) -> list[str]:
    ctx = {
        "commands": shlex.quote(commands_path),
        "quirks": shlex.quote(workload.quirks_path),
        "vendor": shlex.quote(workload.vendor),
        "api": shlex.quote(workload.api),
        "family": shlex.quote(workload.family),
        "driver": shlex.quote(workload.driver),
        "workload": shlex.quote(workload_id),
        "dawn_filter": shlex.quote(workload.dawn_filter),
        "trace_jsonl": shlex.quote(str(trace_jsonl)),
        "trace_meta": shlex.quote(str(trace_meta)),
        "queue_sync_mode": shlex.quote(queue_sync_mode),
        "upload_buffer_usage": shlex.quote(upload_buffer_usage),
        "upload_submit_every": shlex.quote(str(upload_submit_every)),
        "extra_args": shlex.join(extra_args),
    }
    resolved = template.format(**ctx)
    return shlex.split(resolved)

def max_rss_time_prefix() -> tuple[str, ...]:
    gtime_bin = shutil.which("gtime")
    if gtime_bin:
        return (gtime_bin, "-f", f"{MAX_RSS_MARKER}%M")

    time_bin = Path("/usr/bin/time")
    if not time_bin.exists():
        return ()

    probe = [str(time_bin), "-f", "%M", "/usr/bin/true"]
    try:
        result = subprocess.run(
            probe,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return ()

    if result.returncode != 0:
        return ()
    return (str(time_bin), "-f", f"{MAX_RSS_MARKER}%M")

time_prefix_cache = max_rss_time_prefix()

def run_once(
    command: list[str],
    *,
    gpu_memory_probe: str,
    resource_sample_ms: int,
    resource_sample_target_count: int,
) -> tuple[float, float, int, dict[str, Any]]:
    time_prefix = time_prefix_cache
    wrapped_command = [*time_prefix, *command] if time_prefix else command

    cpu_usage_before = py_resource.getrusage(py_resource.RUSAGE_CHILDREN)
    start = time.perf_counter()
    with tempfile.TemporaryFile(mode="w+b") as stdout_capture, tempfile.TemporaryFile(
        mode="w+b"
    ) as stderr_capture:
        popen = subprocess.Popen(
            wrapped_command,
            stdout=stdout_capture,
            stderr=stderr_capture,
        )

        sample_interval_s = max(resource_sample_ms, 1) / 1000.0
        process_peak_rss_kb = 0
        sample_count = 0
        sampling_truncated = False

        gpu_probe_error: str | None = None
        gpu_before: dict[str, int] | None = None
        gpu_peak: dict[str, int] | None = None

        if gpu_memory_probe == "rocm-smi":
            gpu_before, gpu_probe_error = read_rocm_vram_snapshot()
            if gpu_before is not None:
                gpu_peak = dict(gpu_before)

        while True:
            process_running = popen.poll() is None
            if process_running:
                process_peak_rss_kb = max(process_peak_rss_kb, read_process_rss_kb(popen.pid))
            sample_count += 1

            if gpu_memory_probe == "rocm-smi":
                snapshot, err = read_rocm_vram_snapshot()
                if snapshot is not None:
                    if gpu_peak is None:
                        gpu_peak = dict(snapshot)
                    elif snapshot.get("usedBytes", 0) > gpu_peak.get("usedBytes", 0):
                        gpu_peak = dict(snapshot)
                elif gpu_probe_error is None and err:
                    gpu_probe_error = err

            if resource_sample_target_count > 0 and sample_count >= resource_sample_target_count:
                if process_running:
                    sampling_truncated = True
                    popen.wait()
                break

            if resource_sample_target_count <= 0 and not process_running:
                break

            if resource_sample_target_count > 0:
                time.sleep(sample_interval_s)
                continue

            try:
                popen.wait(timeout=sample_interval_s)
            except subprocess.TimeoutExpired:
                pass

        popen.wait()
        stdout_capture.seek(0)
        stderr_capture.seek(0)
        stdout = stdout_capture.read().decode("utf-8", errors="replace")
        stderr = stderr_capture.read().decode("utf-8", errors="replace")

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        cpu_usage_after = py_resource.getrusage(py_resource.RUSAGE_CHILDREN)
        process_cpu_ms = max(
            0.0,
            (
                (cpu_usage_after.ru_utime + cpu_usage_after.ru_stime)
                - (cpu_usage_before.ru_utime + cpu_usage_before.ru_stime)
            )
            * 1000.0,
        )

        stderr_lines: list[str] = []
        stderr_text = stderr if isinstance(stderr, str) else ""
        for raw_line in stderr_text.splitlines():
            line = raw_line.strip()
            if line.startswith(MAX_RSS_MARKER):
                parsed_rss = parse_int(line[len(MAX_RSS_MARKER):].strip())
                if parsed_rss is not None:
                    process_peak_rss_kb = max(process_peak_rss_kb, parsed_rss)
                continue
            stderr_lines.append(raw_line)
        sanitized_stderr = "\\n".join(stderr_lines).strip()

        gpu_after: dict[str, int] | None = None
        if gpu_memory_probe == "rocm-smi":
            gpu_after, err = read_rocm_vram_snapshot()
            if gpu_after is not None:
                if gpu_peak is None or gpu_after.get("usedBytes", 0) > gpu_peak.get("usedBytes", 0):
                    gpu_peak = dict(gpu_after)
            elif gpu_probe_error is None and err:
                gpu_probe_error = err

        resource: dict[str, Any] = {
            "resourceSampleMs": max(resource_sample_ms, 1),
            "resourceSampleCount": sample_count,
            "resourceSampleTargetCount": max(resource_sample_target_count, 0),
            "resourceSamplingTruncated": sampling_truncated,
            "processWallMs": elapsed_ms,
            "processCpuMs": process_cpu_ms,
            "processPeakRssKb": process_peak_rss_kb,
            "gpuMemoryProbe": gpu_memory_probe,
            "gpuMemoryProbeAvailable": False,
        }

        if gpu_memory_probe == "rocm-smi":
            resource["gpuMemoryProbeError"] = gpu_probe_error or ""
            if gpu_before is not None:
                resource["gpuVramUsedBeforeBytes"] = gpu_before.get("usedBytes", 0)
                resource["gpuVramTotalBytes"] = gpu_before.get("totalBytes", 0)
                resource["gpuVramCardCount"] = gpu_before.get("cardCount", 0)
            if gpu_after is not None:
                resource["gpuVramUsedAfterBytes"] = gpu_after.get("usedBytes", 0)
                if "gpuVramTotalBytes" not in resource:
                    resource["gpuVramTotalBytes"] = gpu_after.get("totalBytes", 0)
                    resource["gpuVramCardCount"] = gpu_after.get("cardCount", 0)
            if gpu_peak is not None:
                resource["gpuVramUsedPeakBytes"] = gpu_peak.get("usedBytes", 0)
            if gpu_before is not None and gpu_peak is not None:
                resource["gpuVramDeltaPeakFromBeforeBytes"] = max(
                    0,
                    gpu_peak.get("usedBytes", 0) - gpu_before.get("usedBytes", 0),
                )
                resource["gpuMemoryProbeAvailable"] = True

        if popen.returncode != 0:
            stdout_text = stdout.strip() if isinstance(stdout, str) else ""
            raise RuntimeError(
                f"command failed (rc={popen.returncode}): {' '.join(command)}\\n"
                f"stdout={stdout_text}\\nstderr={sanitized_stderr}"
            )

        return elapsed_ms, process_cpu_ms, popen.returncode, resource

from compare_dawn_vs_doe_modules import reporting as reporting_mod

def run_workload(
    name: str,
    template: str,
    workload: Any,
    iterations: int,
    warmup: int,
    out_dir: Path,
    gpu_memory_probe: str,
    resource_sample_ms: int,
    resource_sample_target_count: int,
    timing_divisor: float,
    command_repeat: int,
    ignore_first_ops: int,
    upload_buffer_usage: str,
    upload_submit_every: int,
    inject_upload_runtime_flags: bool,
    required_timing_class: str,
    benchmark_policy: Any,
    emit_shell: bool,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    commands_path = materialize_repeated_commands(
        workload.commands_path,
        repeat=command_repeat,
        out_dir=out_dir,
        side_name=name,
    )
    timings: list[float] = []
    run_records: list[dict[str, Any]] = []
    sample_meta: dict[str, Any] = {}
    last_meta = {}

    for run_idx in range(max(iterations, 0)):
        trace_jsonl = out_dir / f"{name}.run{run_idx:03d}.ndjson"
        trace_meta = out_dir / f"{name}.run{run_idx:03d}.meta.json"
        effective_extra_args = list(workload.extra_args)
        if inject_upload_runtime_flags and workload.domain == "upload" and "doe-zig-runtime" in template:
            effective_extra_args.extend(
                [
                    "--upload-buffer-usage",
                    upload_buffer_usage,
                    "--upload-submit-every",
                    str(upload_submit_every),
                ]
            )
        queue_sync_mode = "per-command"
        for i, arg in enumerate(workload.extra_args):
            if arg == "--queue-sync-mode" and i + 1 < len(workload.extra_args):
                queue_sync_mode = workload.extra_args[i + 1]

        command = command_for(
            template,
            workload=workload,
            workload_id=workload.id,
            commands_path=commands_path,
            trace_jsonl=trace_jsonl,
            trace_meta=trace_meta,
            queue_sync_mode=queue_sync_mode,
            upload_buffer_usage=upload_buffer_usage,
            upload_submit_every=upload_submit_every,
            extra_args=effective_extra_args,
        )
        if emit_shell:
            run_records.append(
                {
                    "runIndex": run_idx,
                    "command": " ".join(command),
                    "commandRepeat": command_repeat,
                    "uploadIgnoreFirstOps": ignore_first_ops,
                    "uploadBufferUsage": upload_buffer_usage,
                    "uploadSubmitEvery": upload_submit_every,
                    "timingNormalizationDivisor": timing_divisor,
                }
            )
            continue

        if run_idx < warmup:
            run_once(
                command,
                gpu_memory_probe=gpu_memory_probe,
                resource_sample_ms=resource_sample_ms,
                resource_sample_target_count=resource_sample_target_count,
            )
            continue

        elapsed_ms, process_cpu_ms, rc, resource = run_once(
            command,
            gpu_memory_probe=gpu_memory_probe,
            resource_sample_ms=resource_sample_ms,
            resource_sample_target_count=resource_sample_target_count,
        )
        sample_meta = parse_trace_meta(trace_meta)

        trace_meta_patched = False
        if "doe-zig-runtime" in template:
            if "queueSyncMode" not in sample_meta:
                sample_meta["queueSyncMode"] = queue_sync_mode
                trace_meta_patched = True
            if "uploadBufferUsage" not in sample_meta:
                sample_meta["uploadBufferUsage"] = upload_buffer_usage
                trace_meta_patched = True
            if "uploadSubmitEvery" not in sample_meta:
                sample_meta["uploadSubmitEvery"] = upload_submit_every
                trace_meta_patched = True
        if trace_meta_patched:
            trace_meta.write_text(
                json.dumps(sample_meta, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )

        # Note: maybe_override_render_encode_timing must be implemented/imported in the final logic
        measured_ms, measured_source, measured_meta = pick_measured_timing_ms(
            wall_ms=elapsed_ms,
            trace_meta=sample_meta,
            trace_jsonl=trace_jsonl,
            required_timing_class=required_timing_class,
            benchmark_policy=benchmark_policy,
            workload_domain=workload.domain,
        )
        ignore_meta: dict[str, Any] = {}
        if required_timing_class != "process-wall" and ignore_first_ops > 0:
            measured_ms, measured_source, ignore_meta = maybe_adjust_timing_for_ignored_first_ops(
                measured_ms=measured_ms,
                measured_source=measured_source,
                trace_jsonl=trace_jsonl,
                ignore_first_ops=ignore_first_ops,
            )
        measured_raw_ms = measured_ms
        effective_timing_divisor = timing_divisor
        if required_timing_class == "process-wall":
            effective_timing_divisor = 1.0
            
        trace_row_count = parse_int(sample_meta.get("executionRowCount", 0)) or 0
        trace_dispatch_count = parse_int(sample_meta.get("executionDispatchCount", 0)) or 0
        trace_success_count = parse_int(sample_meta.get("executionSuccessCount", 0)) or 0
        trace_submit_every = parse_int(sample_meta.get("uploadSubmitEvery", 0)) or 0
        derived_divisor = 0.0
        
        if workload.domain == "upload" and trace_submit_every > 0:
            derived_divisor = float(trace_row_count)
        elif trace_dispatch_count > 0:
            derived_divisor = float(trace_dispatch_count)
        elif trace_success_count > 0 or trace_row_count > 0:
            derived_divisor = float(max(trace_success_count, trace_row_count))
        
        if required_timing_class != "process-wall" and derived_divisor > 1.0 and effective_timing_divisor != derived_divisor and workload.comparable:
            raise ValueError(
                f"strict counter-derived normalization failed for {workload.id} (run {run_idx}): "
                f"workload contract specifies divisor {effective_timing_divisor}, but trace meta "
                f"reveals {derived_divisor} physical operations "
                f"(success={trace_success_count}, rows={trace_row_count}, dispatches={trace_dispatch_count})."
            )

        measured_ms = measured_raw_ms / effective_timing_divisor
        timing_metrics_raw_ms = extract_timing_metrics_ms(
            sample_meta,
            wall_ms=elapsed_ms,
            cpu_ms=process_cpu_ms,
        )
        timing_metrics_normalized_ms = normalize_timing_metrics_ms(
            timing_metrics_raw_ms,
            effective_timing_divisor,
        )
        measured_meta["timingNormalizationDivisor"] = effective_timing_divisor
        measured_meta["timingConfiguredDivisor"] = timing_divisor
        measured_meta["timingRawMs"] = measured_raw_ms
        measured_meta["timingNormalizedMs"] = measured_ms
        measured_meta["uploadBufferUsage"] = upload_buffer_usage
        measured_meta["uploadSubmitEvery"] = upload_submit_every
        if ignore_meta:
            measured_meta.update(ignore_meta)
        timings.append(measured_ms)
        run_records.append(
            {
                "runIndex": run_idx,
                "command": command,
                "elapsedMs": elapsed_ms,
                "measuredRawMs": measured_raw_ms,
                "measuredMs": measured_ms,
                "timingSource": measured_source,
                "timing": measured_meta,
                "traceJsonlPath": str(trace_jsonl),
                "traceMetaPath": str(trace_meta),
                "returnCode": rc,
                "resource": resource,
                "timingMetricsRawMs": timing_metrics_raw_ms,
                "timingMetricsNormalizedMs": timing_metrics_normalized_ms,
                "traceMeta": sample_meta,
                "commandRepeat": command_repeat,
                "uploadIgnoreFirstOps": ignore_first_ops,
                "uploadBufferUsage": upload_buffer_usage,
                "uploadSubmitEvery": upload_submit_every,
                "timingNormalizationDivisor": timing_divisor,
            }
        )
        last_meta = sample_meta

    if emit_shell:
        return {
            "commandSamples": run_records,
            "stats": reporting_mod.format_stats([]),
            "timingsMs": [],
            "lastMeta": {},
            "resourceStats": reporting_mod.summarize_resource_stats(run_records),
            "timingMetricsRawStatsMs": reporting_mod.summarize_timing_metric_stats(run_records, "timingMetricsRawMs"),
            "timingMetricsNormalizedStatsMs": reporting_mod.summarize_timing_metric_stats(run_records, "timingMetricsNormalizedMs"),
        }

    if not timings:
        return {
            "commandSamples": run_records,
            "stats": reporting_mod.format_stats([]),
            "lastMeta": last_meta,
            "resourceStats": reporting_mod.summarize_resource_stats(run_records),
            "timingMetricsRawStatsMs": reporting_mod.summarize_timing_metric_stats(run_records, "timingMetricsRawMs"),
            "timingMetricsNormalizedStatsMs": reporting_mod.summarize_timing_metric_stats(run_records, "timingMetricsNormalizedMs"),
        }

    from compare_dawn_vs_doe_modules import timing_selection as timing_selection_mod
    timing_sources = sorted({str(sample.get("timingSource", "")) for sample in run_records})
    timing_classes = sorted(
        {
            timing_selection_mod.classify_timing_source(str(sample.get("timingSource", "")))
            for sample in run_records
            if isinstance(sample.get("timingSource"), str)
        }
    )
    return {
        "commandSamples": run_records,
        "stats": reporting_mod.format_stats(timings),
        "timingsMs": timings,
        "lastMeta": last_meta,
        "timingSources": timing_sources,
        "timingClasses": timing_classes,
        "resourceStats": reporting_mod.summarize_resource_stats(run_records),
        "timingMetricsRawStatsMs": reporting_mod.summarize_timing_metric_stats(run_records, "timingMetricsRawMs"),
        "timingMetricsNormalizedStatsMs": reporting_mod.summarize_timing_metric_stats(run_records, "timingMetricsNormalizedMs"),
    }
