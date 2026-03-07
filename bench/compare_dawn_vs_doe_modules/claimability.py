"""Claimability helpers for compare_dawn_vs_doe."""

from __future__ import annotations

from typing import Any

from compare_dawn_vs_doe_modules import timing_sanity
from compare_dawn_vs_doe_modules.timing_selection import canonical_timing_source


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

        if ignore_applied and canonical != "doe-execution-row-total-ns":
            reasons.append(
                f"{side_name} {run_label} uses ignore-first with non-row timing source "
                f"({canonical}); require doe-execution-row-total-ns"
            )
        if ignore_applied:
            base_source_raw = timing.get("uploadIgnoreFirstBaseTimingSource")
            adjusted_source_raw = timing.get("uploadIgnoreFirstAdjustedTimingSource")
            base_source = (
                str(base_source_raw) if isinstance(base_source_raw, str) else ""
            )
            adjusted_source = (
                str(adjusted_source_raw) if isinstance(adjusted_source_raw, str) else ""
            )
            canonical_base = canonical_timing_source(base_source)
            canonical_adjusted = canonical_timing_source(adjusted_source)
            if not canonical_base:
                reasons.append(
                    f"{side_name} {run_label} missing uploadIgnoreFirstBaseTimingSource while ignore-first is applied"
                )
            if canonical_adjusted != "doe-execution-row-total-ns":
                reasons.append(
                    f"{side_name} {run_label} uses ignore-first adjusted source "
                    f"({canonical_adjusted}); require doe-execution-row-total-ns"
                )
            if canonical_base and canonical_adjusted and canonical_base != canonical_adjusted:
                reasons.append(
                    f"{side_name} {run_label} uses mixed-scope ignore-first sources "
                    f"(base={canonical_base}, adjusted={canonical_adjusted})"
                )
        if "ignore-first-ops" in timing_source and not ignore_applied:
            reasons.append(
                f"{side_name} {run_label} timing source marks ignore-first but uploadIgnoreFirstApplied=false"
            )
    return reasons


