"""Comparability helpers for compare_dawn_vs_fawn."""

from __future__ import annotations

import json
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
OBLIGATION_SCHEMA_VERSION = 1
_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPARABILITY_OBLIGATIONS_PATH = _REPO_ROOT / "config/comparability-obligations.json"


def _obligation(
    *,
    obligation_id: str,
    blocking: bool,
    applicable: bool,
    passes: bool,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": obligation_id,
        "blocking": bool(blocking),
        "applicable": bool(applicable),
        "passes": bool(passes) if applicable else True,
        "details": details if isinstance(details, dict) else {},
    }


def _record_obligation(
    obligations: list[dict[str, Any]],
    reasons: list[str],
    *,
    obligation_id: str,
    blocking: bool,
    applicable: bool,
    passes: bool,
    failure_reason: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    obligations.append(
        _obligation(
            obligation_id=obligation_id,
            blocking=blocking,
            applicable=applicable,
            passes=passes,
            details=details,
        )
    )
    if blocking and applicable and (not passes) and failure_reason:
        reasons.append(failure_reason)


def _load_canonical_obligation_ids() -> tuple[str, ...]:
    payload = json.loads(_COMPARABILITY_OBLIGATIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(
            "invalid comparability obligation contract: expected object at "
            f"{_COMPARABILITY_OBLIGATIONS_PATH}"
        )
    schema_version = payload.get("schemaVersion")
    if schema_version != OBLIGATION_SCHEMA_VERSION:
        raise ValueError(
            "comparability obligation contract schemaVersion mismatch: "
            f"expected {OBLIGATION_SCHEMA_VERSION}, got {schema_version!r}"
        )
    raw_ids = payload.get("obligationIds")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError(
            "invalid comparability obligation contract: obligationIds must be a non-empty list"
        )
    ids: list[str] = []
    for index, raw_id in enumerate(raw_ids):
        if not isinstance(raw_id, str) or not raw_id:
            raise ValueError(
                "invalid comparability obligation contract: "
                f"obligationIds[{index}] must be a non-empty string"
            )
        ids.append(raw_id)
    if len(ids) != len(set(ids)):
        raise ValueError("invalid comparability obligation contract: duplicate obligationIds")
    return tuple(ids)


CANONICAL_COMPARABILITY_OBLIGATION_IDS = _load_canonical_obligation_ids()


def evaluate_comparability_from_facts(
    facts: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(facts, dict):
        raise ValueError("comparability facts must be an object")

    def fact_bool(name: str) -> bool:
        value = facts.get(name)
        if not isinstance(value, bool):
            raise ValueError(f"comparability facts field {name!r} must be bool")
        return value

    result_by_id: dict[str, tuple[bool, bool, bool]] = {
        "workload_marked_comparable": (
            True,
            True,
            fact_bool("workload_marked_comparable"),
        ),
        "left_samples_present": (
            True,
            True,
            fact_bool("left_samples_present"),
        ),
        "right_samples_present": (
            True,
            True,
            fact_bool("right_samples_present"),
        ),
        "left_single_timing_class": (
            True,
            True,
            fact_bool("left_single_timing_class"),
        ),
        "right_single_timing_class": (
            True,
            True,
            fact_bool("right_single_timing_class"),
        ),
        "left_required_timing_class": (
            True,
            fact_bool("required_timing_class_applies"),
            fact_bool("left_required_timing_class"),
        ),
        "right_required_timing_class": (
            True,
            fact_bool("required_timing_class_applies"),
            fact_bool("right_required_timing_class"),
        ),
        "left_right_timing_class_match": (
            True,
            fact_bool("timing_class_match_applies"),
            fact_bool("left_right_timing_class_match"),
        ),
        "left_native_operation_timing_for_webgpu_ffi": (
            True,
            fact_bool("operation_timing_class_required"),
            fact_bool("left_native_operation_timing_for_webgpu_ffi"),
        ),
        "left_upload_ignore_first_scope_consistent": (
            True,
            fact_bool("upload_domain"),
            fact_bool("left_upload_ignore_first_scope_consistent"),
        ),
        "right_upload_ignore_first_scope_consistent": (
            True,
            fact_bool("upload_domain"),
            fact_bool("right_upload_ignore_first_scope_consistent"),
        ),
        "left_execution_evidence_present": (
            True,
            not fact_bool("allow_left_no_execution"),
            fact_bool("left_execution_evidence_present"),
        ),
        "left_successful_execution_present": (
            True,
            not fact_bool("allow_left_no_execution"),
            fact_bool("left_successful_execution_present"),
        ),
        "left_success_or_unsupported_or_skipped": (
            True,
            fact_bool("allow_left_no_execution"),
            fact_bool("left_success_or_unsupported_or_skipped"),
        ),
        "left_execution_errors_absent": (
            True,
            True,
            fact_bool("left_execution_errors_absent"),
        ),
        "right_execution_errors_absent": (
            True,
            True,
            fact_bool("right_execution_errors_absent"),
        ),
        "left_resource_probe_available": (
            True,
            fact_bool("resource_probe_enabled"),
            fact_bool("left_resource_probe_available"),
        ),
        "right_resource_probe_available": (
            True,
            fact_bool("resource_probe_enabled"),
            fact_bool("right_resource_probe_available"),
        ),
        "strict_resource_sample_target_positive": (
            True,
            fact_bool("resource_probe_enabled") and fact_bool("strict_comparability"),
            fact_bool("resource_sample_target_positive"),
        ),
        "left_resource_sample_target_match": (
            True,
            fact_bool("resource_probe_enabled")
            and fact_bool("strict_comparability")
            and fact_bool("resource_sample_target_positive"),
            fact_bool("left_resource_sample_target_match"),
        ),
        "right_resource_sample_target_match": (
            True,
            fact_bool("resource_probe_enabled")
            and fact_bool("strict_comparability")
            and fact_bool("resource_sample_target_positive"),
            fact_bool("right_resource_sample_target_match"),
        ),
        "left_resource_sampling_not_truncated": (
            True,
            fact_bool("resource_probe_enabled")
            and fact_bool("strict_comparability")
            and fact_bool("resource_sample_target_positive"),
            fact_bool("left_resource_sampling_not_truncated"),
        ),
        "right_resource_sampling_not_truncated": (
            True,
            fact_bool("resource_probe_enabled")
            and fact_bool("strict_comparability")
            and fact_bool("resource_sample_target_positive"),
            fact_bool("right_resource_sampling_not_truncated"),
        ),
        "left_resource_sample_density_sufficient": (
            True,
            fact_bool("resource_probe_enabled") and (not fact_bool("strict_comparability")),
            fact_bool("left_resource_sample_density_sufficient"),
        ),
        "right_resource_sample_density_sufficient": (
            True,
            fact_bool("resource_probe_enabled") and (not fact_bool("strict_comparability")),
            fact_bool("right_resource_sample_density_sufficient"),
        ),
    }

    obligations: list[dict[str, Any]] = []
    for obligation_id in CANONICAL_COMPARABILITY_OBLIGATION_IDS:
        rule = result_by_id.get(obligation_id)
        if rule is None:
            raise ValueError(
                "missing comparability fact mapping for obligation id: "
                f"{obligation_id}"
            )
        blocking, applicable, passes = rule
        obligations.append(
            _obligation(
                obligation_id=obligation_id,
                blocking=blocking,
                applicable=applicable,
                passes=passes,
                details={},
            )
        )

    extra_rule_ids = sorted(set(result_by_id.keys()) - set(CANONICAL_COMPARABILITY_OBLIGATION_IDS))
    if extra_rule_ids:
        raise ValueError(
            "comparability fact mapping has ids missing from canonical contract: "
            + ", ".join(extra_rule_ids)
        )

    generated_obligation_ids = [str(item.get("id", "")) for item in obligations]
    if generated_obligation_ids != list(CANONICAL_COMPARABILITY_OBLIGATION_IDS):
        raise ValueError(
            "internal comparability obligation contract drift: generated ids do not "
            "match config/comparability-obligations.json"
        )

    blocking_failed_obligations = [
        str(item.get("id", ""))
        for item in obligations
        if item.get("applicable") is True
        and item.get("blocking") is True
        and item.get("passes") is False
    ]
    advisory_failed_obligations = [
        str(item.get("id", ""))
        for item in obligations
        if item.get("applicable") is True
        and item.get("blocking") is False
        and item.get("passes") is False
    ]

    return {
        "obligationSchemaVersion": OBLIGATION_SCHEMA_VERSION,
        "obligations": obligations,
        "blockingFailedObligations": blocking_failed_obligations,
        "advisoryFailedObligations": advisory_failed_obligations,
        "comparable": len(blocking_failed_obligations) == 0,
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
        if Path(token).name == "doe-zig-runtime":
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
            "strict upload comparability requires a rebuilt doe-zig-runtime binary; "
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
            f"executed doe-zig-runtime binary; missing help flags: {', '.join(missing_flags)}"
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
    workload_domain: str,
    left: dict[str, Any],
    right: dict[str, Any],
    required_timing_class: str,
    allow_left_no_execution: bool,
    resource_probe: str,
    comparability_mode: str,
    resource_sample_target_count: int,
) -> dict[str, Any]:
    left_samples_raw = left.get("commandSamples", [])
    right_samples_raw = right.get("commandSamples", [])
    left_samples = left_samples_raw if isinstance(left_samples_raw, list) else []
    right_samples = right_samples_raw if isinstance(right_samples_raw, list) else []

    left_sources = sorted({str(sample.get("timingSource", "")) for sample in left_samples})
    right_sources = sorted({str(sample.get("timingSource", "")) for sample in right_samples})
    left_classes = sorted({classify_timing_source(source) for source in left_sources if source})
    right_classes = sorted({classify_timing_source(source) for source in right_sources if source})
    left_class = left_classes[0] if len(left_classes) == 1 else "mixed"
    right_class = right_classes[0] if len(right_classes) == 1 else "mixed"

    reasons: list[str] = []
    resource_reasons: list[str] = []
    obligations: list[dict[str, Any]] = []

    _record_obligation(
        obligations,
        reasons,
        obligation_id="workload_marked_comparable",
        blocking=True,
        applicable=True,
        passes=bool(workload_comparable),
        failure_reason="workload is marked non-comparable by workload contract",
        details={"workloadComparable": bool(workload_comparable)},
    )
    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_samples_present",
        blocking=True,
        applicable=True,
        passes=len(left_samples) > 0,
        failure_reason="left side has no measured samples",
        details={"leftSampleCount": len(left_samples)},
    )
    _record_obligation(
        obligations,
        reasons,
        obligation_id="right_samples_present",
        blocking=True,
        applicable=True,
        passes=len(right_samples) > 0,
        failure_reason="right side has no measured samples",
        details={"rightSampleCount": len(right_samples)},
    )
    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_single_timing_class",
        blocking=True,
        applicable=True,
        passes=len(left_classes) == 1,
        failure_reason=f"left side uses mixed timing classes: {left_classes}",
        details={"leftTimingClasses": left_classes},
    )
    _record_obligation(
        obligations,
        reasons,
        obligation_id="right_single_timing_class",
        blocking=True,
        applicable=True,
        passes=len(right_classes) == 1,
        failure_reason=f"right side uses mixed timing classes: {right_classes}",
        details={"rightTimingClasses": right_classes},
    )

    required_timing_class_applies = required_timing_class != "any"
    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_required_timing_class",
        blocking=True,
        applicable=required_timing_class_applies,
        passes=left_class == required_timing_class,
        failure_reason=f"left timing class is {left_class}, required {required_timing_class}",
        details={
            "requiredTimingClass": required_timing_class,
            "leftTimingClass": left_class,
        },
    )
    _record_obligation(
        obligations,
        reasons,
        obligation_id="right_required_timing_class",
        blocking=True,
        applicable=required_timing_class_applies,
        passes=right_class == required_timing_class,
        failure_reason=f"right timing class is {right_class}, required {required_timing_class}",
        details={
            "requiredTimingClass": required_timing_class,
            "rightTimingClass": right_class,
        },
    )

    timing_match_applies = left_class != "mixed" and right_class != "mixed"
    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_right_timing_class_match",
        blocking=True,
        applicable=timing_match_applies,
        passes=left_class == right_class,
        failure_reason=f"left/right timing class mismatch: {left_class} vs {right_class}",
        details={
            "leftTimingClass": left_class,
            "rightTimingClass": right_class,
        },
    )

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
    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_native_operation_timing_for_webgpu_ffi",
        blocking=True,
        applicable=required_timing_class == "operation",
        passes=len(invalid_native_execution_sources) == 0,
        failure_reason=(
            "left side uses non-native operation timing source(s) for webgpu-ffi execution: "
            + ", ".join(sorted(invalid_native_execution_sources))
        ),
        details={
            "invalidCanonicalSources": sorted(invalid_native_execution_sources),
        },
    )

    def collect_upload_ignore_first_violations(
        *,
        side_name: str,
        samples: list[dict[str, Any]],
    ) -> list[str]:
        side_reasons: list[str] = []
        for sample in samples:
            timing = sample.get("timing", {})
            if not isinstance(timing, dict):
                continue
            if timing.get("uploadIgnoreFirstApplied") is not True:
                continue
            run_index = safe_int(sample.get("runIndex"), default=-1)
            run_label = f"run {run_index}" if run_index >= 0 else "sample"
            base_raw = timing.get("uploadIgnoreFirstBaseTimingSource")
            adjusted_raw = timing.get("uploadIgnoreFirstAdjustedTimingSource")
            base_source = str(base_raw) if isinstance(base_raw, str) else ""
            adjusted_source = str(adjusted_raw) if isinstance(adjusted_raw, str) else ""
            canonical_base = canonical_timing_source(base_source)
            canonical_adjusted = canonical_timing_source(adjusted_source)
            canonical_selected = canonical_timing_source(str(sample.get("timingSource", "")))
            if canonical_adjusted != "fawn-execution-row-total-ns":
                side_reasons.append(
                    f"{side_name} {run_label} ignore-first adjusted source is "
                    f"{canonical_adjusted}; require fawn-execution-row-total-ns"
                )
            if canonical_base and canonical_adjusted and canonical_base != canonical_adjusted:
                side_reasons.append(
                    f"{side_name} {run_label} uses mixed-scope ignore-first sources "
                    f"(base={canonical_base}, adjusted={canonical_adjusted})"
                )
            if canonical_adjusted and canonical_selected != canonical_adjusted:
                side_reasons.append(
                    f"{side_name} {run_label} selected timing source {canonical_selected} "
                    f"does not match ignore-first adjusted source {canonical_adjusted}"
                )
        return side_reasons

    upload_scope_applies = workload_domain == "upload"
    left_upload_scope_reasons = (
        collect_upload_ignore_first_violations(side_name="left", samples=left_samples)
        if upload_scope_applies
        else []
    )
    right_upload_scope_reasons = (
        collect_upload_ignore_first_violations(side_name="right", samples=right_samples)
        if upload_scope_applies
        else []
    )
    reasons.extend(left_upload_scope_reasons)
    reasons.extend(right_upload_scope_reasons)
    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_upload_ignore_first_scope_consistent",
        blocking=True,
        applicable=upload_scope_applies,
        passes=len(left_upload_scope_reasons) == 0,
        details={"violationCount": len(left_upload_scope_reasons)},
    )
    _record_obligation(
        obligations,
        reasons,
        obligation_id="right_upload_ignore_first_scope_consistent",
        blocking=True,
        applicable=upload_scope_applies,
        passes=len(right_upload_scope_reasons) == 0,
        details={"violationCount": len(right_upload_scope_reasons)},
    )

    left_has_execution = False
    left_successful_execution = False
    left_has_unsupported_or_skipped = False
    for sample in left_samples:
        trace_meta = sample.get("traceMeta", {})
        execution_success = safe_int(trace_meta.get("executionSuccessCount"), default=0)
        execution_rows = safe_int(trace_meta.get("executionRowCount"), default=0)
        execution_unsupported = safe_int(trace_meta.get("executionUnsupportedCount"), default=0)
        execution_skipped = safe_int(trace_meta.get("executionSkippedCount"), default=0)
        if execution_success > 0 or execution_rows > 0:
            left_has_execution = True
        if execution_success > 0:
            left_successful_execution = True
        if execution_unsupported > 0 or execution_skipped > 0:
            left_has_unsupported_or_skipped = True

    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_execution_evidence_present",
        blocking=True,
        applicable=not allow_left_no_execution,
        passes=left_has_execution,
        failure_reason="left side has no execution evidence (executionSuccessCount/executionRowCount)",
        details={
            "allowLeftNoExecution": bool(allow_left_no_execution),
            "leftHasExecutionEvidence": left_has_execution,
        },
    )
    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_successful_execution_present",
        blocking=True,
        applicable=not allow_left_no_execution,
        passes=left_successful_execution,
        failure_reason="left side has no successful execution samples (executionSuccessCount=0)",
        details={
            "leftSuccessfulExecution": left_successful_execution,
        },
    )
    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_success_or_unsupported_or_skipped",
        blocking=True,
        applicable=allow_left_no_execution,
        passes=left_successful_execution or left_has_unsupported_or_skipped,
        failure_reason=(
            "left side has no successful execution samples and no unsupported/skipped execution evidence"
        ),
        details={
            "leftSuccessfulExecution": left_successful_execution,
            "leftHasUnsupportedOrSkippedEvidence": left_has_unsupported_or_skipped,
        },
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

    _record_obligation(
        obligations,
        reasons,
        obligation_id="left_execution_errors_absent",
        blocking=True,
        applicable=True,
        passes=left_execution_error_samples == 0,
        failure_reason=(
            f"left side reported execution errors in {left_execution_error_samples}/{len(left_samples)} samples"
        ),
        details={
            "leftExecutionErrorSampleCount": left_execution_error_samples,
            "leftSampleCount": len(left_samples),
        },
    )
    _record_obligation(
        obligations,
        reasons,
        obligation_id="right_execution_errors_absent",
        blocking=True,
        applicable=True,
        passes=right_execution_error_samples == 0,
        failure_reason=(
            f"right side reported execution errors in {right_execution_error_samples}/{len(right_samples)} samples"
        ),
        details={
            "rightExecutionErrorSampleCount": right_execution_error_samples,
            "rightSampleCount": len(right_samples),
        },
    )

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

    def record_resource_obligation(
        *,
        obligation_id: str,
        applicable: bool,
        passes: bool,
        failure_reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        _record_obligation(
            obligations,
            reasons,
            obligation_id=obligation_id,
            blocking=True,
            applicable=applicable,
            passes=passes,
            failure_reason=failure_reason,
            details=details,
        )
        if applicable and (not passes):
            resource_reasons.append(failure_reason)

    resource_probe_applies = resource_probe != "none"
    record_resource_obligation(
        obligation_id="left_resource_probe_available",
        applicable=resource_probe_applies,
        passes=left_resource_probe_available > 0,
        failure_reason="left side has no successful GPU resource probe samples",
        details={"leftResourceProbeAvailableCount": left_resource_probe_available},
    )
    record_resource_obligation(
        obligation_id="right_resource_probe_available",
        applicable=resource_probe_applies,
        passes=right_resource_probe_available > 0,
        failure_reason="right side has no successful GPU resource probe samples",
        details={"rightResourceProbeAvailableCount": right_resource_probe_available},
    )

    if resource_probe_applies and comparability_mode == "strict":
        target_positive = resource_sample_target_count > 0
        record_resource_obligation(
            obligation_id="strict_resource_sample_target_positive",
            applicable=True,
            passes=target_positive,
            failure_reason=(
                "strict resource comparability requires --resource-sample-target-count > 0 "
                "for N-vs-N probing"
            ),
            details={"resourceSampleTargetCount": resource_sample_target_count},
        )
        if target_positive:
            record_resource_obligation(
                obligation_id="left_resource_sample_target_match",
                applicable=True,
                passes=left_resource_sample_median == resource_sample_target_count,
                failure_reason=(
                    "left side resource sample median does not match target "
                    f"({left_resource_sample_median} vs target={resource_sample_target_count})"
                ),
                details={
                    "leftResourceSampleMedian": left_resource_sample_median,
                    "resourceSampleTargetCount": resource_sample_target_count,
                },
            )
            record_resource_obligation(
                obligation_id="right_resource_sample_target_match",
                applicable=True,
                passes=right_resource_sample_median == resource_sample_target_count,
                failure_reason=(
                    "right side resource sample median does not match target "
                    f"({right_resource_sample_median} vs target={resource_sample_target_count})"
                ),
                details={
                    "rightResourceSampleMedian": right_resource_sample_median,
                    "resourceSampleTargetCount": resource_sample_target_count,
                },
            )
            record_resource_obligation(
                obligation_id="left_resource_sampling_not_truncated",
                applicable=True,
                passes=left_resource_truncated == 0,
                failure_reason=(
                    "left side resource probing truncated before process completion; "
                    "increase --resource-sample-target-count or reduce --resource-sample-ms"
                ),
                details={"leftResourceSamplingTruncatedCount": left_resource_truncated},
            )
            record_resource_obligation(
                obligation_id="right_resource_sampling_not_truncated",
                applicable=True,
                passes=right_resource_truncated == 0,
                failure_reason=(
                    "right side resource probing truncated before process completion; "
                    "increase --resource-sample-target-count or reduce --resource-sample-ms"
                ),
                details={"rightResourceSamplingTruncatedCount": right_resource_truncated},
            )
    elif resource_probe_applies:
        record_resource_obligation(
            obligation_id="left_resource_sample_density_sufficient",
            applicable=True,
            passes=left_resource_sample_median >= 5,
            failure_reason=(
                "left side resource sampling too sparse "
                f"(median samples={left_resource_sample_median}, require >=5)"
            ),
            details={"leftResourceSampleMedian": left_resource_sample_median},
        )
        record_resource_obligation(
            obligation_id="right_resource_sample_density_sufficient",
            applicable=True,
            passes=right_resource_sample_median >= 5,
            failure_reason=(
                "right side resource sampling too sparse "
                f"(median samples={right_resource_sample_median}, require >=5)"
            ),
            details={"rightResourceSampleMedian": right_resource_sample_median},
        )

    blocking_failed_obligations = [
        str(item.get("id", ""))
        for item in obligations
        if item.get("applicable") is True
        and item.get("blocking") is True
        and item.get("passes") is False
    ]
    advisory_failed_obligations = [
        str(item.get("id", ""))
        for item in obligations
        if item.get("applicable") is True
        and item.get("blocking") is False
        and item.get("passes") is False
    ]

    return {
        "comparable": len(blocking_failed_obligations) == 0,
        "requiredTimingClass": required_timing_class,
        "obligationSchemaVersion": OBLIGATION_SCHEMA_VERSION,
        "obligations": obligations,
        "blockingFailedObligations": blocking_failed_obligations,
        "advisoryFailedObligations": advisory_failed_obligations,
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
