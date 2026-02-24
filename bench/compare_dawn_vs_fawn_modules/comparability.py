"""Comparability helpers for compare_dawn_vs_fawn."""

from __future__ import annotations

import statistics
import subprocess
from pathlib import Path
from typing import Any, Callable

from compare_dawn_vs_fawn_modules.timing_selection import (
    canonical_timing_source,
    classify_timing_source,
)


NATIVE_EXECUTION_OPERATION_TIMING_SOURCES = {
    "fawn-execution-total-ns",
    "fawn-execution-row-total-ns",
    "fawn-execution-dispatch-window-ns",
    "fawn-execution-encode-ns",
    "fawn-execution-gpu-timestamp-ns",
}


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


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


def is_dawn_writebuffer_upload_workload(workload: Any) -> bool:
    if workload.domain != "upload":
        return False
    return (
        "BufferUploadPerf.Run/" in workload.dawn_filter
        and "WriteBuffer" in workload.dawn_filter
    )


def validate_upload_apples_to_apples(
    workload: Any,
    *,
    comparability_mode: str,
) -> None:
    if workload.left_upload_submit_every < 1:
        raise ValueError(
            f"invalid workload {workload.id}: leftUploadSubmitEvery must be >= 1"
        )
    if workload.right_upload_submit_every < 1:
        raise ValueError(
            f"invalid workload {workload.id}: rightUploadSubmitEvery must be >= 1"
        )
    if workload.left_command_repeat % workload.left_upload_submit_every != 0:
        raise ValueError(
            f"invalid workload {workload.id}: leftCommandRepeat ({workload.left_command_repeat}) "
            f"must be divisible by leftUploadSubmitEvery ({workload.left_upload_submit_every})"
        )
    if workload.right_command_repeat % workload.right_upload_submit_every != 0:
        raise ValueError(
            f"invalid workload {workload.id}: rightCommandRepeat ({workload.right_command_repeat}) "
            f"must be divisible by rightUploadSubmitEvery ({workload.right_upload_submit_every})"
        )

    if not is_dawn_writebuffer_upload_workload(workload):
        return

    if comparability_mode == "strict" and workload.left_upload_buffer_usage != "copy-dst":
        raise ValueError(
            "strict upload comparability requires leftUploadBufferUsage=copy-dst "
            f"for Dawn WriteBuffer workload {workload.id}; got {workload.left_upload_buffer_usage}"
        )


def find_fawn_runtime_index(command: list[str]) -> int | None:
    for idx, token in enumerate(command):
        if Path(token).name == "fawn-zig-runtime":
            return idx
    return None


def subprocess_combined_output(proc: subprocess.CompletedProcess[str]) -> str:
    stdout = proc.stdout if isinstance(proc.stdout, str) else ""
    stderr = proc.stderr if isinstance(proc.stderr, str) else ""
    return f"{stdout}\n{stderr}".strip()


def assert_runtime_not_stale(
    runtime_binary: Path,
    *,
    runtime_source_paths: tuple[Path, ...],
) -> None:
    if not runtime_binary.exists():
        return
    runtime_mtime = runtime_binary.stat().st_mtime
    stale_sources = [
        str(path)
        for path in runtime_source_paths
        if path.exists() and path.stat().st_mtime > runtime_mtime
    ]
    if stale_sources:
        raise ValueError(
            "strict upload comparability requires a rebuilt fawn-zig-runtime binary; "
            "binary appears older than runtime sources: "
            + ", ".join(stale_sources)
        )


