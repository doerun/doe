"""Timing-interpretation helpers for the compare lane."""

from __future__ import annotations

from typing import Any

from native_compare_modules import reporting as reporting_mod
from native_compare_modules import timing_selection as timing_selection_mod
from native_compare_modules.reporting import safe_float


_OPERATION_TOTAL_SOURCES = {
    "doe-execution-total-ns",
    "doe-execution-workload-total-ns",
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
_HOST_OVERHEAD_BUCKETS = (
    ("inputRead", "hostInputReadTotalNs", "Input/config file reads before selected execution timing begins."),
    ("inputParse", "hostInputParseTotalNs", "Command/plan parsing and input decoding before selected execution timing begins."),
    ("workloadPrepare", "hostWorkloadPrepareTotalNs", "Pre-execution workload preparation such as dispatch-context or buffer-spec setup."),
    ("executorInit", "hostExecutorInitTotalNs", "Executor/device/backend initialization outside the selected execution timing."),
    ("uploadPrewarm", "hostUploadPrewarmTotalNs", "Doe upload-path prewarm work outside the selected execution timing."),
    ("kernelPrewarm", "hostKernelPrewarmTotalNs", "Kernel/pipeline prewarm work outside the selected execution timing."),
    ("commandOrchestration", "hostCommandOrchestrationTotalNs", "Command-loop bookkeeping outside traced execution phase timing."),
    ("artifactFinalize", "hostArtifactFinalizeTotalNs", "Post-execution artifact writing/finalization outside the selected execution timing."),
)
WORKLOAD_UNIT_WALL_FIELD = "workloadUnitWall"
LEGACY_WORKLOAD_UNIT_WALL_FIELD = "headlineProcessWall"


def percent_delta(baseline: float, comparison: float) -> float:
    if baseline <= 0.0:
        return 0.0
    return ((comparison / baseline) - 1.0) * 100.0


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


def _sample_normalization_factor(sample: dict[str, Any]) -> float:
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
    return command_repeat * timing_divisor


def _normalized_elapsed_ms(sample: dict[str, Any]) -> float | None:
    elapsed_ms = safe_float(sample.get("elapsedMs"))
    if elapsed_ms is None or elapsed_ms < 0.0:
        return None
    return elapsed_ms / _sample_normalization_factor(sample)


def _normalized_trace_meta_total_ms(sample: dict[str, Any], field: str) -> float | None:
    trace_meta = sample.get("traceMeta", {})
    if not isinstance(trace_meta, dict):
        return None
    raw_ns = safe_float(trace_meta.get(field))
    if raw_ns is None or raw_ns < 0.0:
        return None
    return (raw_ns / reporting_mod.NS_PER_MS) / _sample_normalization_factor(sample)


def trace_meta_field_values_ms(
    command_samples: list[dict[str, Any]],
    field: str,
) -> list[float]:
    values: list[float] = []
    for sample in command_samples:
        if not isinstance(sample, dict):
            continue
        normalized_ms = _normalized_trace_meta_total_ms(sample, field)
        if normalized_ms is None:
            continue
        values.append(normalized_ms)
    return values


def selected_gap_values_ms(command_samples: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for sample in command_samples:
        if not isinstance(sample, dict):
            continue
        elapsed_ms = _normalized_elapsed_ms(sample)
        measured_ms = safe_float(sample.get("measuredMs"))
        if elapsed_ms is None or measured_ms is None:
            continue
        values.append(elapsed_ms - measured_ms)
    return values


def attributed_host_values_ms(command_samples: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for sample in command_samples:
        if not isinstance(sample, dict):
            continue
        sample_total_ms = 0.0
        found = False
        for _, field_name, _ in _HOST_OVERHEAD_BUCKETS:
            field_ms = _normalized_trace_meta_total_ms(sample, field_name)
            if field_ms is None:
                continue
            sample_total_ms += field_ms
            found = True
        if found:
            values.append(sample_total_ms)
    return values


def unattributed_gap_remainder_values_ms(command_samples: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for sample in command_samples:
        if not isinstance(sample, dict):
            continue
        elapsed_ms = _normalized_elapsed_ms(sample)
        measured_ms = safe_float(sample.get("measuredMs"))
        if elapsed_ms is None or measured_ms is None:
            continue
        gap_ms = elapsed_ms - measured_ms
        attributed_ms = 0.0
        for _, field_name, _ in _HOST_OVERHEAD_BUCKETS:
            field_ms = _normalized_trace_meta_total_ms(sample, field_name)
            if field_ms is None:
                continue
            attributed_ms += field_ms
        values.append(gap_ms - attributed_ms)
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
            "submit/wait, and process startup. Use workloadUnitWall for end-to-end ranking.",
        )

    if canonical_sources and all(source in _OPERATION_TOTAL_SOURCES for source in canonical_sources):
        return (
            "operation-total",
            "operation-total",
            False,
            "Selected timing measures the comparable operation scope. workloadUnitWall "
            "adds the full timed workload-unit wall interval for the command the harness ran.",
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


def workload_unit_wall_view(timing_interpretation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(timing_interpretation, dict):
        return {}
    current = timing_interpretation.get(WORKLOAD_UNIT_WALL_FIELD)
    if isinstance(current, dict):
        return current
    legacy = timing_interpretation.get(LEGACY_WORKLOAD_UNIT_WALL_FIELD)
    if isinstance(legacy, dict):
        return legacy
    return {}


def build_host_overhead_breakdown(
    *,
    baseline_command_samples: list[dict[str, Any]],
    comparison_command_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_gap_stats = reporting_mod.format_stats(selected_gap_values_ms(baseline_command_samples))
    comparison_gap_stats = reporting_mod.format_stats(selected_gap_values_ms(comparison_command_samples))
    baseline_attributed_stats = reporting_mod.format_stats(attributed_host_values_ms(baseline_command_samples))
    comparison_attributed_stats = reporting_mod.format_stats(attributed_host_values_ms(comparison_command_samples))
    baseline_remainder_stats = reporting_mod.format_stats(unattributed_gap_remainder_values_ms(baseline_command_samples))
    comparison_remainder_stats = reporting_mod.format_stats(unattributed_gap_remainder_values_ms(comparison_command_samples))

    buckets: dict[str, Any] = {}
    for bucket_id, field_name, note in _HOST_OVERHEAD_BUCKETS:
        baseline_stats = reporting_mod.format_stats(trace_meta_field_values_ms(baseline_command_samples, field_name))
        comparison_stats = reporting_mod.format_stats(trace_meta_field_values_ms(comparison_command_samples, field_name))
        buckets[bucket_id] = {
            "traceMetaField": field_name,
            "baselineStatsMs": baseline_stats,
            "comparisonStatsMs": comparison_stats,
            "deltaPercent": delta_percent_from_stats(baseline_stats, comparison_stats),
            "note": note,
        }

    return {
        "metric": "traceMeta.host*TotalNs",
        "scope": "selected-timing-gap-breakdown",
        "scopeClass": "host-overhead-diagnostic",
        "available": (
            int(baseline_gap_stats.get("count", 0)) > 0
            and int(comparison_gap_stats.get("count", 0)) > 0
        ),
        "selectedGap": {
            "baselineStatsMs": baseline_gap_stats,
            "comparisonStatsMs": comparison_gap_stats,
            "deltaPercent": delta_percent_from_stats(baseline_gap_stats, comparison_gap_stats),
            "note": (
                "The normalized difference between workloadUnitWall and selected timing "
                "for each timed sample."
            ),
        },
        "attributedHostOverhead": {
            "baselineStatsMs": baseline_attributed_stats,
            "comparisonStatsMs": comparison_attributed_stats,
            "deltaPercent": delta_percent_from_stats(baseline_attributed_stats, comparison_attributed_stats),
            "note": (
                "Sum of coarse host-overhead buckets recorded outside the selected "
                "execution timing. These buckets are once-per-sample phase timers, not "
                "per-dispatch probes."
            ),
        },
        "unattributedGapRemainder": {
            "baselineStatsMs": baseline_remainder_stats,
            "comparisonStatsMs": comparison_remainder_stats,
            "deltaPercent": delta_percent_from_stats(baseline_remainder_stats, comparison_remainder_stats),
            "note": (
                "Selected-gap remainder after subtracting the coarse host-overhead "
                "buckets. This typically captures trace-meta emission, process teardown, "
                "and any uninstrumented sample overhead."
            ),
        },
        "buckets": buckets,
        "note": (
            "Coarse host-overhead buckets are recorded around existing once-per-sample "
            "phase boundaries so they explain workloadUnitWall minus selected timing "
            "without inserting hot-path profiling probes."
        ),
    }


def build_timing_interpretation(
    *,
    baseline: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    baseline_sources = parse_string_list(baseline.get("timingSources"))
    comparison_sources = parse_string_list(comparison.get("timingSources"))
    baseline_classes = parse_string_list(baseline.get("timingClasses"))
    comparison_classes = parse_string_list(comparison.get("timingClasses"))

    canonical_sources = _canonical_sources(baseline_sources + comparison_sources)
    timing_classes = sorted({value for value in baseline_classes + comparison_classes if value})
    scope, scope_class, is_narrow, note = _selected_scope(canonical_sources, timing_classes)

    baseline_workload_unit_stats = summarize_command_sample_field_ms(
        baseline.get("commandSamples", []),
        "elapsedMs",
    )
    comparison_workload_unit_stats = summarize_command_sample_field_ms(
        comparison.get("commandSamples", []),
        "elapsedMs",
    )
    workload_unit_wall = {
        "metric": "elapsedMs",
        "scope": "timed-command-process-wall",
        "scopeClass": "workload-unit-wall",
        "available": (
            int(baseline_workload_unit_stats.get("count", 0)) > 0
            and int(comparison_workload_unit_stats.get("count", 0)) > 0
        ),
        "baselineStatsMs": baseline_workload_unit_stats,
        "comparisonStatsMs": comparison_workload_unit_stats,
        "deltaPercent": delta_percent_from_stats(
            baseline_workload_unit_stats,
            comparison_workload_unit_stats,
        ),
        "note": (
            "Uses timed command process wall normalized by commandRepeat and "
            "timingNormalizationDivisor. This is the full timed workload-unit view for one "
            "comparable workload unit, not a warm-session-only metric."
        ),
    }
    legacy_workload_unit_wall = dict(workload_unit_wall)
    legacy_workload_unit_wall["deprecatedAliasFor"] = WORKLOAD_UNIT_WALL_FIELD
    host_overhead_breakdown = build_host_overhead_breakdown(
        baseline_command_samples=baseline.get("commandSamples", []),
        comparison_command_samples=comparison.get("commandSamples", []),
    )

    return {
        "selectedTiming": {
            "baselineSources": baseline_sources,
            "comparisonSources": comparison_sources,
            "baselineClasses": baseline_classes,
            "comparisonClasses": comparison_classes,
            "canonicalSources": canonical_sources,
            "timingClasses": timing_classes,
            "scope": scope,
            "scopeClass": scope_class,
            "isNarrowHotPath": is_narrow,
            "note": note,
        },
        WORKLOAD_UNIT_WALL_FIELD: workload_unit_wall,
        "hostOverheadBreakdown": host_overhead_breakdown,
        LEGACY_WORKLOAD_UNIT_WALL_FIELD: legacy_workload_unit_wall,
    }
