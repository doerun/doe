"""Timing-interpretation helpers for compare_dawn_vs_doe."""

from __future__ import annotations

from typing import Any

from compare_dawn_vs_doe_modules import reporting as reporting_mod
from compare_dawn_vs_doe_modules import timing_selection as timing_selection_mod


_OPERATION_TOTAL_SOURCES = {
    "doe-execution-total-ns",
    "doe-execution-row-total-ns",
    "doe-execution-row-average-ns",
    "doe-execution-gpu-timestamp-ns",
    "dawn-perf-wall-time",
    "dawn-perf-cpu-time",
    "dawn-perf-gpu-time",
    "dawn-perf-wall-ns",
    "doe-trace-window",
}
_NARROW_OPERATION_SCOPE_BY_SOURCE = {
    "doe-execution-encode-ns": "operation-encode",
    "doe-execution-dispatch-window-ns": "operation-dispatch-window",
}


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def percent_delta(left: float, right: float) -> float:
    if left <= 0.0:
        return 0.0
    return ((right / left) - 1.0) * 100.0


def parse_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            out.append(item)
    return out


def command_sample_field_values_ms(
    command_samples: list[dict[str, Any]],
    field: str,
) -> list[float]:
    values: list[float] = []
    for sample in command_samples:
        if not isinstance(sample, dict):
            continue
        parsed = safe_float(sample.get(field))
        if parsed is None or parsed < 0.0:
            continue
        if field == "elapsedMs":
            command_repeat = safe_float(sample.get("commandRepeat")) or 1.0
            if command_repeat <= 0.0:
                command_repeat = 1.0
            timing_divisor = safe_float(sample.get("timingNormalizationDivisor"))
            if timing_divisor is None or timing_divisor <= 0.0:
                timing_meta = sample.get("timing", {})
                if isinstance(timing_meta, dict):
                    timing_divisor = safe_float(timing_meta.get("timingNormalizationDivisor"))
            if timing_divisor is None or timing_divisor <= 0.0:
                timing_divisor = 1.0
            parsed /= command_repeat * timing_divisor
        values.append(parsed)
    return values


def summarize_command_sample_field_ms(
    command_samples: list[dict[str, Any]],
    field: str,
) -> dict[str, float]:
    return reporting_mod.format_stats(command_sample_field_values_ms(command_samples, field))


def delta_percent_from_stats(
    left_stats: dict[str, Any],
    right_stats: dict[str, Any],
) -> dict[str, float]:
    return {
        "p10Percent": percent_delta(
            safe_float(left_stats.get("p10Ms")) or 0.0,
            safe_float(right_stats.get("p10Ms")) or 0.0,
        ),
        "p50Percent": percent_delta(
            safe_float(left_stats.get("p50Ms")) or 0.0,
            safe_float(right_stats.get("p50Ms")) or 0.0,
        ),
        "p95Percent": percent_delta(
            safe_float(left_stats.get("p95Ms")) or 0.0,
            safe_float(right_stats.get("p95Ms")) or 0.0,
        ),
        "p99Percent": percent_delta(
            safe_float(left_stats.get("p99Ms")) or 0.0,
            safe_float(right_stats.get("p99Ms")) or 0.0,
        ),
        "meanPercent": percent_delta(
            safe_float(left_stats.get("meanMs")) or 0.0,
            safe_float(right_stats.get("meanMs")) or 0.0,
        ),
    }


def _canonical_sources(sources: list[str]) -> list[str]:
    canonical: set[str] = set()
    for source in sources:
        canonical_source = timing_selection_mod.canonical_timing_source(source)
        if canonical_source:
            canonical.add(canonical_source)
    return sorted(canonical)


def _selected_scope(canonical_sources: list[str], timing_classes: list[str]) -> tuple[str, str, bool, str]:
    if canonical_sources and all(source == "wall-time" for source in canonical_sources):
        return (
            "process-wall",
            "process-wall",
            False,
            "Selected timing already measures timed-command process wall.",
        )

    narrow_scopes = {
        _NARROW_OPERATION_SCOPE_BY_SOURCE[source]
        for source in canonical_sources
        if source in _NARROW_OPERATION_SCOPE_BY_SOURCE
    }
    if narrow_scopes and len(narrow_scopes) == len(canonical_sources):
        scope = sorted(narrow_scopes)[0] if len(narrow_scopes) == 1 else "mixed-narrow-operation"
        return (
            scope,
            "narrow-hot-path",
            True,
            "Selected timing isolates a narrow operation hot path and excludes setup, "
            "submit/wait, and process startup. Use headlineProcessWall for end-to-end ranking.",
        )

    if canonical_sources and all(source in _OPERATION_TOTAL_SOURCES for source in canonical_sources):
        return (
            "operation-total",
            "operation-total",
            False,
            "Selected timing measures the comparable operation scope. headlineProcessWall "
            "adds process startup and harness overhead for the timed command.",
        )

    normalized_classes = sorted({value for value in timing_classes if value})
    if normalized_classes == ["process-wall"]:
        return (
            "process-wall",
            "process-wall",
            False,
            "Selected timing already measures timed-command process wall.",
        )
    if normalized_classes == ["operation"]:
        return (
            "operation",
            "operation-scope",
            False,
            "Selected timing measures operation scope, but the exact scope could not be "
            "classified from the timing source list. Inspect the timing sources directly.",
        )

    return (
        "unknown",
        "unknown",
        False,
        "Selected timing scope could not be classified reliably from the timing metadata.",
    )


def build_timing_interpretation(
    *,
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    left_sources = parse_string_list(left.get("timingSources"))
    right_sources = parse_string_list(right.get("timingSources"))
    left_classes = parse_string_list(left.get("timingClasses"))
    right_classes = parse_string_list(right.get("timingClasses"))

    canonical_sources = _canonical_sources(left_sources + right_sources)
    timing_classes = sorted({value for value in left_classes + right_classes if value})
    scope, scope_class, is_narrow, note = _selected_scope(canonical_sources, timing_classes)

    left_headline_stats = summarize_command_sample_field_ms(
        left.get("commandSamples", []),
        "elapsedMs",
    )
    right_headline_stats = summarize_command_sample_field_ms(
        right.get("commandSamples", []),
        "elapsedMs",
    )

    return {
        "selectedTiming": {
            "leftSources": left_sources,
            "rightSources": right_sources,
            "leftClasses": left_classes,
            "rightClasses": right_classes,
            "canonicalSources": canonical_sources,
            "timingClasses": timing_classes,
            "scope": scope,
            "scopeClass": scope_class,
            "isNarrowHotPath": is_narrow,
            "note": note,
        },
        "headlineProcessWall": {
            "metric": "elapsedMs",
            "scope": "timed-command-process-wall",
            "available": (
                int(left_headline_stats.get("count", 0)) > 0
                and int(right_headline_stats.get("count", 0)) > 0
            ),
            "leftStatsMs": left_headline_stats,
            "rightStatsMs": right_headline_stats,
            "deltaPercent": delta_percent_from_stats(left_headline_stats, right_headline_stats),
            "note": (
                "Uses timed command process wall normalized by commandRepeat and "
                "timingNormalizationDivisor. This is the end-to-end ranking view for one "
                "comparable workload unit."
            ),
        },
    }
