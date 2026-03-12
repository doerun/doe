"""Comparability helpers for compare_dawn_vs_doe."""

from __future__ import annotations

import json
import statistics
import subprocess
from pathlib import Path
from typing import Any, Callable

from compare_dawn_vs_doe_modules.timing_selection import (
    canonical_timing_source,
    classify_timing_source,
)


NATIVE_EXECUTION_OPERATION_TIMING_SOURCES = {
    "doe-execution-total-ns",
    "doe-execution-row-total-ns",
    "doe-execution-dispatch-window-ns",
    "doe-execution-encode-ns",
    "doe-execution-gpu-timestamp-ns",
}
DOE_OPERATION_TIMING_SOURCES = {
    *NATIVE_EXECUTION_OPERATION_TIMING_SOURCES,
    "doe-trace-window",
}
DAWN_OPERATION_TIMING_SOURCES = {
    "dawn-perf-wall-time",
    "dawn-perf-cpu-time",
    "dawn-perf-gpu-time",
    "dawn-perf-wall-ns",
}
OBLIGATION_SCHEMA_VERSION = 1
_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPARABILITY_OBLIGATIONS_PATH = _REPO_ROOT / "config/comparability-obligations.json"
RENDER_ENCODE_TIMING_DOMAINS = {"render", "render-bundle"}
_PHASE_ASYMMETRY_THRESHOLD = 0.10
_TIMING_PHASE_FIELDS: tuple[tuple[str, str], ...] = (
    ("setup", "executionSetupTotalNs"),
    ("encode", "executionEncodeTotalNs"),
    ("submitWait", "executionSubmitWaitTotalNs"),
)


def _normalized_domain(workload_domain: str) -> str:
    return workload_domain.strip().lower()


def _strict_doe_expected_sources(workload_domain: str) -> set[str]:
    normalized_domain = _normalized_domain(workload_domain)
    if normalized_domain == "upload":
        return {"doe-execution-row-total-ns"}
    if normalized_domain in RENDER_ENCODE_TIMING_DOMAINS:
        return {"doe-execution-encode-ns"}
    return {"doe-execution-total-ns"}


def _strict_doe_expected_policies(workload_domain: str) -> set[str]:
    normalized_domain = _normalized_domain(workload_domain)
    if normalized_domain == "upload":
        return {"upload-row-total-preferred"}
    if normalized_domain in RENDER_ENCODE_TIMING_DOMAINS:
        return {"render-encode-preferred"}
    return {"<none>"}


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


def _sources_match_with_runtime_compatibility(
    *,
    left_sources: list[str],
    right_sources: list[str],
    workload_domain: str,
    comparability_mode: str,
    required_timing_class: str,
    is_dawn_vs_doe: bool,
    is_left_dawn_perf: bool,
    is_right_dawn_perf: bool,
    is_left_dawn_delegate: bool,
    is_right_dawn_delegate: bool,
    is_left_dawn: bool,
    is_right_dawn: bool,
    is_left_doe: bool,
    is_right_doe: bool,
) -> bool:
    if not left_sources or not right_sources:
        return False
    if comparability_mode == "strict" and required_timing_class == "process-wall":
        return set(left_sources) == {"wall-time"} and set(right_sources) == {"wall-time"}
    if not is_dawn_vs_doe:
        return left_sources == right_sources

    left_set = set(left_sources)
    right_set = set(right_sources)
    normalized_domain = _normalized_domain(workload_domain)
    if comparability_mode == "strict":
        doe_expected = _strict_doe_expected_sources(normalized_domain)
        left_expected: set[str] | None = None
        right_expected: set[str] | None = None
        if is_left_dawn_perf:
            left_expected = {"dawn-perf-wall-time"}
        elif is_left_dawn_delegate or is_left_doe:
            left_expected = doe_expected
        if is_right_dawn_perf:
            right_expected = {"dawn-perf-wall-time"}
        elif is_right_dawn_delegate or is_right_doe:
            right_expected = doe_expected
        if left_expected is not None and left_set != left_expected:
            return False
        if right_expected is not None and right_set != right_expected:
            return False
        return True

    if is_left_dawn_perf and not left_set.issubset(DAWN_OPERATION_TIMING_SOURCES):
        return False
    if is_right_dawn_perf and not right_set.issubset(DAWN_OPERATION_TIMING_SOURCES):
        return False
    if is_left_dawn_delegate and not left_set.issubset(DOE_OPERATION_TIMING_SOURCES):
        return False
    if is_right_dawn_delegate and not right_set.issubset(DOE_OPERATION_TIMING_SOURCES):
        return False
    if is_left_doe and not left_set.issubset(DOE_OPERATION_TIMING_SOURCES):
        return False
    if is_right_doe and not right_set.issubset(DOE_OPERATION_TIMING_SOURCES):
        return False
    return True


