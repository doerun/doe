"""Report-level coherence checks for compare-report comparability.

The per-workload comparability obligations decide whether each workload is
comparable. This module validates the report-level invariant: a report may only
remain top-level ``comparisonStatus=comparable`` when the matching layer, the
obligation layer, structural execution-shape checks, timing-phase checks, and
optional sample-floor policy all agree on the same workload rows.

Sample-floor policy has two tiers. Claim-eligible workloads must clear the
``min_timed_samples`` floor (default 7 per ``comparabilityDefaults``). Non-claim-
eligible workloads (smoke, diagnostic, directional) must clear the lower
``smoke_min_timed_samples`` floor (default 3). The two-tier structure exists so
that ``count: 2`` smoke artifacts cannot land ``comparable: true`` at the report
level even though they are never claim-eligible.
"""

from __future__ import annotations

from typing import Any

REQUIRED_COMPARABLE_OBLIGATIONS = (
    "workload_marked_comparable",
    "left_samples_present",
    "right_samples_present",
    "baseline_comparison_timing_phase_match",
    "baseline_comparison_execution_shape_match",
    "baseline_comparison_hardware_path_match",
)
OPTIONAL_COMPARABLE_OBLIGATIONS = (
    "baseline_comparison_submit_scope_match",
)


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _stats_count(workload: dict[str, Any], key: str) -> int:
    stats = workload.get(key, {})
    if not isinstance(stats, dict):
        return 0
    return _safe_int(stats.get("count"), 0)