def verify_fawn_upload_runtime_contract(
    *,
    template: str,
    workload: Any,
    command_for_fn: Callable[..., list[str]],
    runtime_source_paths: tuple[Path, ...],
) -> None:
    queue_wait_mode_value: str | None = None
    for idx, arg in enumerate(workload.extra_args):
        if arg != "--queue-wait-mode":
            continue
        if idx + 1 >= len(workload.extra_args):
            raise ValueError(
                f"invalid workload {workload.id}: --queue-wait-mode requires a value"
            )
        queue_wait_mode_value = str(workload.extra_args[idx + 1])
        if queue_wait_mode_value not in ("process-events", "wait-any"):
            raise ValueError(
                f"invalid workload {workload.id}: --queue-wait-mode must be process-events|wait-any"
            )

    preflight_trace_jsonl = Path("/tmp/fawn-upload-preflight.ndjson")
    preflight_trace_meta = Path("/tmp/fawn-upload-preflight.meta.json")
    preflight_extra_args = list(workload.extra_args)
    preflight_extra_args.extend(
        [
            "--upload-buffer-usage",
            workload.left_upload_buffer_usage,
            "--upload-submit-every",
            str(workload.left_upload_submit_every),
        ]
    )
    command = command_for_fn(
        template,
        workload=workload,
        workload_id=workload.id,
        commands_path=workload.commands_path,
        trace_jsonl=preflight_trace_jsonl,
        trace_meta=preflight_trace_meta,
        extra_args=preflight_extra_args,
    )
    runtime_index = find_fawn_runtime_index(command)
    if runtime_index is None:
        return

    runtime_token = command[runtime_index]
    runtime_binary = Path(runtime_token)
    if not runtime_binary.is_absolute():
        runtime_binary = Path.cwd() / runtime_binary
    assert_runtime_not_stale(
        runtime_binary,
        runtime_source_paths=runtime_source_paths,
    )

    runtime_prefix = command[: runtime_index + 1]
    help_proc = subprocess.run(
        [*runtime_prefix, "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    help_output = subprocess_combined_output(help_proc)
    required_flags = ["--upload-buffer-usage", "--upload-submit-every"]
    if queue_wait_mode_value is not None:
        required_flags.append("--queue-wait-mode")
    missing_flags = [flag for flag in required_flags if flag not in help_output]
    if missing_flags:
        raise ValueError(
            "strict upload comparability requires runtime upload knobs to be supported by the "
            f"executed fawn-zig-runtime binary; missing help flags: {', '.join(missing_flags)}"
        )

    capability_checks = [
        (
            ["--upload-buffer-usage", "invalid-value", "--help"],
            "invalid --upload-buffer-usage",
        ),
        (
            ["--upload-submit-every", "0", "--help"],
            "invalid --upload-submit-every",
        ),
    ]
    if queue_wait_mode_value is not None:
        capability_checks.append(
            (
                ["--queue-wait-mode", "invalid-value", "--help"],
                "invalid --queue-wait-mode",
            )
        )
    for probe_args, expected_fragment in capability_checks:
        probe_proc = subprocess.run(
            [*runtime_prefix, *probe_args],
            text=True,
            capture_output=True,
            check=False,
        )
        probe_output = subprocess_combined_output(probe_proc)
        if expected_fragment not in probe_output:
            raise ValueError(
                "strict upload comparability requires runtime validation of upload knobs; "
                f"missing expected probe output '{expected_fragment}' for command: "
                f"{' '.join([*runtime_prefix, *probe_args])}"
            )


def compare_assessment(
    *,
    workload_comparable: bool,
    left: dict[str, Any],
    right: dict[str, Any],
    required_timing_class: str,
    allow_left_no_execution: bool,
    resource_probe: str,
    comparability_mode: str,
    resource_sample_target_count: int,
) -> dict[str, Any]:
    left_samples = left.get("commandSamples", [])
    right_samples = right.get("commandSamples", [])

    left_sources = sorted({str(sample.get("timingSource", "")) for sample in left_samples})
    right_sources = sorted({str(sample.get("timingSource", "")) for sample in right_samples})
    left_classes = sorted({classify_timing_source(source) for source in left_sources if source})
    right_classes = sorted({classify_timing_source(source) for source in right_sources if source})
    reasons: list[str] = []

    if not workload_comparable:
        reasons.append("workload is marked non-comparable by workload contract")
    if not left_samples:
        reasons.append("left side has no measured samples")
    if not right_samples:
        reasons.append("right side has no measured samples")
    if len(left_classes) != 1:
        reasons.append(f"left side uses mixed timing classes: {left_classes}")
    if len(right_classes) != 1:
        reasons.append(f"right side uses mixed timing classes: {right_classes}")

    left_class = left_classes[0] if len(left_classes) == 1 else "mixed"
    right_class = right_classes[0] if len(right_classes) == 1 else "mixed"

    if required_timing_class == "operation":
        invalid_native_execution_sources: set[str] = set()
        for sample in left_samples:
            trace_meta = sample.get("traceMeta", {})
            if not isinstance(trace_meta, dict):
                continue
            if str(trace_meta.get("executionBackend", "")) != "webgpu-ffi":
                continue
            execution_dispatch = safe_int(trace_meta.get("executionDispatchCount"), default=0)
            execution_success = safe_int(trace_meta.get("executionSuccessCount"), default=0)
            execution_rows = safe_int(trace_meta.get("executionRowCount"), default=0)
            if execution_dispatch <= 0 and execution_success <= 0 and execution_rows <= 0:
                continue
            timing_source_raw = sample.get("timingSource")
            if not isinstance(timing_source_raw, str) or not timing_source_raw:
                invalid_native_execution_sources.add("<missing>")
                continue
            canonical_source = canonical_timing_source(timing_source_raw)
            if canonical_source not in NATIVE_EXECUTION_OPERATION_TIMING_SOURCES:
                invalid_native_execution_sources.add(canonical_source)
        if invalid_native_execution_sources:
            reasons.append(
                "left side uses non-native operation timing source(s) for webgpu-ffi execution: "
                + ", ".join(sorted(invalid_native_execution_sources))
            )

    if required_timing_class != "any":
        if left_class != required_timing_class:
            reasons.append(f"left timing class is {left_class}, required {required_timing_class}")
        if right_class != required_timing_class:
            reasons.append(f"right timing class is {right_class}, required {required_timing_class}")
    if left_class != "mixed" and right_class != "mixed" and left_class != right_class:
        reasons.append(f"left/right timing class mismatch: {left_class} vs {right_class}")

    if not allow_left_no_execution:
        left_has_execution = False
        left_successful_execution = False
        for sample in left_samples:
            trace_meta = sample.get("traceMeta", {})
            execution_success = safe_int(trace_meta.get("executionSuccessCount"), default=0)
            execution_rows = safe_int(trace_meta.get("executionRowCount"), default=0)
            if execution_success > 0 or execution_rows > 0:
                left_has_execution = True
            if execution_success > 0:
                left_successful_execution = True
        if not left_has_execution:
            reasons.append("left side has no execution evidence (executionSuccessCount/executionRowCount)")
        if not left_successful_execution:
            reasons.append("left side has no successful execution samples (executionSuccessCount=0)")
    else:
        left_successful_execution = False
        left_has_unsupported_or_skipped = False
        for sample in left_samples:
            trace_meta = sample.get("traceMeta", {})
            execution_success = safe_int(trace_meta.get("executionSuccessCount"), default=0)
            execution_unsupported = safe_int(trace_meta.get("executionUnsupportedCount"), default=0)
            execution_skipped = safe_int(trace_meta.get("executionSkippedCount"), default=0)
            if execution_success > 0:
                left_successful_execution = True
                break
            if execution_unsupported > 0 or execution_skipped > 0:
                left_has_unsupported_or_skipped = True
        if (not left_successful_execution) and (not left_has_unsupported_or_skipped):
            reasons.append(
                "left side has no successful execution samples and no unsupported/skipped execution evidence"
            )

    left_execution_error_samples = 0
    right_execution_error_samples = 0
    for sample in left_samples:
        trace_meta = sample.get("traceMeta", {})
        if safe_int(trace_meta.get("executionErrorCount"), default=0) > 0:
            left_execution_error_samples += 1
    for sample in right_samples:
        trace_meta = sample.get("traceMeta", {})
        if safe_int(trace_meta.get("executionErrorCount"), default=0) > 0:
            right_execution_error_samples += 1
    if left_execution_error_samples > 0:
        reasons.append(
            f"left side reported execution errors in {left_execution_error_samples}/{len(left_samples)} samples"
        )
    if right_execution_error_samples > 0:
        reasons.append(
            f"right side reported execution errors in {right_execution_error_samples}/{len(right_samples)} samples"
        )

    resource_reasons: list[str] = []
    left_resource_sample_counts: list[int] = []
    right_resource_sample_counts: list[int] = []
    left_resource_probe_available = 0
    right_resource_probe_available = 0
    left_resource_truncated = 0
    right_resource_truncated = 0

    for sample in left_samples:
        resource = sample.get("resource", {})
        if isinstance(resource, dict):
            count = parse_int(resource.get("resourceSampleCount"))
            if count is not None:
                left_resource_sample_counts.append(count)
            if resource.get("gpuMemoryProbeAvailable") is True:
                left_resource_probe_available += 1
            if resource.get("resourceSamplingTruncated") is True:
                left_resource_truncated += 1
    for sample in right_samples:
        resource = sample.get("resource", {})
        if isinstance(resource, dict):
            count = parse_int(resource.get("resourceSampleCount"))
            if count is not None:
                right_resource_sample_counts.append(count)
            if resource.get("gpuMemoryProbeAvailable") is True:
                right_resource_probe_available += 1
            if resource.get("resourceSamplingTruncated") is True:
                right_resource_truncated += 1

    left_resource_sample_median = (
        int(statistics.median(left_resource_sample_counts))
        if left_resource_sample_counts
        else 0
    )
    right_resource_sample_median = (
        int(statistics.median(right_resource_sample_counts))
        if right_resource_sample_counts
        else 0
    )

    if resource_probe != "none":
        if left_resource_probe_available == 0:
            resource_reasons.append("left side has no successful GPU resource probe samples")
        if right_resource_probe_available == 0:
            resource_reasons.append("right side has no successful GPU resource probe samples")

        if comparability_mode == "strict":
            if resource_sample_target_count <= 0:
                resource_reasons.append(
                    "strict resource comparability requires --resource-sample-target-count > 0 for N-vs-N probing"
                )
            else:
                if left_resource_sample_median != resource_sample_target_count:
                    resource_reasons.append(
                        "left side resource sample median does not match target "
                        f"({left_resource_sample_median} vs target={resource_sample_target_count})"
                    )
                if right_resource_sample_median != resource_sample_target_count:
                    resource_reasons.append(
                        "right side resource sample median does not match target "
                        f"({right_resource_sample_median} vs target={resource_sample_target_count})"
                    )
                if left_resource_truncated > 0:
                    resource_reasons.append(
                        "left side resource probing truncated before process completion; "
                        "increase --resource-sample-target-count or reduce --resource-sample-ms"
                    )
                if right_resource_truncated > 0:
                    resource_reasons.append(
                        "right side resource probing truncated before process completion; "
                        "increase --resource-sample-target-count or reduce --resource-sample-ms"
                    )
        else:
            if left_resource_sample_median < 5:
                resource_reasons.append(
                    f"left side resource sampling too sparse (median samples={left_resource_sample_median}, require >=5)"
                )
            if right_resource_sample_median < 5:
                resource_reasons.append(
                    f"right side resource sampling too sparse (median samples={right_resource_sample_median}, require >=5)"
                )

    reasons.extend(resource_reasons)
    return {
        "comparable": len(reasons) == 0,
        "requiredTimingClass": required_timing_class,
        "leftTimingSources": left_sources,
        "rightTimingSources": right_sources,
        "leftTimingClass": left_class,
        "rightTimingClass": right_class,
        "resourceProbe": resource_probe,
        "leftResourceSampleMedian": left_resource_sample_median,
        "rightResourceSampleMedian": right_resource_sample_median,
        "leftResourceProbeAvailableCount": left_resource_probe_available,
        "rightResourceProbeAvailableCount": right_resource_probe_available,
        "resourceSampleTargetCount": max(resource_sample_target_count, 0),
        "leftResourceSamplingTruncatedCount": left_resource_truncated,
        "rightResourceSamplingTruncatedCount": right_resource_truncated,
        "leftExecutionErrorSampleCount": left_execution_error_samples,
        "rightExecutionErrorSampleCount": right_execution_error_samples,
        "resourceReasons": resource_reasons,
        "reasons": reasons,
    }
