"""Report assembly and timing-interpretation synthesis for the compare runner.

Builds report header, per-workload entries, overall summaries, and final
output artifacts. Extracted from the former compare wrapper per the 1200-line
Python tooling file limit.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.lib import output_paths
from native_compare_modules import comparability as comparability_mod
from native_compare_modules import claimability as claimability_mod
from native_compare_modules import operator_diff as operator_diff_mod
from native_compare_modules import reporting as reporting_mod
from native_compare_modules.config_support import (
    Workload,
    BenchmarkMethodologyPolicy,
    percent_delta,
)
from native_compare_modules.runner import (
    file_sha256,
    json_sha256,
    collect_trace_meta_hashes,
    safe_float,
)
from native_compare_modules.timing_interpretation import (
    build_timing_interpretation,
    command_sample_field_values_ms,
    delta_percent_from_stats,
)
from native_compare_modules.comparability import (
    compare_assessment,
    validate_upload_apples_to_apples,
)
from native_compare_modules.claimability import (
    assess_claimability,
    default_claim_min_timed_samples,
    required_positive_percentiles,
)
from native_compare_modules.reporting import format_stats
from native_compare_modules.runner import run_workload


def build_report_header(
    *,
    args: Any,
    workloads_path: Path,
    benchmark_policy: BenchmarkMethodologyPolicy,
    output_timestamp: str,
    out: Path,
    workspace: Path,
) -> dict[str, Any]:
    selector = getattr(args, "selector", {}) if isinstance(getattr(args, "selector", {}), dict) else {}
    selector_benchmark_classes = selector.get("benchmarkClass", [])
    selector_comparability = selector.get("comparability", [])
    if args.workload_cohort == "doe-advantage":
        benchmark_intent = "doe-advantage"
    elif args.workload_cohort == "comparability-candidates":
        benchmark_intent = "comparability-candidates"
    elif selector_benchmark_classes == ["comparable"] or selector_comparability == ["comparable"]:
        benchmark_intent = "apples-to-apples"
    else:
        benchmark_intent = "mixed"
    workload_contract = {
        "path": str(workloads_path),
        "sha256": file_sha256(workloads_path),
    }
    benchmark_policy_contract = {
        "path": benchmark_policy.source_path,
        "schemaVersion": 1,
        "sha256": file_sha256(Path(benchmark_policy.source_path)),
    }
    config_contract = None
    if args.config:
        config_path = Path(args.config).resolve()
        if config_path.exists():
            config_contract = {
                "path": str(config_path),
                "sha256": file_sha256(config_path),
            }
    return build_report_header_from_contracts(
        args=args,
        workload_contract=workload_contract,
        benchmark_policy_contract=benchmark_policy_contract,
        min_dispatch_window_ns_without_encode=(
            benchmark_policy.min_dispatch_window_ns_without_encode
        ),
        min_dispatch_window_coverage_percent_without_encode=(
            benchmark_policy.min_dispatch_window_coverage_percent_without_encode
        ),
        local_claim_min_timed_samples=benchmark_policy.local_claim_min_timed_samples,
        release_claim_min_timed_samples=benchmark_policy.release_claim_min_timed_samples,
        output_timestamp=output_timestamp,
        out=out,
        workspace=workspace,
        config_contract=config_contract,
    )


def build_report_header_from_contracts(
    *,
    args: Any,
    workload_contract: dict[str, Any],
    benchmark_policy_contract: dict[str, Any],
    min_dispatch_window_ns_without_encode: int,
    min_dispatch_window_coverage_percent_without_encode: float,
    local_claim_min_timed_samples: int,
    release_claim_min_timed_samples: int,
    output_timestamp: str,
    out: Path,
    workspace: Path,
    config_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selector = (
        getattr(args, "selector", {})
        if isinstance(getattr(args, "selector", {}), dict)
        else {}
    )
    selector_benchmark_classes = selector.get("benchmarkClass", [])
    selector_comparability = selector.get("comparability", [])
    if args.workload_cohort == "doe-advantage":
        benchmark_intent = "doe-advantage"
    elif args.workload_cohort == "comparability-candidates":
        benchmark_intent = "comparability-candidates"
    elif (
        selector_benchmark_classes == ["comparable"]
        or selector_comparability == ["comparable"]
    ):
        benchmark_intent = "apples-to-apples"
    else:
        benchmark_intent = "mixed"
    report: dict[str, Any] = {
        "schemaVersion": 5,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "outputTimestamp": output_timestamp,
        "outPath": str(out),
        "workspacePath": str(workspace),
        "benchmarkIntent": benchmark_intent,
        "runParameters": {
            "iterations": args.iterations,
            "warmup": args.warmup,
            "workloadCooldownMs": args.workload_cooldown_ms,
        },
        "comparisonAxes": {
            "boundary": getattr(args, "boundary", "") or None,
            "runtimeHost": getattr(args, "runtime_host", "") or None,
            "temperature": getattr(args, "temperature", "") or None,
            "comparisonView": getattr(args, "comparison_view", "") or None,
            "providerSet": getattr(args, "provider_set", "") or None,
        },
        "participants": {
            "baseline": {
                "name": args.baseline_name,
                "id": getattr(args, "baseline_provider_id", "") or None,
                "executorId": getattr(args, "baseline_executor_id", "") or None,
                "role": "baseline",
            },
            "comparison": {
                "name": args.comparison_name,
                "id": getattr(args, "comparison_provider_id", "") or None,
                "executorId": getattr(args, "comparison_executor_id", "") or None,
                "role": "comparison",
            },
        },
        "deltaPercentConvention": {
            "baseline": "baseline",
            "formula": "((comparisonMs / baselineMs) - 1) * 100",
            "positive": "baseline faster",
            "negative": "baseline slower",
            "zero": "parity",
        },
        "timingInterpretationPolicy": {
            "selectedMetricField": "deltaPercent",
            "selectedMetricUse": "methodology-selected apples-to-apples claim metric",
            "workloadUnitWallMetricField": "timingInterpretation.workloadUnitWall.deltaPercent",
            "workloadUnitWallMetricUse": "timed workload-unit wall end-to-end ranking metric",
            "workloadUnitWallMetricScope": "workloadUnitWall",
            "narrowSelectedScopeClass": "narrow-hot-path",
            "narrowSelectedMetricEligibleForClaims": False,
            "narrowHotPathClaimMetricField": "timingInterpretation.workloadUnitWall.deltaPercent",
            "narrowHotPathClaimMetricScope": "workloadUnitWall",
            "legacyAliases": {
                "timingInterpretation.headlineProcessWall": "timingInterpretation.workloadUnitWall",
                "overallHeadlineProcessWall": "overallWorkloadUnitWall",
            },
            "guidance": (
                "When timingInterpretation.selectedTiming.scopeClass is narrow-hot-path, "
                "deltaPercent remains a phase-specific diagnostic. Claimability evaluates "
                "timingInterpretation.workloadUnitWall.deltaPercent when that full "
                "metric is available."
            ),
        },
        "comparabilityPolicy": {
            "mode": args.comparability,
            "requiredTimingClass": args.require_timing_class,
            "allowBaselineNoExecution": bool(args.allow_baseline_no_execution),
            "resourceProbe": args.resource_probe,
            "resourceSampleMs": args.resource_sample_ms,
            "resourceSampleTargetCount": args.resource_sample_target_count,
            "workloadCooldownMs": args.workload_cooldown_ms,
            "workloadCohort": args.workload_cohort,
            "requireNativeExecutionTimingForBaselineOperation": (
                args.require_timing_class == "operation"
            ),
            "obligationContract": {
                "schemaVersion": comparability_mod.OBLIGATION_SCHEMA_VERSION,
                "blockingFailureFailsComparability": True,
            },
            "dispatchWindowSelectionThresholds": {
                "minDispatchWindowNsWithoutEncode": (
                    min_dispatch_window_ns_without_encode
                ),
                "minDispatchWindowCoveragePercentWithoutEncode": (
                    min_dispatch_window_coverage_percent_without_encode
                ),
            },
        },
        "claimabilityPolicy": {
            "mode": args.claimability,
            "minTimedSamples": (
                args.claim_min_timed_samples
                if args.claim_min_timed_samples > 0
                else (
                    local_claim_min_timed_samples
                    if args.claimability == "local"
                    else (
                        release_claim_min_timed_samples
                        if args.claimability == "release"
                        else 0
                    )
                )
            ),
            "requiredPositivePercentiles": required_positive_percentiles(args.claimability),
            "defaults": {
                "localMinTimedSamples": local_claim_min_timed_samples,
                "releaseMinTimedSamples": release_claim_min_timed_samples,
            },
        },
        "benchmarkPolicy": benchmark_policy_contract,
        "workloadContract": workload_contract,
        "workloads": [],
    }
    if args.config:
        report["configPath"] = str(Path(args.config).resolve())
    if isinstance(config_contract, dict):
        report["configContract"] = config_contract
    return report


def compute_workload_delta(
    baseline_stats: dict[str, Any],
    comparison_stats: dict[str, Any],
) -> dict[str, float]:
    return {
        "p10Percent": percent_delta(safe_float(baseline_stats["p10Ms"]) or 0.0, safe_float(comparison_stats["p10Ms"]) or 0.0),
        "p50Percent": percent_delta(safe_float(baseline_stats["p50Ms"]) or 0.0, safe_float(comparison_stats["p50Ms"]) or 0.0),
        "p95Percent": percent_delta(safe_float(baseline_stats["p95Ms"]) or 0.0, safe_float(comparison_stats["p95Ms"]) or 0.0),
        "p99Percent": percent_delta(safe_float(baseline_stats["p99Ms"]) or 0.0, safe_float(comparison_stats["p99Ms"]) or 0.0),
        "meanPercent": percent_delta(safe_float(baseline_stats["meanMs"]) or 0.0, safe_float(comparison_stats["meanMs"]) or 0.0),
    }


def build_workload_report_entry(
    *,
    workload: Workload,
    baseline: dict[str, Any],
    comparison: dict[str, Any],
    delta: dict[str, float],
    timing_interpretation: dict[str, Any],
    comparability: dict[str, Any],
    claimability: dict[str, Any],
    baseline_trace_meta_hashes: list[dict[str, str]],
    comparison_trace_meta_hashes: list[dict[str, str]],
    claim_workload_hash: str,
    previous_claim_workload_hash: str,
    claim_workload_context: dict[str, Any],
    operator_diff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": workload.id,
        "name": workload.name,
        "description": workload.description,
        "domain": workload.domain,
        "comparabilityNotes": workload.comparability_notes,
        "asyncDiagnosticsMode": workload.async_diagnostics_mode or None,
        "timingNormalization": {
            "baselineDivisor": workload.baseline_timing_divisor,
            "comparisonDivisor": workload.comparison_timing_divisor,
            "baselineCommandRepeat": workload.baseline_command_repeat,
            "comparisonCommandRepeat": workload.comparison_command_repeat,
            "baselineIgnoreFirstOps": workload.baseline_ignore_first_ops,
            "comparisonIgnoreFirstOps": workload.comparison_ignore_first_ops,
            "baselineUploadBufferUsage": workload.baseline_upload_buffer_usage,
            "comparisonUploadBufferUsage": workload.comparison_upload_buffer_usage,
            "baselineUploadSubmitEvery": workload.baseline_upload_submit_every,
            "comparisonUploadSubmitEvery": workload.comparison_upload_submit_every,
            "note": workload.timing_normalization_note,
        },
        "workloadComparable": workload.comparable,
        "benchmarkClass": workload.benchmark_class,
        "cohorts": workload.cohorts,
        "directionalReason": workload.directional_reason or None,
        "pathAsymmetry": workload.path_asymmetry,
        "pathAsymmetryNote": workload.path_asymmetry_note,
        "comparabilityCandidate": {
            "enabled": workload.comparability_candidate,
            "tier": workload.comparability_candidate_tier,
            "notes": workload.comparability_candidate_notes,
        },
        "workloadAllowBaselineNoExecution": workload.allow_baseline_no_execution,
        "workloadDefault": workload.include_by_default,
        "baseline": baseline,
        "comparison": comparison,
        "deltaPercent": delta,
        "timingInterpretation": timing_interpretation,
        "comparability": comparability,
        "claimability": claimability,
        "traceMetaHashes": {
            "baseline": baseline_trace_meta_hashes,
            "comparison": comparison_trace_meta_hashes,
        },
        "claimWorkloadHash": {
            "algorithm": "sha256",
            "previousHash": previous_claim_workload_hash,
            "hash": claim_workload_hash,
            "context": claim_workload_context,
        },
        "operatorDiff": operator_diff if isinstance(operator_diff, dict) else None,
    }


def build_claim_workload_context(
    *,
    workload: Workload,
    report: dict[str, Any],
    baseline_trace_meta_hashes: list[dict[str, str]],
    comparison_trace_meta_hashes: list[dict[str, str]],
    delta: dict[str, float],
    comparability: dict[str, Any],
    claimability: dict[str, Any],
) -> dict[str, Any]:
    return {
        "workloadId": workload.id,
        "workloadContractSha256": report["workloadContract"]["sha256"],
        "configContractSha256": (
            report.get("configContract", {}).get("sha256", "")
            if isinstance(report.get("configContract"), dict)
            else ""
        ),
        "benchmarkPolicySha256": report["benchmarkPolicy"]["sha256"],
        "baselineTraceMetaSha256": [
            entry["sha256"] for entry in baseline_trace_meta_hashes
        ],
        "comparisonTraceMetaSha256": [
            entry["sha256"] for entry in comparison_trace_meta_hashes
        ],
        "benchmarkClass": workload.benchmark_class,
        "directionalReason": workload.directional_reason,
        "workloadPathAsymmetry": workload.path_asymmetry,
        "workloadPathAsymmetryNote": workload.path_asymmetry_note,
        "deltaPercent": delta,
        "comparability": {
            "comparable": comparability.get("comparable"),
            "blockingFailedObligations": comparability.get(
                "blockingFailedObligations", []
            ),
        },
        "claimability": {
            "evaluated": claimability.get("evaluated"),
            "claimable": claimability.get("claimable"),
            "reasons": claimability.get("reasons", []),
        },
    }


def build_overall_stats(
    *,
    overall_baseline: list[float],
    overall_comparison: list[float],
    overall_workload_unit_baseline: list[float],
    overall_workload_unit_comparison: list[float],
    report: dict[str, Any],
) -> None:
    if overall_baseline and overall_comparison:
        overall_baseline_stats = format_stats(overall_baseline)
        overall_comparison_stats = format_stats(overall_comparison)
        report["overall"] = {
            "baseline": overall_baseline_stats,
            "comparison": overall_comparison_stats,
            "deltaPercent": {
                "p10Approx": percent_delta(
                    safe_float(overall_baseline_stats["p10Ms"]) or 0.0,
                    safe_float(overall_comparison_stats["p10Ms"]) or 0.0,
                ),
                "p50Approx": percent_delta(
                    safe_float(overall_baseline_stats["p50Ms"]) or 0.0,
                    safe_float(overall_comparison_stats["p50Ms"]) or 0.0,
                ),
                "p95Approx": percent_delta(
                    safe_float(overall_baseline_stats["p95Ms"]) or 0.0,
                    safe_float(overall_comparison_stats["p95Ms"]) or 0.0,
                ),
                "p99Approx": percent_delta(
                    safe_float(overall_baseline_stats["p99Ms"]) or 0.0,
                    safe_float(overall_comparison_stats["p99Ms"]) or 0.0,
                ),
            },
        }
    if overall_workload_unit_baseline and overall_workload_unit_comparison:
        overall_workload_unit_baseline_stats = format_stats(overall_workload_unit_baseline)
        overall_workload_unit_comparison_stats = format_stats(overall_workload_unit_comparison)
        overall_workload_unit_wall = {
            "scope": "timed-command-process-wall",
            "scopeClass": "workload-unit-wall",
            "metric": "elapsedMs",
            "baseline": overall_workload_unit_baseline_stats,
            "comparison": overall_workload_unit_comparison_stats,
            "deltaPercent": delta_percent_from_stats(
                overall_workload_unit_baseline_stats,
                overall_workload_unit_comparison_stats,
            ),
        }
        report["overallWorkloadUnitWall"] = overall_workload_unit_wall
        legacy_overall_workload_unit_wall = dict(overall_workload_unit_wall)
        legacy_overall_workload_unit_wall["deprecatedAliasFor"] = "overallWorkloadUnitWall"
        report["overallHeadlineProcessWall"] = legacy_overall_workload_unit_wall


def build_report_summaries(
    *,
    report: dict[str, Any],
    workloads: list[Workload],
    comparability_failures: list[dict[str, Any]],
    claimability_failures: list[dict[str, Any]],
    claim_workload_hashes: list[str],
    claimability_mode: str,
) -> None:
    obligation_failure_counts: dict[str, int] = {}
    benchmark_class_counts: dict[str, int] = {}
    directional_reason_counts: dict[str, int] = {}
    for workload in workloads:
        benchmark_class_counts[workload.benchmark_class] = (
            benchmark_class_counts.get(workload.benchmark_class, 0) + 1
        )
        if workload.benchmark_class != "directional":
            continue
        directional_reason = workload.directional_reason or "other"
        directional_reason_counts[directional_reason] = (
            directional_reason_counts.get(directional_reason, 0) + 1
        )
    for failure in comparability_failures:
        failed_obligations = failure.get("failedBlockingObligations", [])
        if not isinstance(failed_obligations, list):
            continue
        for obligation_id in failed_obligations:
            if not isinstance(obligation_id, str) or not obligation_id:
                continue
            obligation_failure_counts[obligation_id] = (
                obligation_failure_counts.get(obligation_id, 0) + 1
            )

    report["comparabilitySummary"] = {
        "workloadCount": len(workloads),
        "benchmarkIntent": report.get("benchmarkIntent", "mixed"),
        "benchmarkClassCounts": dict(sorted(benchmark_class_counts.items())),
        "directionalReasonCounts": dict(sorted(directional_reason_counts.items())),
        "nonComparableCount": len(comparability_failures),
        "nonComparableWorkloads": comparability_failures,
        "failedBlockingObligationCounts": dict(sorted(obligation_failure_counts.items())),
    }
    report["comparisonStatus"] = "comparable" if not comparability_failures else "unreliable"
    report["claimabilitySummary"] = {
        "workloadCount": len(workloads),
        "nonClaimableCount": len(claimability_failures),
        "nonClaimableWorkloads": claimability_failures,
    }
    operator_diff_available_count = 0
    operator_diff_diverged_count = 0
    operator_diff_matched_count = 0
    operator_diff_missing_count = 0
    operator_diff_workloads: list[dict[str, Any]] = []
    for workload_entry in report.get("workloads", []):
        if not isinstance(workload_entry, dict):
            continue
        summary = workload_entry.get("operatorDiff")
        if not isinstance(summary, dict):
            continue
        status = str(summary.get("status", ""))
        if summary.get("available") is True:
            operator_diff_available_count += 1
            if status == "diverged":
                operator_diff_diverged_count += 1
            elif status == "matched":
                operator_diff_matched_count += 1
        else:
            operator_diff_missing_count += 1
        operator_diff_workloads.append(
            {
                "workloadId": workload_entry.get("id", "unknown"),
                "status": status,
                "available": summary.get("available") is True,
                "eligibleSamplePairCount": summary.get("eligibleSamplePairCount", 0),
                "comparedSamplePairCount": summary.get("comparedSamplePairCount", 0),
                "firstDivergence": summary.get("firstDivergence"),
            }
        )
    report["operatorDiffSummary"] = {
        "workloadCount": len(workloads),
        "availableCount": operator_diff_available_count,
        "matchedCount": operator_diff_matched_count,
        "divergedCount": operator_diff_diverged_count,
        "missingCount": operator_diff_missing_count,
        "workloads": operator_diff_workloads,
    }
    report["claimWorkloadHashChain"] = {
        "algorithm": "sha256",
        "count": len(claim_workload_hashes),
        "startPreviousHash": "0" * 64,
        "finalHash": claim_workload_hashes[-1] if claim_workload_hashes else "",
    }
    if claimability_mode == "off":
        report["claimStatus"] = "not-evaluated"
    else:
        report["claimStatus"] = "claimable" if not claimability_failures else "diagnostic"


def write_report_and_determine_status(
    *,
    report: dict[str, Any],
    out: Path,
    workspace: Path,
    args: Any,
    comparability_failures: list[dict[str, Any]],
    claimability_failures: list[dict[str, Any]],
    workload_count: int,
) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    run_status = "passed"
    if comparability_failures and args.comparability == "strict":
        run_status = "failed"
    elif args.claimability != "off" and claimability_failures:
        # Preserve non-zero exit for claim gates, but keep manifests explicit
        # that the compare run completed and produced diagnostic evidence.
        run_status = "diagnostic"
    elif comparability_failures and args.comparability == "warn":
        run_status = "diagnostic"
    output_paths.write_run_manifest_for_outputs(
        [out, workspace],
        {
            "runType": "compare_dawn_vs_doe",
            "config": str(Path(args.config)) if args.config else "",
            "fullRun": not args.emit_shell,
            "claimGateRan": False,
            "dropinGateRan": False,
            "reportPath": str(out),
            "workspacePath": str(workspace),
            "status": run_status,
        },
    )
    if args.emit_shell:
        print(json.dumps({"resolvedCommandsOnly": True, "out": str(out)}, indent=2))
        return 0

    if comparability_failures and args.comparability in ("strict", "warn"):
        summary = {
            "out": str(out),
            "workloadCount": workload_count,
            "benchmarkIntent": report.get("benchmarkIntent", "mixed"),
            "comparisonStatus": report["comparisonStatus"],
            "nonComparableCount": len(comparability_failures),
            "nonComparableWorkloads": comparability_failures,
            "claimStatus": report["claimStatus"],
        }
        print(json.dumps(summary, indent=2))
        if args.comparability == "strict":
            return 2
        return 0

    if args.claimability != "off" and claimability_failures:
        summary = {
            "out": str(out),
            "workloadCount": workload_count,
            "benchmarkIntent": report.get("benchmarkIntent", "mixed"),
            "comparisonStatus": report["comparisonStatus"],
            "claimStatus": report["claimStatus"],
            "nonClaimableCount": len(claimability_failures),
            "nonClaimableWorkloads": claimability_failures,
        }
        print(json.dumps(summary, indent=2))
        return 3

    print(
        json.dumps(
            {
                "out": str(out),
                "workloadCount": workload_count,
                "benchmarkIntent": report.get("benchmarkIntent", "mixed"),
                "comparisonStatus": report["comparisonStatus"],
                "claimStatus": report["claimStatus"],
            },
            indent=2,
        )
    )
    return 0


def summarize_operator_diff(
    baseline: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    return operator_diff_mod.summarize_workload_operator_diff(baseline, comparison)
