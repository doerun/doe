"""Claimability helpers for compare_dawn_vs_fawn."""

from __future__ import annotations

from typing import Any

from compare_dawn_vs_fawn_modules.timing_selection import canonical_timing_source


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def default_claim_min_timed_samples(
    mode: str,
    benchmark_policy: Any,
) -> int:
    if mode == "local":
        return benchmark_policy.local_claim_min_timed_samples
    if mode == "release":
        return benchmark_policy.release_claim_min_timed_samples
    return 0


def required_positive_percentiles(mode: str) -> list[str]:
    if mode == "release":
        return ["p50Percent", "p95Percent", "p99Percent"]
    if mode == "local":
        return ["p50Percent", "p95Percent"]
    return []


def assess_upload_timing_scope_consistency(
    *,
    side_name: str,
    command_samples: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    canonical_sources = {
        canonical_timing_source(str(sample.get("timingSource", "")))
        for sample in command_samples
        if isinstance(sample.get("timingSource"), str) and str(sample.get("timingSource", ""))
    }
    if len(canonical_sources) > 1:
        reasons.append(
            f"{side_name} upload timings use mixed canonical sources: {sorted(canonical_sources)}"
        )

    for sample in command_samples:
        timing = sample.get("timing", {})
        if not isinstance(timing, dict):
            continue
        ignore_applied = timing.get("uploadIgnoreFirstApplied") is True
        timing_source_raw = sample.get("timingSource")
        timing_source = str(timing_source_raw) if isinstance(timing_source_raw, str) else ""
        canonical = canonical_timing_source(timing_source)
        run_index = safe_int(sample.get("runIndex"), default=-1)
        run_label = f"run {run_index}" if run_index >= 0 else "sample"

        if ignore_applied and canonical != "fawn-execution-row-total-ns":
            reasons.append(
                f"{side_name} {run_label} uses ignore-first with non-row timing source "
                f"({canonical}); require fawn-execution-row-total-ns"
            )
        if "ignore-first-ops" in timing_source and not ignore_applied:
            reasons.append(
                f"{side_name} {run_label} timing source marks ignore-first but uploadIgnoreFirstApplied=false"
            )
    return reasons


def assess_claimability(
    *,
    mode: str,
    min_timed_samples: int,
    workload: Any,
    left: dict[str, Any],
    right: dict[str, Any],
    delta: dict[str, Any],
    comparability: dict[str, Any],
    benchmark_policy: Any,
) -> dict[str, Any]:
    if mode == "off":
        return {
            "mode": "off",
            "evaluated": False,
            "claimable": None,
            "minTimedSamples": 0,
            "requiredPositivePercentiles": [],
            "reasons": [],
        }

    reasons: list[str] = []
    effective_min_samples = (
        min_timed_samples
        if min_timed_samples > 0
        else default_claim_min_timed_samples(mode, benchmark_policy)
    )
    required_percentiles = required_positive_percentiles(mode)

    if not comparability.get("comparable", False):
        reasons.append("workload is non-comparable; reliability claimability requires comparability")

    left_count = safe_int(left.get("stats", {}).get("count"), default=0)
    right_count = safe_int(right.get("stats", {}).get("count"), default=0)
    if left_count < effective_min_samples:
        reasons.append(
            f"left timed sample count {left_count} is below claim floor {effective_min_samples}"
        )
    if right_count < effective_min_samples:
        reasons.append(
            f"right timed sample count {right_count} is below claim floor {effective_min_samples}"
        )

    for percentile_key in required_percentiles:
        value = safe_float(delta.get(percentile_key))
        if value is None:
            reasons.append(f"missing delta percentile {percentile_key}")
            continue
        if value <= 0.0:
            reasons.append(
                f"{percentile_key}={value:.6f} is not positive (positive means left faster)"
            )

    if workload.domain == "upload":
        left_samples = left.get("commandSamples", [])
        right_samples = right.get("commandSamples", [])
        if isinstance(left_samples, list):
            reasons.extend(
                assess_upload_timing_scope_consistency(
                    side_name="left",
                    command_samples=left_samples,
                )
            )
        if isinstance(right_samples, list):
            reasons.extend(
                assess_upload_timing_scope_consistency(
                    side_name="right",
                    command_samples=right_samples,
                )
            )

    return {
        "mode": mode,
        "evaluated": True,
        "claimable": len(reasons) == 0,
        "minTimedSamples": effective_min_samples,
        "requiredPositivePercentiles": required_percentiles,
        "leftTimedSamples": left_count,
        "rightTimedSamples": right_count,
        "reasons": reasons,
    }