def _obligations_by_id(comparability: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_obligations = comparability.get("obligations", [])
    if not isinstance(raw_obligations, list):
        return {}
    obligations: dict[str, dict[str, Any]] = {}
    for obligation in raw_obligations:
        if not isinstance(obligation, dict):
            continue
        obligation_id = obligation.get("id")
        if isinstance(obligation_id, str) and obligation_id:
            obligations[obligation_id] = obligation
    return obligations


def _obligation_failed(obligation: dict[str, Any]) -> bool:
    return (
        obligation.get("blocking") is True
        and obligation.get("applicable") is True
        and obligation.get("passes") is not True
    )


def _sample_count_from_obligation(
    obligation: dict[str, Any],
    detail_key: str,
) -> int | None:
    details = obligation.get("details", {})
    if not isinstance(details, dict):
        return None
    value = details.get(detail_key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _phase_counts_match_samples(
    obligation: dict[str, Any],
    *,
    baseline_count: int,
    comparison_count: int,
) -> list[str]:
    details = obligation.get("details", {})
    if not isinstance(details, dict):
        return []
    phase_counts = details.get("phaseSampleCounts", {})
    if not isinstance(phase_counts, dict):
        return []

    failures: list[str] = []
    for phase_name, counts in sorted(phase_counts.items()):
        if not isinstance(counts, dict):
            continue
        phase_baseline = _safe_int(counts.get("baseline"), -1)
        phase_comparison = _safe_int(counts.get("comparison"), -1)
        if phase_baseline not in (-1, baseline_count):
            failures.append(
                f"{phase_name} baseline phase sample count {phase_baseline} "
                f"does not match baselineStatsMs.count {baseline_count}"
            )
        if phase_comparison not in (-1, comparison_count):
            failures.append(
                f"{phase_name} comparison phase sample count {phase_comparison} "
                f"does not match comparisonStatsMs.count {comparison_count}"
            )
    return failures


def assess_workload(
    workload: dict[str, Any],
    *,
    min_timed_samples: int = 0,
    smoke_min_timed_samples: int = 0,
) -> dict[str, Any]:
    workload_id = str(workload.get("id", "?")).strip() or "?"
    reasons: list[str] = []

    workload_matching = workload.get("workloadMatching", {})
    if not isinstance(workload_matching, dict):
        reasons.append("missing workloadMatching object")
    elif workload_matching.get("matched") is not True:
        reasons.append("workloadMatching.matched is not true")

    comparability = workload.get("comparability", {})
    if not isinstance(comparability, dict):
        return {
            "workloadId": workload_id,
            "status": "fail",
            "reasons": [*reasons, "missing comparability object"],
        }

    baseline_count = _stats_count(workload, "baselineStatsMs")
    comparison_count = _stats_count(workload, "comparisonStatsMs")
    if baseline_count <= 0:
        reasons.append("baselineStatsMs.count is not positive")
    if comparison_count <= 0:
        reasons.append("comparisonStatsMs.count is not positive")

    obligations = _obligations_by_id(comparability)
    if comparability.get("comparable") is True:
        if workload.get("workloadComparable") is not True:
            reasons.append("comparability.comparable=true but workloadComparable is not true")
        blocking_failed = comparability.get("blockingFailedObligations")
        if not isinstance(blocking_failed, list):
            reasons.append("blockingFailedObligations is not a list")
        elif blocking_failed:
            reasons.append(
                "comparability.comparable=true but blockingFailedObligations is non-empty"
            )

        for obligation_id in REQUIRED_COMPARABLE_OBLIGATIONS:
            obligation = obligations.get(obligation_id)
            if obligation is None:
                reasons.append(f"missing required comparable obligation {obligation_id}")
                continue
            if _obligation_failed(obligation):
                reasons.append(f"required comparable obligation failed: {obligation_id}")

        for obligation_id in OPTIONAL_COMPARABLE_OBLIGATIONS:
            obligation = obligations.get(obligation_id)
            if obligation is not None and _obligation_failed(obligation):
                reasons.append(f"optional applicable obligation failed: {obligation_id}")

        left_samples = obligations.get("left_samples_present", {})
        right_samples = obligations.get("right_samples_present", {})
        left_obligation_count = _sample_count_from_obligation(
            left_samples, "baselineSampleCount"
        )
        right_obligation_count = _sample_count_from_obligation(
            right_samples, "comparisonSampleCount"
        )
        if left_obligation_count is not None and left_obligation_count != baseline_count:
            reasons.append(
                "left_samples_present baselineSampleCount "
                f"{left_obligation_count} does not match baselineStatsMs.count "
                f"{baseline_count}"
            )
        if right_obligation_count is not None and right_obligation_count != comparison_count:
            reasons.append(
                "right_samples_present comparisonSampleCount "
                f"{right_obligation_count} does not match comparisonStatsMs.count "
                f"{comparison_count}"
            )

        timing_phase = obligations.get("baseline_comparison_timing_phase_match")
        if timing_phase is not None:
            reasons.extend(
                _phase_counts_match_samples(
                    timing_phase,
                    baseline_count=baseline_count,
                    comparison_count=comparison_count,
                )
            )

        execution_shape = obligations.get("baseline_comparison_execution_shape_match")
        if execution_shape is not None and execution_shape.get("applicable") is True:
            details = execution_shape.get("details", {})
            if isinstance(details, dict):
                if not details.get("baselineNormalizedExecutionShapes"):
                    reasons.append("missing baseline normalized execution shape")
                if not details.get("comparisonNormalizedExecutionShapes"):
                    reasons.append("missing comparison normalized execution shape")

        claim_eligible = workload.get("claimEligible") is True
        if claim_eligible:
            applied_floor = min_timed_samples
            floor_kind = "comparability"
        else:
            applied_floor = smoke_min_timed_samples
            floor_kind = "smoke-comparability"
        if applied_floor > 0:
            if baseline_count < applied_floor:
                reasons.append(
                    f"baselineStatsMs.count {baseline_count} < {floor_kind} floor "
                    f"{applied_floor}"
                )
            if comparison_count < applied_floor:
                reasons.append(
                    f"comparisonStatsMs.count {comparison_count} < {floor_kind} floor "
                    f"{applied_floor}"
                )

    return {
        "workloadId": workload_id,
        "status": "pass" if not reasons else "fail",
        "reasons": reasons,
        "sampleCounts": {
            "baseline": baseline_count,
            "comparison": comparison_count,
        },
    }


def assess_report(
    report: dict[str, Any],
    *,
    min_timed_samples: int = 0,
    smoke_min_timed_samples: int = 0,
    benchmark_policy_path: str = "",
) -> dict[str, Any]:
    workloads_raw = report.get("workloads", [])
    workloads = workloads_raw if isinstance(workloads_raw, list) else []
    failures: list[dict[str, Any]] = []
    comparable_workload_count = 0
    observed_non_comparable = 0

    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        comparability = workload.get("comparability", {})
        if isinstance(comparability, dict) and comparability.get("comparable") is True:
            comparable_workload_count += 1
        else:
            observed_non_comparable += 1
        result = assess_workload(
            workload,
            min_timed_samples=max(min_timed_samples, 0),
            smoke_min_timed_samples=max(smoke_min_timed_samples, 0),
        )
        if result["status"] != "pass":
            failures.append(result)

    summary = report.get("comparabilitySummary", {})
    if isinstance(summary, dict):
        summary_non_comparable = _safe_int(summary.get("nonComparableCount"), -1)
        summary_workload_count = _safe_int(summary.get("workloadCount"), -1)
        if summary_workload_count not in (-1, len(workloads)):
            failures.append(
                {
                    "workloadId": "<report>",
                    "status": "fail",
                    "reasons": [
                        "comparabilitySummary.workloadCount "
                        f"{summary_workload_count} does not match workloads length "
                        f"{len(workloads)}"
                    ],
                }
            )
        if summary_non_comparable not in (-1, observed_non_comparable):
            failures.append(
                {
                    "workloadId": "<report>",
                    "status": "fail",
                    "reasons": [
                        "comparabilitySummary.nonComparableCount "
                        f"{summary_non_comparable} does not match observed "
                        f"{observed_non_comparable}"
                    ],
                }
            )

    if report.get("comparisonStatus") == "comparable" and failures:
        failures.append(
            {
                "workloadId": "<report>",
                "status": "fail",
                "reasons": [
                    "comparisonStatus=comparable while comparability coherence failed"
                ],
            }
        )

    return {
        "status": "pass" if not failures else "fail",
        "checkedWorkloadCount": len(workloads),
        "comparableWorkloadCount": comparable_workload_count,
        "failureCount": len(failures),
        "failures": failures,
        "minTimedSamples": max(min_timed_samples, 0),
        "smokeMinTimedSamples": max(smoke_min_timed_samples, 0),
        "benchmarkPolicyPath": benchmark_policy_path,
        "requiredComparableObligations": list(REQUIRED_COMPARABLE_OBLIGATIONS),
        "optionalComparableObligations": list(OPTIONAL_COMPARABLE_OBLIGATIONS),
    }