def _timing_selection_policy_match_with_runtime_compatibility(
    *,
    left_policies: list[str],
    right_policies: list[str],
    workload_domain: str,
    comparability_mode: str,
    required_timing_class: str,
    is_dawn_vs_doe: bool,
    is_left_dawn_perf: bool,
    is_right_dawn_perf: bool,
    is_left_dawn_delegate: bool,
    is_right_dawn_delegate: bool,
    is_left_dawn: bool,
    is_right_dawn: bool,
    is_left_doe: bool,
    is_right_doe: bool,
) -> bool:
    if not left_policies or not right_policies:
        return False
    if comparability_mode == "strict" and required_timing_class == "process-wall":
        expected = {"forced-process-wall"}
        return set(left_policies) == expected and set(right_policies) == expected
    if not is_dawn_vs_doe:
        return left_policies == right_policies

    left_set = set(left_policies)
    right_set = set(right_policies)
    normalized_domain = _normalized_domain(workload_domain)

    if comparability_mode == "strict":
        doe_expected = _strict_doe_expected_policies(normalized_domain)
        left_expected: set[str] | None = None
        right_expected: set[str] | None = None
        if is_left_dawn_perf:
            left_expected = {"<none>"}
        elif is_left_dawn_delegate or is_left_doe:
            left_expected = doe_expected
        if is_right_dawn_perf:
            right_expected = {"<none>"}
        elif is_right_dawn_delegate or is_right_doe:
            right_expected = doe_expected
        if left_expected is not None and left_set != left_expected:
            return False
        if right_expected is not None and right_set != right_expected:
            return False
        return True

    doe_allowed = {"<none>"}
    if normalized_domain == "upload":
        doe_allowed = {"upload-row-total-preferred"}
    elif normalized_domain in RENDER_ENCODE_TIMING_DOMAINS:
        doe_allowed = {"<none>", "render-encode-preferred"}
    dawn_perf_allowed = {"<none>"}
    dawn_delegate_allowed = doe_allowed

    if is_left_dawn_perf and not left_set.issubset(dawn_perf_allowed):
        return False
    if is_right_dawn_perf and not right_set.issubset(dawn_perf_allowed):
        return False
    if is_left_dawn_delegate and not left_set.issubset(dawn_delegate_allowed):
        return False
    if is_right_dawn_delegate and not right_set.issubset(dawn_delegate_allowed):
        return False
    if is_left_doe and not left_set.issubset(doe_allowed):
        return False
    if is_right_doe and not right_set.issubset(doe_allowed):
        return False
    return True


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
        "left_right_trace_meta_source_match": (
            True,
            fact_bool("trace_meta_source_match_applies"),
            fact_bool("left_right_trace_meta_source_match"),
        ),
        "left_right_timing_selection_policy_match": (
            True,
            fact_bool("timing_selection_policy_match_applies"),
            fact_bool("left_right_timing_selection_policy_match"),
        ),
        "left_right_queue_sync_mode_match": (
            True,
            fact_bool("queue_sync_mode_match_applies"),
            fact_bool("left_right_queue_sync_mode_match"),
        ),
        "left_right_timing_phase_match": (
            True,
            fact_bool("timing_phase_match_applies"),
            fact_bool("left_right_timing_phase_match"),
        ),
        "left_right_execution_shape_match": (
            True,
            fact_bool("execution_shape_match_applies"),
            fact_bool("left_right_execution_shape_match"),
        ),
        "left_right_hardware_path_match": (
            True,
            fact_bool("hardware_path_match_applies"),
            fact_bool("left_right_hardware_path_match"),
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
        "left_right_upload_buffer_usage_match": (
            True,
            fact_bool("upload_domain"),
            fact_bool("left_right_upload_buffer_usage_match"),
        ),
        "left_right_upload_submit_cadence_match": (
            True,
            fact_bool("upload_domain"),
            fact_bool("left_right_upload_submit_cadence_match"),
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

from compare_dawn_vs_doe_modules.comparability_runtime import (
    assess_timing_phase_equivalence,
    compare_assessment,
)
from compare_dawn_vs_doe_modules.comparability_upload_contract import (
    assert_runtime_not_stale,
    find_fawn_runtime_index,
    is_dawn_writebuffer_upload_workload,
    subprocess_combined_output,
    validate_upload_apples_to_apples,
    verify_fawn_upload_runtime_contract,
)
