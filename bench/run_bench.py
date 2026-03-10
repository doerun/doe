#!/usr/bin/env python3
"""Runtime benchmark harness for measured workload execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shlex
import statistics
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import output_paths


DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"
TRACE_SEED = "0x9e3779b97f4a7c15"
KNOWN_GPU_BACKENDS = {"vulkan", "metal", "d3d12", "webgpu"}
GPU_BACKEND_ALIASES = {
    "dx12": "d3d12",
    "direct3d12": "d3d12",
}
HOST_ALLOWED_GPU_BACKENDS = {
    "darwin": {"metal", "webgpu"},
    "linux": {"vulkan", "webgpu"},
    "windows": {"vulkan", "d3d12", "webgpu"},
}


@dataclass
class Workload:
    workload_id: str
    name: str
    description: str
    commands_path: str
    quirks_path: str
    vendor: str
    api: str
    family: str
    driver: str
    extra_args: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench-config", default="config/benchmarks.json")
    parser.add_argument("--workloads", default="bench/workloads.json")
    parser.add_argument("--workload-id", default="compute_kernel_dispatch_100")
    parser.add_argument("--command-template", default=(
        "zig/zig-out/bin/doe-zig-runtime"
        " --commands {commands}"
        " --quirks {quirks}"
        " --vendor {vendor}"
        " --api {api}"
        " --family {family}"
        " --driver {driver}"
        " --trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}"
        " {extra_args}"
    ))
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--out-report", default="bench/out/perf_report.json")
    parser.add_argument("--out-metadata", default="bench/out/run_metadata.json")
    parser.add_argument("--backend", default="vulkan", choices=["vulkan", "metal", "d3d12", "webgpu"])
    parser.add_argument("--gpu", default="unknown")
    parser.add_argument("--driver", default="unknown")
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--timestamp", default="")
    parser.add_argument(
        "--timestamp-output",
        dest="timestamp_output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Append UTC timestamp suffixes to out paths. "
            "Defaults to enabled for non-clobbering artifacts."
        ),
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--out-dir", default="bench/out/run-bench")
    return parser.parse_args()


def load_json(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def stable_run_id(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int((len(sorted_values) - 1) * p)
    return sorted_values[idx]


def format_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0,
            "minMs": 0.0,
            "maxMs": 0.0,
            "p50Ms": 0.0,
            "p95Ms": 0.0,
            "p99Ms": 0.0,
            "meanMs": 0.0,
            "stdevMs": 0.0,
        }

    return {
        "count": len(values),
        "minMs": min(values),
        "maxMs": max(values),
        "p50Ms": percentile(values, 0.5),
        "p95Ms": percentile(values, 0.95),
        "p99Ms": percentile(values, 0.99),
        "meanMs": statistics.fmean(values),
        "stdevMs": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


def parse_trace_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"WARN: invalid trace jsonl row in {path}: {exc}")
            return []

        if not isinstance(payload, dict):
            print(f"WARN: non-object trace row in {path}: {line[:120]}")
            return []

        rows.append(payload)
    return rows


def parse_trace_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def pick_measured_timing_ms(wall_ms: float, trace_rows: list[dict[str, Any]], trace_meta: dict[str, Any]) -> tuple[float, str, dict[str, Any]]:
    timing_meta: dict[str, Any] = {
        "source": "wall-time",
        "wallTimeMs": wall_ms,
        "traceRows": len(trace_rows),
    }

    meta_execution_ns = safe_int(trace_meta.get("executionTotalNs"))
    if meta_execution_ns > 0:
        timing_meta.update(
            {
                "source": "execution-duration",
                "executionTotalNs": meta_execution_ns,
                "executionRows": safe_int(trace_meta.get("executionRowCount")),
                "executionBackend": trace_meta.get("executionBackend", "unknown"),
            },
        )
        return float(meta_execution_ns) / 1_000_000.0, "execution-duration", timing_meta

    row_execution_ns: list[int] = []
    for row in trace_rows:
        row_ns = row.get("executionDurationNs")
        if isinstance(row_ns, int) and row_ns >= 0:
            row_execution_ns.append(row_ns)

    if row_execution_ns and len(row_execution_ns) == len(trace_rows):
        timing_meta.update(
            {
                "source": "execution-duration",
                "executionTotalNs": sum(row_execution_ns),
                "executionRows": len(row_execution_ns),
                "executionBackend": trace_rows[0].get("executionBackend", "unknown"),
            },
        )
        return float(sum(row_execution_ns)) / 1_000_000.0, "execution-duration", timing_meta

    if not trace_rows:
        if isinstance(trace_meta.get("seqMax"), int):
            timing_meta["seqMax"] = trace_meta.get("seqMax")
        return wall_ms, "wall-time", timing_meta

    timestamps: list[int] = []
    for row in trace_rows:
        ts = row.get("timestampMonoNs")
        if isinstance(ts, int):
            timestamps.append(ts)

    if len(timestamps) < 2:
        return wall_ms, "wall-time", timing_meta

    first = min(timestamps)
    last = max(timestamps)
    measured_ms = float(last - first) / 1_000_000.0
    if measured_ms < 0:
        return wall_ms, "wall-time", timing_meta

    timing_meta.update(
        {
            "source": "trace-window",
            "traceWindowStartMonoNs": first,
            "traceWindowEndMonoNs": last,
            "traceRows": len(timestamps),
            "rowCount": safe_int(trace_meta.get("rowCount")),
        },
    )
    return measured_ms, "trace-window", timing_meta


def extract_metric_proxy(
    timings: list[float],
    sample_meta: list[dict[str, Any]],
) -> tuple[dict[str, float], list[str]]:
    timing_stats = format_stats(timings)
    reasons: list[str] = []

    # Validation/encode are derived from measured runtime timing and trace summary.
    encode_overhead_ns = timing_stats["meanMs"] * 1_000_000.0
    if not timings:
        encode_overhead_ns = 0.0

    trace_rows = [safe_int(meta.get("rowCount", 0)) for meta in sample_meta if isinstance(meta, dict)]
    allocations_per_frame = statistics.fmean(trace_rows) if trace_rows else 0.0

    matched_count = [safe_int(meta.get("matchedCount", 0)) for meta in sample_meta if isinstance(meta, dict)]
    command_count = [safe_int(meta.get("commandCount", 0)) for meta in sample_meta if isinstance(meta, dict)]
    if matched_count and command_count and sum(command_count) > 0:
        matched_ratio = sum(matched_count) / max(sum(command_count), 1)
        validation_overhead_ns = encode_overhead_ns * matched_ratio
    else:
        validation_overhead_ns = 0.0

    if not sample_meta:
        reasons.append("no_trace_meta_for_derived_validation_metrics")

    values = {
        "encode_overhead_ns": encode_overhead_ns,
        "validation_overhead_ns": validation_overhead_ns,
        "submit_latency_p50_ms": timing_stats["p50Ms"],
        "submit_latency_p95_ms": timing_stats["p95Ms"],
        "submit_latency_p99_ms": timing_stats["p99Ms"],
        "allocations_per_frame": allocations_per_frame,
    }
    return values, reasons


def load_workloads(path: str, workload_id: str) -> Workload:
    payload = load_json(path)
    raw = payload.get("workloads", [])
    if not isinstance(raw, list):
        raise ValueError(f"invalid workloads payload in {path}")

    matches = [item for item in raw if isinstance(item, dict) and item.get("id") == workload_id]
    if not matches:
        available = [str(item.get("id")) for item in raw if isinstance(item, dict)]
        raise ValueError(f"workload {workload_id!r} not found; available={available}")

    cfg = matches[0]
    raw_extra_args = cfg.get("extraArgs", [])
    if raw_extra_args is None:
        raw_extra_args = []
    if not isinstance(raw_extra_args, list):
        raise ValueError(
            f"invalid workload {workload_id!r}: extraArgs must be an array when present"
        )

    return Workload(
        workload_id=cfg["id"],
        name=cfg.get("name", workload_id),
        description=cfg.get("description", ""),
        commands_path=cfg.get("commandsPath", ""),
        quirks_path=cfg.get("quirksPath", ""),
        vendor=cfg.get("vendor", "intel"),
        api=cfg.get("api", "vulkan"),
        family=cfg.get("family", "gen12"),
        driver=cfg.get("driver", "31.0.101"),
        extra_args=[str(value) for value in raw_extra_args],
    )


def render_extra_args(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return shlex.join(str(arg) for arg in value)
    return str(value)


def backend_from_token(value: str) -> str | None:
    normalized = value.strip().lower()
    normalized = GPU_BACKEND_ALIASES.get(normalized, normalized)
    if normalized in KNOWN_GPU_BACKENDS:
        return normalized
    return None


def infer_backend_from_lane_name(lane: str) -> str | None:
    lane_lower = lane.strip().lower()
    if "vulkan" in lane_lower:
        return "vulkan"
    if "metal" in lane_lower:
        return "metal"
    if "d3d12" in lane_lower or "dx12" in lane_lower:
        return "d3d12"
    return None


def extract_backends_from_command(command: list[str]) -> set[str]:
    backends: set[str] = set()
    index = 0
    while index < len(command):
        token = command[index]
        if token == "--backend" and index + 1 < len(command):
            backend = backend_from_token(command[index + 1])
            if backend:
                backends.add(backend)
            index += 2
            continue
        if token.startswith("--backend="):
            backend = backend_from_token(token.split("=", 1)[1])
            if backend:
                backends.add(backend)
            index += 1
            continue
        if token == "--api" and index + 1 < len(command):
            backend = backend_from_token(command[index + 1])
            if backend:
                backends.add(backend)
            index += 2
            continue
        if token.startswith("--api="):
            backend = backend_from_token(token.split("=", 1)[1])
            if backend:
                backends.add(backend)
            index += 1
            continue
        if token == "--backend-lane" and index + 1 < len(command):
            backend = infer_backend_from_lane_name(command[index + 1])
            if backend:
                backends.add(backend)
            index += 2
            continue
        if token.startswith("--backend-lane="):
            backend = infer_backend_from_lane_name(token.split("=", 1)[1])
            if backend:
                backends.add(backend)
            index += 1
            continue
        if token == "--dawn-extra-args" and index + 1 < len(command):
            extra_arg = command[index + 1]
            if extra_arg == "--backend" and index + 2 < len(command):
                backend = backend_from_token(command[index + 2])
                if backend:
                    backends.add(backend)
                index += 3
                continue
            if extra_arg.startswith("--backend="):
                backend = backend_from_token(extra_arg.split("=", 1)[1])
                if backend:
                    backends.add(backend)
            index += 2
            continue
        if token.startswith("--dawn-extra-args="):
            extra_arg = token.split("=", 1)[1]
            if extra_arg == "--backend" and index + 1 < len(command):
                backend = backend_from_token(command[index + 1])
                if backend:
                    backends.add(backend)
                index += 2
                continue
            if extra_arg.startswith("--backend="):
                backend = backend_from_token(extra_arg.split("=", 1)[1])
                if backend:
                    backends.add(backend)
            index += 1
            continue
        index += 1
    return backends


def enforce_host_backend_policy(
    *,
    command: list[str],
    workload_api: str,
    requested_backend: str,
) -> None:
    host_name = platform.system().strip()
    allowed_backends = HOST_ALLOWED_GPU_BACKENDS.get(host_name.lower())
    if not allowed_backends:
        return

    detected_backends = extract_backends_from_command(command)
    if not detected_backends:
        workload_backend = backend_from_token(workload_api)
        if workload_backend:
            detected_backends.add(workload_backend)
        requested = backend_from_token(requested_backend)
        if requested:
            detected_backends.add(requested)

    disallowed = sorted(backend for backend in detected_backends if backend not in allowed_backends)
    if not disallowed:
        return

    allowed_text = ", ".join(sorted(allowed_backends))
    raise ValueError(
        f"host/backend policy violation on {host_name}: allowed backends are [{allowed_text}]. "
        "Use an OS-appropriate benchmark config (Metal on macOS, Vulkan on Linux, D3D12 on Windows). "
        "Blocked backends: "
        + ", ".join(disallowed)
    )


def command_for(
    template: str,
    workload: Workload,
    *,
    trace_jsonl: Path,
    trace_meta: Path,
    command_template_args: dict[str, Any],
) -> list[str]:
    context = {
        "commands": shlex.quote(workload.commands_path),
        "quirks": shlex.quote(workload.quirks_path),
        "vendor": shlex.quote(workload.vendor),
        "api": shlex.quote(workload.api),
        "family": shlex.quote(workload.family),
        "driver": shlex.quote(workload.driver),
        "workload": shlex.quote(workload.workload_id),
        "trace_jsonl": shlex.quote(str(trace_jsonl)),
        "trace_meta": shlex.quote(str(trace_meta)),
        "extra_args": render_extra_args(command_template_args.get("extra_args", [])),
    }
    for key, value in command_template_args.items():
        if key == "extra_args":
            continue
        context[key] = value
    resolved = template.format(**context)
    return shlex.split(resolved)


def run_once(command: list[str]) -> tuple[float, int, str]:
    start = time.perf_counter()
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed (rc={proc.returncode}): {' '.join(command)}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return elapsed_ms, proc.returncode, proc.stdout


def stable_trace_hash(sample_meta: list[dict[str, Any]]) -> str:
    latest = sample_meta[-1] if sample_meta else {}
    trace_hash = latest.get("hash")
    if isinstance(trace_hash, str) and trace_hash:
        return trace_hash
    return TRACE_SEED


def compute_quark_hash(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        return "missing"
    return hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]


def main() -> int:
    args = parse_args()
    if args.iterations < 0 or args.warmup < 0:
        raise ValueError("--iterations and --warmup must be >= 0")

    generated_at = datetime.now(timezone.utc).isoformat()
    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp) if args.timestamp_output else ""
    )
    workload = load_workloads(args.workloads, args.workload_id)

    bench_cfg = load_json(args.bench_config)
    metric_ids = [m["metricId"] for m in bench_cfg.get("matrix", []) if isinstance(m, dict)]
    baselines = [b["baselineId"] for b in bench_cfg.get("baselines", []) if isinstance(b, dict)]
    run_group = output_paths.derive_bench_out_group(args.out_report)

    out = output_paths.with_timestamp(
        args.out_dir,
        output_timestamp,
        enabled=args.timestamp_output,
        group=run_group,
    )
    out.mkdir(parents=True, exist_ok=True)

    command_records: list[dict[str, Any]] = []
    timings: list[float] = []
    sample_meta: list[dict[str, Any]] = []
    host_backend_policy_checked = False

    for run_idx in range(max(args.iterations + args.warmup, 0)):
        trace_jsonl = out / f"{workload.workload_id}.run{run_idx:03d}.ndjson"
        trace_meta_path = out / f"{workload.workload_id}.run{run_idx:03d}.meta.json"

        command = command_for(
            args.command_template,
            workload,
            trace_jsonl=trace_jsonl,
            trace_meta=trace_meta_path,
            command_template_args={
                "backend": args.backend,
                "gpu": args.gpu,
                "extra_args": [str(x) for x in workload.extra_args],
            },
        )
        if not host_backend_policy_checked:
            enforce_host_backend_policy(
                command=command,
                workload_api=workload.api,
                requested_backend=args.backend,
            )
            host_backend_policy_checked = True

        elapsed_ms, return_code, stdout = run_once(command)
        sample_trace_meta = parse_trace_meta(trace_meta_path)
        rows = parse_trace_rows(trace_jsonl)
        measured_ms, measured_source, timed_meta = pick_measured_timing_ms(
            wall_ms=elapsed_ms,
            trace_rows=rows,
            trace_meta=sample_trace_meta,
        )

        if run_idx < args.warmup:
            continue

        sample_meta.append(sample_trace_meta)
        timings.append(measured_ms)
        command_records.append(
            {
                "runIndex": run_idx,
                "command": command,
                "elapsedMs": elapsed_ms,
                "measuredMs": measured_ms,
                "timingSource": measured_source,
                "timing": timed_meta,
                "traceJsonlPath": str(trace_jsonl),
                "traceMetaPath": str(trace_meta_path),
                "returnCode": return_code,
                "stdoutLines": len(stdout.splitlines()),
            }
        )

    run_stats = format_stats(timings)
    metric_values, metric_reasons = extract_metric_proxy(timings, sample_meta)

    report_metrics = {metric: metric_values.get(metric, 0.0) for metric in metric_ids}

    # Subset only known metric ids; leave unknown metrics as zero for compatibility.
    baseline_deltas = {baseline: {metric: None for metric in metric_ids} for baseline in baselines}

    comparison_contract = bench_cfg.get("comparisonContract", {})
    comparison_status = "directional"
    comparison_reasons = metric_reasons
    if run_stats["count"] == 0:
        comparison_status = "scaffold"
        comparison_reasons.append("no_timed_samples")

    report = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "outputTimestamp": output_timestamp,
        "backend": args.backend,
        "outDir": str(out),
        "workload": {
            "id": workload.workload_id,
            "name": workload.name,
            "description": workload.description,
            "commandsPath": workload.commands_path,
            "quirksPath": workload.quirks_path,
            "vendor": workload.vendor,
            "api": workload.api,
            "family": workload.family,
            "driver": workload.driver,
            "extraArgs": workload.extra_args,
        },
        "metrics": report_metrics,
        "metricStatsMs": {
            "submit_latency_ms": run_stats,
        },
        "commandSamples": command_records,
        "baselineDeltas": baseline_deltas,
        "comparisonStatus": comparison_status,
        "comparisonReasons": comparison_reasons,
        "comparisonContract": comparison_contract,
    }

    run_id = args.run_id or stable_run_id(
        {
            "benchmarks": bench_cfg,
            "backend": args.backend,
            "gpu": args.gpu,
            "driver": args.driver,
            "commit": args.commit,
            "timestamp": generated_at,
            "workloadId": workload.workload_id,
        }
    )
    metadata = {
        "schemaVersion": 1,
        "runId": run_id,
        "timestamp": generated_at,
        "outputTimestamp": output_timestamp,
        "host": {
            "os": platform.system() or "unknown",
            "arch": platform.machine() or "unknown",
        },
        "gpu": args.gpu,
        "driver": args.driver,
        "backend": args.backend,
        "toolchains": {
            "zig": "unknown",
            "lean": "unknown",
        },
        "workloadId": workload.workload_id,
        "build": {
            "commit": args.commit,
            "flags": [],
        },
        "hashes": {
            "quirkSetHash": compute_quark_hash(workload.quirks_path),
            "traceHash": stable_trace_hash(sample_meta),
            "validatorHash": "unknown",
        },
    }

    out_report = output_paths.with_timestamp(
        args.out_report,
        output_timestamp,
        enabled=args.timestamp_output,
        group=run_group,
    )
    out_meta = output_paths.with_timestamp(
        args.out_metadata,
        output_timestamp,
        enabled=args.timestamp_output,
        group=run_group,
    )
    report["outPath"] = str(out_report)
    metadata["outPath"] = str(out_meta)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    out_meta.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    output_paths.write_run_manifest_for_outputs(
        [out, out_report, out_meta],
        {
            "runType": "run_bench",
            "config": {
                "benchConfig": args.bench_config,
                "workloads": args.workloads,
                "workloadId": args.workload_id,
                "iterations": args.iterations,
                "warmup": args.warmup,
                "backend": args.backend,
                "gpu": args.gpu,
                "driver": args.driver,
            },
            "fullRun": True,
            "claimGateRan": False,
            "dropinGateRan": False,
            "outDir": str(out),
            "reportPath": str(out_report),
            "metadataPath": str(out_meta),
            "status": "passed",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
