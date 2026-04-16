"""Shared claim-grade gating module for ad-hoc compare scripts.

The canonical `bench/native_compare_modules/claimability.py` applies to the
`bench/cli.py compare` infrastructure (GPU-execution, Dawn-vs-Doe, run receipts).
Ad-hoc compare scripts that emit their own `.claim.json` artifacts --
`compare_doe_vs_tint_compilation.py`, `compare_subgroup_kernels.py`, and
future per-op comparisons -- were each re-implementing the same gate logic
(local=7 samples+p50/p95, release=15 samples+p50/p95/p99). This module
exposes one canonical implementation so all ad-hoc scripts share the same
contract.

CLAUDE.md non-negotiable #10 requires structural-equivalence parity
regardless of domain; this module makes it trivial for a new ad-hoc compare
to adopt that contract without re-deriving it.

Per-script usage:

    from bench.lib.adhoc_claim_gating import (
        ClaimPolicy,
        DeltaPercentiles,
        gate_workload_claim,
        render_claim_policy,
    )

    policy = ClaimPolicy.for_mode("release")
    per_workload = gate_workload_claim(
        shader="atan2-const-eval",
        baseline_sample_count=200,
        comparison_sample_count=200,
        warm_comparison_sample_count=200,
        delta_percent=DeltaPercentiles(p50=+106.49, p95=+46.65, p99=+45.78),
        policy=policy,
    )
    # per_workload["claimable"] -> True; per_workload["reasons"] -> []
"""

from __future__ import annotations

import dataclasses
from typing import Any

CLAIM_REPORT_SCHEMA_VERSION = 1
CLAIM_LOCAL_MIN_SAMPLES = 7
CLAIM_RELEASE_MIN_SAMPLES = 15
CLAIM_TIMER_OVERHEAD_BUDGET_PERCENT = 1.0
CLAIM_POLICY_SOURCE = "config/benchmark-methodology-thresholds.json (claimabilityDefaults)"
DELTA_PERCENT_CONVENTION = (
    "((comparisonNs / baselineNs) - 1) * 100; positive = baseline (Doe) faster"
)


@dataclasses.dataclass(frozen=True)
class ClaimPolicy:
    """Claim-grade policy parameters for a compare run.

    Modes follow the same naming as `config/benchmark-methodology-thresholds.json`:
      * local: >=7 timed samples per side; positive p50 + p95
      * release: >=15 timed samples per side; positive p50 + p95 + p99
    """

    mode: str
    min_timed_samples: int
    required_positive_percentiles: tuple[str, ...]
    timer_overhead_budget_percent: float = CLAIM_TIMER_OVERHEAD_BUDGET_PERCENT
    policy_source: str = CLAIM_POLICY_SOURCE

    @classmethod
    def for_mode(cls, mode: str) -> "ClaimPolicy":
        if mode == "release":
            return cls(
                mode="release",
                min_timed_samples=CLAIM_RELEASE_MIN_SAMPLES,
                required_positive_percentiles=("p50", "p95", "p99"),
            )
        if mode == "local":
            return cls(
                mode="local",
                min_timed_samples=CLAIM_LOCAL_MIN_SAMPLES,
                required_positive_percentiles=("p50", "p95"),
            )
        raise ValueError(f"unknown claim mode: {mode!r}; expected local or release")

    def to_dict(self, *, timer_overhead_p50_ns: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": self.mode,
            "minTimedSamples": self.min_timed_samples,
            "requiredPositivePercentiles": list(self.required_positive_percentiles),
            "timerOverheadBudgetPercent": self.timer_overhead_budget_percent,
            "policySource": self.policy_source,
            "deltaPercentConvention": DELTA_PERCENT_CONVENTION,
        }
        if timer_overhead_p50_ns is not None:
            payload["timerOverheadP50Ns"] = int(timer_overhead_p50_ns)
        return payload


@dataclasses.dataclass(frozen=True)
class DeltaPercentiles:
    """Positive-side-faster delta percentages at each percentile."""

    p50: float | None = None
    p95: float | None = None
    p99: float | None = None

    def get(self, percentile: str) -> float | None:
        if percentile == "p50":
            return self.p50
        if percentile == "p95":
            return self.p95
        if percentile == "p99":
            return self.p99
        return None

    def to_dict(self) -> dict[str, float | None]:
        return {"p50": self.p50, "p95": self.p95, "p99": self.p99}


def gate_workload_claim(
    *,
    shader: str,
    baseline_sample_count: int,
    comparison_sample_count: int,
    delta_percent: DeltaPercentiles,
    policy: ClaimPolicy,
    warm_comparison_sample_count: int | None = None,
    timer_overhead_p50_ns: int | None = None,
    smallest_measurement_p50_ns: int | None = None,
    extra_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply claim-grade gating to a single workload; return workload record.

    The record shape matches the existing ad-hoc compare claim artifacts'
    `workloads[]` entries so existing artifact consumers keep working.
    """
    reasons: list[str] = []

    # Sample-count floor
    if baseline_sample_count < policy.min_timed_samples:
        reasons.append(
            f"baseline sample count {baseline_sample_count} < {policy.mode} "
            f"floor {policy.min_timed_samples}"
        )
    if comparison_sample_count < policy.min_timed_samples:
        reasons.append(
            f"comparison sample count {comparison_sample_count} < {policy.mode} "
            f"floor {policy.min_timed_samples}"
        )
    if warm_comparison_sample_count is not None and warm_comparison_sample_count < policy.min_timed_samples:
        reasons.append(
            f"warm comparison sample count {warm_comparison_sample_count} < {policy.mode} "
            f"floor {policy.min_timed_samples}"
        )

    # Required positive percentiles (e.g. Doe faster at p50, p95, p99)
    for pct in policy.required_positive_percentiles:
        value = delta_percent.get(pct)
        if value is None:
            reasons.append(f"{pct} delta missing")
        elif value <= 0:
            reasons.append(f"{pct} delta {value:+.2f}% not positive")

    # Timer-overhead budget (optional; applied when both values provided)
    if timer_overhead_p50_ns is not None and smallest_measurement_p50_ns:
        if smallest_measurement_p50_ns > 0:
            overhead_percent = (timer_overhead_p50_ns / smallest_measurement_p50_ns) * 100.0
            if overhead_percent > policy.timer_overhead_budget_percent:
                reasons.append(
                    f"timer overhead {timer_overhead_p50_ns}ns is "
                    f"{overhead_percent:.2f}% of smallest p50 "
                    f"(budget {policy.timer_overhead_budget_percent}%)"
                )

    record: dict[str, Any] = {
        "shader": shader,
        "claimable": not reasons,
        "reasons": reasons,
        "requiredPositivePercentiles": list(policy.required_positive_percentiles),
        "deltaPercent": delta_percent.to_dict(),
        "baselineSampleCount": baseline_sample_count,
        "comparisonSampleCount": comparison_sample_count,
    }
    if warm_comparison_sample_count is not None:
        record["warmComparisonSampleCount"] = warm_comparison_sample_count
    if extra_details:
        record.update(extra_details)
    return record


def aggregate_claim_status(workloads: list[dict[str, Any]]) -> tuple[str, bool, list[str]]:
    """Collapse per-workload records into an aggregate (status, pass, reasons) tuple."""
    non_claimable = [w for w in workloads if not w.get("claimable")]
    if non_claimable:
        return (
            "not_claimable",
            False,
            [f"{len(non_claimable)} of {len(workloads)} rows not claimable"],
        )
    return "claimable", True, []
