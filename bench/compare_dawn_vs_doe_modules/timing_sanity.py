"""Timing-scope sanity helpers shared by compare and cube reporting."""

from __future__ import annotations

import statistics
from typing import Any

from compare_dawn_vs_doe_modules.timing_selection import canonical_timing_source


OPERATION_TIMING_SOURCES = {
    "doe-execution-row-total-ns",
    "doe-execution-total-ns",
    "doe-execution-encode-ns",
    "doe-execution-dispatch-window-ns",
    "doe-execution-gpu-timestamp-ns",
}


def safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def _raw_operation_total_ms(sample: dict[str, Any]) -> float | None:
    timing = sample.get("timing")
    if not isinstance(timing, dict):
        return None

    source_raw = sample.get("timingSource")
    source = canonical_timing_source(str(source_raw)) if isinstance(source_raw, str) else ""
    if source not in OPERATION_TIMING_SOURCES:
        return None

    if source == "doe-execution-row-total-ns":
        ignored_total_ns = safe_float(timing.get("uploadTimingTotalNsAfterIgnore"))
        if ignored_total_ns is not None and ignored_total_ns > 0.0:
            return ignored_total_ns / 1_000_000.0
        row_total_ns = safe_float(timing.get("executionRowTotalNs"))
        if row_total_ns is not None and row_total_ns > 0.0:
            return row_total_ns / 1_000_000.0

    raw_ms = safe_float(timing.get("timingRawMs"))
    if raw_ms is not None and raw_ms > 0.0:
        return raw_ms

    trace_meta_ms = safe_float(timing.get("traceMetaTimingMs"))
    if trace_meta_ms is not None and trace_meta_ms > 0.0:
        return trace_meta_ms

    return None


def sample_operation_wall_coverage_ratio(sample: dict[str, Any]) -> float | None:
    elapsed_ms = safe_float(sample.get("elapsedMs"))
    if elapsed_ms is None or elapsed_ms <= 0.0:
        return None
    operation_total_ms = _raw_operation_total_ms(sample)
    if operation_total_ms is None or operation_total_ms <= 0.0:
        return None
    return operation_total_ms / elapsed_ms


def median_operation_wall_coverage_ratio(command_samples: list[dict[str, Any]]) -> float | None:
    ratios = [
        ratio
        for ratio in (
            sample_operation_wall_coverage_ratio(sample)
            for sample in command_samples
            if isinstance(sample, dict)
        )
        if ratio is not None
    ]
    if not ratios:
        return None
    return float(statistics.median(ratios))


def assess_operation_scope_claim_sanity(
    *,
    left_command_samples: list[dict[str, Any]],
    right_command_samples: list[dict[str, Any]],
    min_operation_wall_coverage_ratio: float,
    max_operation_wall_coverage_asymmetry_ratio: float,
) -> list[str]:
    left_coverage = median_operation_wall_coverage_ratio(left_command_samples)
    right_coverage = median_operation_wall_coverage_ratio(right_command_samples)
    if left_coverage is None or right_coverage is None:
        return []

    smaller = min(left_coverage, right_coverage)
    larger = max(left_coverage, right_coverage)
    if smaller <= 0.0:
        asymmetry_ratio = float("inf")
    else:
        asymmetry_ratio = larger / smaller

    if (
        smaller < min_operation_wall_coverage_ratio
        and asymmetry_ratio >= max_operation_wall_coverage_asymmetry_ratio
    ):
        return [
            "operation timing coverage is asymmetric versus process wall "
            f"(left median {left_coverage:.6f}, right median {right_coverage:.6f}, "
            f"asymmetry {asymmetry_ratio:.2f}x); treat as non-claimable until timing scope is audited"
        ]

    return []
