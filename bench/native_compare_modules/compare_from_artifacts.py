"""Post-hoc comparison from independent run artifacts.

Maps product-based run artifacts to the existing battle-tested comparability,
claimability, and timing interpretation functions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from native_compare_modules.config_support import Workload
from native_compare_modules.report_assembly import (
    build_claim_workload_context,
    build_overall_stats,
    build_report_header_from_contracts,
    build_report_summaries,
    build_workload_report_entry,
    compute_workload_delta,
    summarize_operator_diff,
)
from native_compare_modules.run_artifact import load_run_artifact
from native_compare_modules.runner import (
    collect_trace_meta_hashes,
    file_sha256,
    json_sha256,
    safe_float,
)

COMPARE_REPORT_SCHEMA_VERSION = 6


def artifact_to_run_view(artifact: dict[str, Any]) -> dict[str, Any]:
    """Project a run artifact back to the legacy per-side run result shape."""
    run_view = {
        "commandSamples": artifact.get("commandSamples", []),
        "stats": artifact.get("stats", {}),
        "timingsMs": artifact.get("timingsMs", []),
        "timingSources": artifact.get("timingSources", []),
        "timingClasses": artifact.get("timingClasses", []),
        "lastMeta": artifact.get("lastMeta", {}),
        "resourceStats": artifact.get("resourceStats", {}),
        "timingMetricsRawStatsMs": artifact.get("timingMetricsRawStatsMs", {}),
        "timingMetricsNormalizedStatsMs": artifact.get(
            "timingMetricsNormalizedStatsMs",
            {},
        ),
    }
    for key in (
        "startupBaselineStatsMs",
        "startupCorrectionMethod",
        "startupCorrectedStatsMs",
    ):
        if key in artifact:
            run_view[key] = artifact[key]
    return run_view


def group_run_artifacts_by_workload(
    artifacts: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for artifact in artifacts:
        workload_id = str(artifact.get("workload", {}).get("id", "")).strip()
        product = str(artifact.get("product", "")).strip()
        if not workload_id or not product:
            raise ValueError("run artifact missing workload.id or product")
        grouped.setdefault(workload_id, {})
        if product in grouped[workload_id]:
            raise ValueError(
                f"duplicate run artifact for workload {workload_id!r} "
                f"and product {product!r}"
            )
        grouped[workload_id][product] = artifact
    return grouped


def _required_contract_ref(
    artifact: dict[str, Any],
    *,
    field_name: str,
) -> dict[str, str]:
    ref = artifact.get(field_name)
    if artifact.get("schemaVersion") != 2:
        raise ValueError(
            "artifact-first comparison requires run artifacts with "
            "schemaVersion=2; rerun the isolated benchmark with the current runner"
        )
    if not isinstance(ref, dict):
        raise ValueError(f"run artifact missing {field_name} contract metadata")
    path = str(ref.get("path", "")).strip()
    sha256 = str(ref.get("sha256", "")).strip()
    if not path or not sha256:
        raise ValueError(
            f"run artifact has incomplete {field_name} contract metadata: "
            f"path={path!r} sha256={sha256!r}"
        )
    return {"path": path, "sha256": sha256}


def workload_from_artifact_pair(
    *,
    baseline_artifact: dict[str, Any],
    comparison_artifact: dict[str, Any],
) -> Workload:
    baseline_workload = baseline_artifact.get("workload", {})
    comparison_workload = comparison_artifact.get("workload", {})
    baseline_id = str(baseline_workload.get("id", "")).strip()
    comparison_id = str(comparison_workload.get("id", "")).strip()
    if not baseline_id or baseline_id != comparison_id:
        raise ValueError(
            "post-hoc comparison requires matching workload ids: "
            f"{baseline_id!r} vs {comparison_id!r}"
        )
    baseline_contract = _required_contract_ref(
        baseline_artifact,
        field_name="workloadContract",
    )
    comparison_contract = _required_contract_ref(
        comparison_artifact,
        field_name="workloadContract",
    )
    if baseline_contract["sha256"] != comparison_contract["sha256"]:
        raise ValueError(
            f"workload contract mismatch for {baseline_id!r}: "
            f"{baseline_contract['sha256']} vs {comparison_contract['sha256']}"
        )
    baseline_policy = baseline_artifact.get("benchmarkPolicy")
    comparison_policy = comparison_artifact.get("benchmarkPolicy")
    if (
        isinstance(baseline_policy, dict)
        and isinstance(comparison_policy, dict)
        and str(baseline_policy.get("sha256", "")).strip()
        and str(comparison_policy.get("sha256", "")).strip()
        and baseline_policy.get("sha256") != comparison_policy.get("sha256")
    ):
        raise ValueError(
            f"benchmark policy mismatch for {baseline_id!r}: "
            f"{baseline_policy.get('sha256')} vs {comparison_policy.get('sha256')}"
        )
    baseline_params = baseline_artifact.get("runParameters", {})
    comparison_params = comparison_artifact.get("runParameters", {})
    baseline_note = str(baseline_params.get("timingNormalizationNote", "")).strip()
    comparison_note = str(
        comparison_params.get("timingNormalizationNote", "")
    ).strip()
    if baseline_note and comparison_note and baseline_note != comparison_note:
        raise ValueError(
            f"timing normalization note mismatch for {baseline_id!r}: "
            f"{baseline_note!r} vs {comparison_note!r}"
        )
    candidate = baseline_workload.get("comparabilityCandidate", {})
    return Workload(
        id=baseline_id,
        name=str(baseline_workload.get("name", "")),
        description=str(baseline_workload.get("description", "")),
        domain=str(baseline_workload.get("domain", "")),
        comparability_notes=str(
            baseline_workload.get("comparabilityNotes", "")
        ),
        commands_path=str(baseline_workload.get("commandsPath", "")),
        quirks_path=str(baseline_workload.get("quirksPath", "")),
        vendor=str(baseline_workload.get("vendor", "")),
        api=str(baseline_workload.get("api", "")),
        family=str(baseline_workload.get("family", "")),
        driver=str(baseline_workload.get("driver", "")),
        extra_args=[],
        baseline_command_repeat=int(baseline_params.get("commandRepeat", 1)),
        comparison_command_repeat=int(comparison_params.get("commandRepeat", 1)),
        baseline_ignore_first_ops=int(baseline_params.get("ignoreFirstOps", 0)),
        comparison_ignore_first_ops=int(comparison_params.get("ignoreFirstOps", 0)),
        baseline_upload_buffer_usage=str(
            baseline_params.get("uploadBufferUsage", "copy-dst-copy-src")
        ),
        comparison_upload_buffer_usage=str(
            comparison_params.get("uploadBufferUsage", "copy-dst-copy-src")
        ),
        baseline_upload_submit_every=int(baseline_params.get("uploadSubmitEvery", 1)),
        comparison_upload_submit_every=int(
            comparison_params.get("uploadSubmitEvery", 1)
        ),
        dawn_filter="",
        comparable=bool(baseline_workload.get("comparable", False)),
        benchmark_class=str(baseline_workload.get("benchmarkClass", "")),
        directional_reason=str(
            baseline_workload.get("directionalReason", "")
        ),
        allow_baseline_no_execution=bool(
            baseline_params.get("allowNoExecution", False)
        ),
        include_by_default=bool(
            baseline_workload.get("includeByDefault", True)
        ),
        baseline_timing_divisor=float(baseline_params.get("timingDivisor", 1.0)),
        comparison_timing_divisor=float(
            comparison_params.get("timingDivisor", 1.0)
        ),
        timing_normalization_note=baseline_note or comparison_note,
        async_diagnostics_mode=str(
            baseline_workload.get("asyncDiagnosticsMode", "")
        ),
        comparability_candidate=bool(candidate.get("enabled", False)),
        comparability_candidate_tier=str(candidate.get("tier", "")),
        comparability_candidate_notes=str(candidate.get("notes", "")),
        path_asymmetry=bool(baseline_workload.get("pathAsymmetry", False)),
        path_asymmetry_note=str(
            baseline_workload.get("pathAsymmetryNote", "")
        ),
        strict_normalization_unit=str(
            baseline_workload.get("strictNormalizationUnit", "")
        ),
        cohorts=list(baseline_workload.get("cohorts", [])),
        claim_eligible=bool(baseline_workload.get("claimEligible", True)),
    )


def build_legacy_compare_report_from_artifacts(
    *,
    args: Any,
    artifacts: list[dict[str, Any]],
    baseline_product: str,
    comparison_product: str,
    benchmark_policy: Any,
    output_timestamp: str,
    out: Path,
    workspace: Path,
    run_artifact_paths: list[str],
    workloads: list[Workload] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    grouped = group_run_artifacts_by_workload(artifacts)
    if not artifacts:
        raise ValueError("no run artifacts were provided for post-hoc comparison")
    if workloads is None:
        workloads = []
        for workload_id in sorted(grouped):
            workload_group = grouped[workload_id]
            if baseline_product not in workload_group or comparison_product not in workload_group:
                raise ValueError(
                    f"missing product artifacts for workload {workload_id!r}: "
                    f"expected {baseline_product!r} and {comparison_product!r}, "
                    f"found {sorted(workload_group)}"
                )
            workloads.append(
                workload_from_artifact_pair(
                    baseline_artifact=workload_group[baseline_product],
                    comparison_artifact=workload_group[comparison_product],
                )
            )
    first_group = grouped[workloads[0].id]
    first_baseline_artifact = first_group[baseline_product]
    workload_contract = _required_contract_ref(
        first_baseline_artifact,
        field_name="workloadContract",
    )
    benchmark_policy_contract = first_baseline_artifact.get("benchmarkPolicy")
    if not isinstance(benchmark_policy_contract, dict):
        benchmark_policy_contract = {
            "path": benchmark_policy.source_path,
            "schemaVersion": 1,
            "sha256": file_sha256(Path(benchmark_policy.source_path)),
        }
    report = build_report_header_from_contracts(
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
        config_contract=(
            {
                "path": str(Path(args.config).resolve()),
                "sha256": file_sha256(Path(args.config).resolve()),
            }
            if getattr(args, "config", "")
            and Path(args.config).resolve().exists()
            else None
        ),
    )
    report["runArtifactPaths"] = list(run_artifact_paths)

    overall_baseline: list[float] = []
    overall_comparison: list[float] = []
    overall_workload_unit_baseline: list[float] = []
    overall_workload_unit_comparison: list[float] = []
    comparability_failures: list[dict[str, Any]] = []
    claimability_failures: list[dict[str, Any]] = []
    previous_claim_workload_hash = "0" * 64
    claim_workload_hashes: list[str] = []

    for workload in workloads:
        workload_group = grouped.get(workload.id, {})
        if baseline_product not in workload_group or comparison_product not in workload_group:
            raise ValueError(
                f"artifact join missing a required side for workload {workload.id!r}: "
                f"expected {baseline_product!r} and {comparison_product!r}, "
                f"found {sorted(workload_group)}"
            )
        baseline_artifact = workload_group[baseline_product]
        comparison_artifact = workload_group[comparison_product]
        baseline = artifact_to_run_view(baseline_artifact)
        comparison = artifact_to_run_view(comparison_artifact)
        baseline_stats = baseline["stats"]
        comparison_stats = comparison["stats"]
        baseline_timings = baseline.get("timingsMs", [])
        comparison_timings = comparison.get("timingsMs", [])
        if not isinstance(baseline_timings, list):
            baseline_timings = []
        if not isinstance(comparison_timings, list):
            comparison_timings = []
        delta = compute_workload_delta(baseline_stats, comparison_stats)

        import native_compare_modules.comparability_runtime as _cr
        import native_compare_modules.claimability as _cl
        import native_compare_modules.timing_interpretation as _ti

        timing_interpretation = _ti.build_timing_interpretation(
            baseline=baseline,
            comparison=comparison,
        )
        comparability = _cr.compare_assessment(
            workload_id=workload.id,
            workload_comparable=workload.comparable,
            workload_domain=workload.domain,
            workload_path_asymmetry=workload.path_asymmetry,
            workload_path_asymmetry_note=workload.path_asymmetry_note,
            baseline_command_repeat=workload.baseline_command_repeat,
            comparison_command_repeat=workload.comparison_command_repeat,
            baseline=baseline,
            comparison=comparison,
            required_timing_class=args.require_timing_class,
            allow_baseline_no_execution=(
                args.allow_baseline_no_execution or workload.allow_baseline_no_execution
            ),
            resource_probe=args.resource_probe,
            comparability_mode=args.comparability,
            resource_sample_target_count=args.resource_sample_target_count,
        )
        claimability = _cl.assess_claimability(
            mode=args.claimability,
            min_timed_samples=args.claim_min_timed_samples,
            workload=workload,
            baseline=baseline,
            comparison=comparison,
            delta=delta,
            timing_interpretation=timing_interpretation,
            comparability=comparability,
            benchmark_policy=benchmark_policy,
        )
        if not comparability["comparable"]:
            comparability_failures.append(
                {
                    "workloadId": workload.id,
                    "failedBlockingObligations": comparability.get(
                        "blockingFailedObligations",
                        [],
                    ),
                    "reasons": comparability["reasons"],
                }
            )
        if claimability.get("evaluated") is True and not claimability.get(
            "claimable",
            False,
        ):
            claimability_failures.append(
                {
                    "workloadId": workload.id,
                    "reasons": claimability.get("reasons", []),
                }
            )
        if comparability.get("comparable"):
            if baseline_stats["count"] >= 7:
                overall_baseline.extend(
                    [
                        safe_float(value)
                        for value in baseline_timings
                        if safe_float(value) is not None
                    ]
                )
                overall_workload_unit_baseline.extend(
                    _ti.command_sample_field_values_ms(
                        baseline.get("commandSamples", []),
                        "elapsedMs",
                    )
                )
            if comparison_stats["count"] >= 7:
                overall_comparison.extend(
                    [
                        safe_float(value)
                        for value in comparison_timings
                        if safe_float(value) is not None
                    ]
                )
                overall_workload_unit_comparison.extend(
                    _ti.command_sample_field_values_ms(
                        comparison.get("commandSamples", []),
                        "elapsedMs",
                    )
                )
        baseline_trace_meta_hashes = collect_trace_meta_hashes(
            baseline.get("commandSamples", [])
        )
        comparison_trace_meta_hashes = collect_trace_meta_hashes(
            comparison.get("commandSamples", [])
        )
        claim_workload_context = build_claim_workload_context(
            workload=workload,
            report=report,
            baseline_trace_meta_hashes=baseline_trace_meta_hashes,
            comparison_trace_meta_hashes=comparison_trace_meta_hashes,
            delta=delta,
            comparability=comparability,
            claimability=claimability,
        )
        claim_workload_hash = json_sha256(
            {
                "previousHash": previous_claim_workload_hash,
                "context": claim_workload_context,
            }
        )
        report["workloads"].append(
            build_workload_report_entry(
                workload=workload,
                baseline=baseline,
                comparison=comparison,
                delta=delta,
                timing_interpretation=timing_interpretation,
                comparability=comparability,
                claimability=claimability,
                baseline_trace_meta_hashes=baseline_trace_meta_hashes,
                comparison_trace_meta_hashes=comparison_trace_meta_hashes,
                claim_workload_hash=claim_workload_hash,
                previous_claim_workload_hash=previous_claim_workload_hash,
                claim_workload_context=claim_workload_context,
                operator_diff=summarize_operator_diff(baseline, comparison),
            )
        )
        claim_workload_hashes.append(claim_workload_hash)
        previous_claim_workload_hash = claim_workload_hash

    build_overall_stats(
        overall_baseline=overall_baseline,
        overall_comparison=overall_comparison,
        overall_workload_unit_baseline=overall_workload_unit_baseline,
        overall_workload_unit_comparison=overall_workload_unit_comparison,
        report=report,
    )
    build_report_summaries(
        report=report,
        workloads=workloads,
        comparability_failures=comparability_failures,
        claimability_failures=claimability_failures,
        claim_workload_hashes=claim_workload_hashes,
        claimability_mode=args.claimability,
    )
    return report, comparability_failures, claimability_failures


def compare_workload_from_artifacts(
    *,
    baseline: dict[str, Any],
    comparison: dict[str, Any],
    comparability_mode: str = "strict",
    required_timing_class: str = "operation",
    claimability_mode: str = "off",
    claimability_min_timed_samples: int = 0,
    resource_probe: str = "none",
    resource_sample_target_count: int = 0,
    benchmark_policy: Any = None,
) -> dict[str, Any]:
    """Compare two run artifacts for the same workload.

    Returns a per-workload comparison entry with comparability, claimability,
    delta, and timing interpretation.
    """
    # Lazy imports: comparability and comparability_runtime have a circular
    # import at module level.  Import comparability first (matching the
    # existing harness's import order) so the circular chain resolves.
    import native_compare_modules.comparability  # noqa: F401 — must load first
    import native_compare_modules.comparability_runtime as _cr
    import native_compare_modules.claimability as _cl
    import native_compare_modules.timing_interpretation as _ti
    compare_assessment = _cr.compare_assessment
    assess_claimability = _cl.assess_claimability
    delta_percent_from_stats = _ti.delta_percent_from_stats
    build_timing_interpretation = _ti.build_timing_interpretation

    workload = baseline["workload"]
    workload_id = workload["id"]

    b_params = baseline.get("runParameters", {})
    c_params = comparison.get("runParameters", {})

    comparability = compare_assessment(
        workload_id=workload_id,
        workload_comparable=workload.get("comparable", False),
        workload_domain=workload.get("domain", ""),
        workload_path_asymmetry=workload.get("pathAsymmetry", False),
        workload_path_asymmetry_note=workload.get("pathAsymmetryNote", ""),
        baseline_command_repeat=b_params.get("commandRepeat", 1),
        comparison_command_repeat=c_params.get("commandRepeat", 1),
        baseline=baseline,
        comparison=comparison,
        required_timing_class=required_timing_class,
        allow_baseline_no_execution=False,
        resource_probe=resource_probe,
        comparability_mode=comparability_mode,
        resource_sample_target_count=resource_sample_target_count,
    )

    delta = delta_percent_from_stats(
        baseline.get("stats", {}),
        comparison.get("stats", {}),
    )

    timing_interpretation = build_timing_interpretation(
        baseline=baseline,
        comparison=comparison,
    )

    claimability = assess_claimability(
        mode=claimability_mode,
        min_timed_samples=claimability_min_timed_samples,
        workload=_workload_proxy(workload),
        baseline=baseline,
        comparison=comparison,
        delta=delta,
        timing_interpretation=timing_interpretation,
        comparability=comparability,
        benchmark_policy=benchmark_policy,
    )

    return {
        "id": workload_id,
        "name": workload.get("name", ""),
        "description": workload.get("description", ""),
        "domain": workload.get("domain", ""),
        "workloadComparable": workload.get("comparable", False),
        "benchmarkClass": workload.get("benchmarkClass", "directional"),
        "participants": {
            "baseline": {
                "product": baseline["product"],
                "commandSamples": baseline.get("commandSamples", []),
                "stats": baseline.get("stats", {}),
            },
            "comparison": {
                "product": comparison["product"],
                "commandSamples": comparison.get("commandSamples", []),
                "stats": comparison.get("stats", {}),
            },
        },
        "timings": {
            "baseline": baseline.get("timingsMs", []),
            "comparison": comparison.get("timingsMs", []),
        },
        "deltaPercent": delta,
        "comparability": comparability,
        "claimability": claimability,
        "timingInterpretation": timing_interpretation,
    }


def build_compare_report(
    *,
    workload_entries: list[dict[str, Any]],
    baseline_artifact: dict[str, Any],
    comparison_artifact: dict[str, Any],
    comparability_mode: str,
    required_timing_class: str,
    claimability_mode: str,
    claimability_min_timed_samples: int,
    out_path: str = "",
    run_artifact_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble a v6 comparison report from workload entries."""
    baseline_product = baseline_artifact["product"]
    comparison_product = comparison_artifact["product"]

    comparability_failures = [
        {"id": e["id"], "reasons": e["comparability"].get("reasons", [])}
        for e in workload_entries
        if not e["comparability"].get("comparable", False)
    ]
    claimability_failures = [
        {"id": e["id"], "reasons": e["claimability"].get("reasons", [])}
        for e in workload_entries
        if e["claimability"].get("evaluated") and not e["claimability"].get("claimable")
    ]

    report = {
        "schemaVersion": COMPARE_REPORT_SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "outPath": out_path,
        "products": [baseline_product, comparison_product],
        "participants": {
            "baseline": {
                "name": baseline_product,
                "id": baseline_product,
                "product": baseline_product,
                "executorId": baseline_artifact.get("executorId", ""),
                "role": "baseline",
            },
            "comparison": {
                "name": comparison_product,
                "id": comparison_product,
                "product": comparison_product,
                "executorId": comparison_artifact.get("executorId", ""),
                "role": "comparison",
            },
        },
        "runArtifactPaths": run_artifact_paths or [],
        "deltaPercentConvention": {
            "baseline": "baseline",
            "formula": "((comparisonMs / baselineMs) - 1) * 100",
            "positive": "baseline faster",
        },
        "comparabilityPolicy": {
            "mode": comparability_mode,
            "requireTimingClass": required_timing_class,
        },
        "claimabilityPolicy": {
            "mode": claimability_mode,
            "minTimedSamples": claimability_min_timed_samples,
        },
        "workloads": workload_entries,
        "comparabilityFailures": comparability_failures,
        "claimabilityFailures": claimability_failures,
    }
    return report


def write_compare_report(report: dict[str, Any], path: Path) -> Path:
    """Write comparison report to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


class _WorkloadProxy:
    """Minimal proxy to satisfy assess_claimability's workload.domain access."""

    def __init__(self, workload_dict: dict[str, Any]) -> None:
        self.id = workload_dict.get("id", "")
        self.domain = workload_dict.get("domain", "")
        self.comparable = workload_dict.get("comparable", False)
        self.claim_eligible = workload_dict.get("claimEligible", True)
        self.path_asymmetry = workload_dict.get("pathAsymmetry", False)


def _workload_proxy(workload_dict: dict[str, Any]) -> _WorkloadProxy:
    return _WorkloadProxy(workload_dict)