def _median_phase_fractions(
    command_samples: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """Return per-sample phase fractions (setup, encode, submitWait) relative to executionTotal."""
    fractions: dict[str, list[float]] = {"setup": [], "encode": [], "submitWait": []}
    for sample in command_samples:
        if not isinstance(sample, dict):
            continue
        tm = sample.get("traceMeta", {})
        if not isinstance(tm, dict):
            continue
        total = safe_int(tm.get("executionTotalNs"), default=0)
        if total <= 0:
            continue
        setup = safe_int(tm.get("executionSetupTotalNs"), default=0)
        encode = safe_int(tm.get("executionEncodeTotalNs"), default=0)
        submit_wait = safe_int(tm.get("executionSubmitWaitTotalNs"), default=0)
        fractions["setup"].append(setup / total)
        fractions["encode"].append(encode / total)
        fractions["submitWait"].append(submit_wait / total)
    return fractions


# Minimum fraction of executionTotal a phase must represent on one side
# for a zero on the other side to be considered structurally asymmetric.
_PHASE_ASYMMETRY_THRESHOLD = 0.10


def assess_phase_equivalence(
    *,
    left_command_samples: list[dict[str, Any]],
    right_command_samples: list[dict[str, Any]],
) -> list[str]:
    """Reject claims where one side reports zero for a phase the other side spends >10% in."""
    reasons: list[str] = []
    left_fracs = _median_phase_fractions(left_command_samples)
    right_fracs = _median_phase_fractions(right_command_samples)

    phase_labels = {"setup": "executionSetupTotalNs", "encode": "executionEncodeTotalNs", "submitWait": "executionSubmitWaitTotalNs"}
    for phase_key, field_name in phase_labels.items():
        left_vals = left_fracs.get(phase_key, [])
        right_vals = right_fracs.get(phase_key, [])
        if not left_vals or not right_vals:
            continue
        left_vals_sorted = sorted(left_vals)
        right_vals_sorted = sorted(right_vals)
        left_median = left_vals_sorted[len(left_vals_sorted) // 2]
        right_median = right_vals_sorted[len(right_vals_sorted) // 2]

        left_zero = left_median == 0.0
        right_zero = right_median == 0.0
        if left_zero and not right_zero and right_median >= _PHASE_ASYMMETRY_THRESHOLD:
            reasons.append(
                f"phase asymmetry: left reports zero {field_name} but right spends "
                f"{right_median:.1%} of execution in that phase; "
                f"treat as non-claimable until phase equivalence is confirmed"
            )
        elif right_zero and not left_zero and left_median >= _PHASE_ASYMMETRY_THRESHOLD:
            reasons.append(
                f"phase asymmetry: right reports zero {field_name} but left spends "
                f"{left_median:.1%} of execution in that phase; "
                f"treat as non-claimable until phase equivalence is confirmed"
            )
    return reasons


_UPLOAD_SIZE_SUFFIXES = {
    "1kb": 1024,
    "4kb": 4096,
    "16kb": 16384,
    "64kb": 65536,
    "256kb": 262144,
    "1mb": 1048576,
    "4mb": 4194304,
    "16mb": 16777216,
    "64mb": 67108864,
    "256mb": 268435456,
    "1gb": 1073741824,
    "4gb": 4294967296,
    "16gb": 17179869184,
}

# 500 GB/s — above PCIe 5.0 x16 (64 GB/s) and Apple M-series memory
# bandwidth (~400 GB/s peak). Anything above this is not real.
_MAX_PLAUSIBLE_THROUGHPUT_BYTES_PER_SEC = 500_000_000_000


def _parse_upload_bytes_from_id(workload_id: str) -> int | None:
    for suffix, size in _UPLOAD_SIZE_SUFFIXES.items():
        if workload_id.endswith(suffix):
            return size
    return None


def assess_throughput_plausibility(
    *,
    workload_id: str,
    workload_domain: str,
    left_p50_ms: float | None,
    right_p50_ms: float | None,
) -> list[str]:
    """Reject claims where implied throughput exceeds hardware limits."""
    if workload_domain != "upload":
        return []
    upload_bytes = _parse_upload_bytes_from_id(workload_id)
    if upload_bytes is None or upload_bytes == 0:
        return []
    reasons: list[str] = []
    for side_name, p50_ms in [("left", left_p50_ms), ("right", right_p50_ms)]:
        if p50_ms is None or p50_ms <= 0.0:
            continue
        throughput = upload_bytes / (p50_ms / 1000.0)
        if throughput > _MAX_PLAUSIBLE_THROUGHPUT_BYTES_PER_SEC:
            reasons.append(
                f"{side_name} implies {throughput / 1e9:.0f} GB/s throughput for "
                f"{upload_bytes / (1024**2):.0f} MB upload at p50={p50_ms:.4f}ms; "
                f"exceeds plausibility ceiling of "
                f"{_MAX_PLAUSIBLE_THROUGHPUT_BYTES_PER_SEC / 1e9:.0f} GB/s"
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
    timing_interpretation: dict[str, Any],
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

    if getattr(workload, "path_asymmetry", False):
        note = getattr(workload, "path_asymmetry_note", "")
        reason = "workload has pathAsymmetry: left/right use structurally different execution paths"
        if note:
            reason += f" ({note})"
        reasons.append(reason)

    selected_timing = timing_interpretation.get("selectedTiming", {})
    if not isinstance(selected_timing, dict):
        selected_timing = {}
    if selected_timing.get("scopeClass") == "narrow-hot-path":
        reasons.append(
            "selected timing scope is narrow-hot-path; not eligible for end-to-end speed claims"
        )

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

    left_stdev_ms = safe_float(left.get("stats", {}).get("stdevMs"))
    left_samples = left.get("commandSamples", [])
    left_canonical_sources = {
        canonical_timing_source(str(sample.get("timingSource", "")))
        for sample in left_samples
        if isinstance(sample, dict) and isinstance(sample.get("timingSource"), str)
    } if isinstance(left_samples, list) else set()
    if (
        left_count >= effective_min_samples
        and left_stdev_ms is not None
        and left_stdev_ms == 0.0
        and left_canonical_sources
        and left_canonical_sources.issubset(
            {
                "doe-execution-row-total-ns",
                "doe-execution-total-ns",
                "doe-execution-dispatch-window-ns",
                "doe-execution-encode-ns",
            }
        )
    ):
        reasons.append(
            "left timed samples have zero variance across the full claim window; "
            "treat as non-claimable until timing path is proven non-synthetic"
        )

    left_p50_ms = safe_float(left.get("stats", {}).get("p50Ms"))
    right_p50_ms = safe_float(right.get("stats", {}).get("p50Ms"))
    if left_p50_ms is not None and left_p50_ms < 0.0001:
        reasons.append(f"left p50 timing ({left_p50_ms * 1e6:.1f}ns) is below the 100ns measurement noise floor")
    if right_p50_ms is not None and right_p50_ms < 0.0001:
        reasons.append(f"right p50 timing ({right_p50_ms * 1e6:.1f}ns) is below the 100ns measurement noise floor")

    reasons.extend(
        assess_throughput_plausibility(
            workload_id=workload.id,
            workload_domain=workload.domain,
            left_p50_ms=left_p50_ms,
            right_p50_ms=right_p50_ms,
        )
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

    left_samples = left.get("commandSamples", [])
    right_samples = right.get("commandSamples", [])
    if isinstance(left_samples, list) and isinstance(right_samples, list):
        reasons.extend(
            timing_sanity.assess_operation_scope_claim_sanity(
                left_command_samples=left_samples,
                right_command_samples=right_samples,
                min_operation_wall_coverage_ratio=benchmark_policy.min_operation_wall_coverage_ratio,
                max_operation_wall_coverage_asymmetry_ratio=benchmark_policy.max_operation_wall_coverage_asymmetry_ratio,
            )
        )
        reasons.extend(
            assess_phase_equivalence(
                left_command_samples=left_samples,
                right_command_samples=right_samples,
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
