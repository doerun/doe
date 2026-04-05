"""Post-hoc comparison from independent run artifacts.

Maps product-based run artifacts to the existing battle-tested comparability,
claimability, and timing interpretation functions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from native_compare_modules.run_artifact import load_run_artifact

COMPARE_REPORT_SCHEMA_VERSION = 6


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
        left_command_repeat=b_params.get("commandRepeat", 1),
        right_command_repeat=c_params.get("commandRepeat", 1),
        left=baseline,
        right=comparison,
        required_timing_class=required_timing_class,
        allow_left_no_execution=False,
        resource_probe=resource_probe,
        comparability_mode=comparability_mode,
        resource_sample_target_count=resource_sample_target_count,
    )

    delta = delta_percent_from_stats(
        baseline.get("stats", {}),
        comparison.get("stats", {}),
    )

    timing_interpretation = build_timing_interpretation(
        left=baseline,
        right=comparison,
    )

    claimability = assess_claimability(
        mode=claimability_mode,
        min_timed_samples=claimability_min_timed_samples,
        workload=_workload_proxy(workload),
        left=baseline,
        right=comparison,
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
            baseline["product"]: {
                "commandSamples": baseline.get("commandSamples", []),
                "stats": baseline.get("stats", {}),
            },
            comparison["product"]: {
                "commandSamples": comparison.get("commandSamples", []),
                "stats": comparison.get("stats", {}),
            },
        },
        # v5 backward compatibility aliases
        "left": {
            "commandSamples": baseline.get("commandSamples", []),
            "stats": baseline.get("stats", {}),
        },
        "right": {
            "commandSamples": comparison.get("commandSamples", []),
            "stats": comparison.get("stats", {}),
        },
        "timings": {
            baseline["product"]: baseline.get("timingsMs", []),
            comparison["product"]: comparison.get("timingsMs", []),
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
            baseline_product: {
                "product": baseline_product,
                "executorId": baseline_artifact.get("executorId", ""),
                "role": "baseline",
            },
            comparison_product: {
                "product": comparison_product,
                "executorId": comparison_artifact.get("executorId", ""),
                "role": "comparison",
            },
            # v5 backward compatibility
            "left": {
                "name": baseline_product,
                "id": baseline_product,
                "role": "baseline",
            },
            "right": {
                "name": comparison_product,
                "id": comparison_product,
                "role": "comparison",
            },
        },
        "runArtifactPaths": run_artifact_paths or [],
        "deltaPercentConvention": {
            "baseline": baseline_product,
            "formula": "((rightMs / leftMs) - 1) * 100",
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
