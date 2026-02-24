"""Timing-source selection helpers for compare_dawn_vs_fawn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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


def parse_trace_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            print(f"WARN: invalid trace jsonl row in {path}: {exc}")
            return []
    return rows


def parse_execution_duration_ns_rows(path: Path) -> list[int]:
    rows = parse_trace_rows(path)
    durations: list[int] = []
    for row in rows:
        duration_ns = safe_int(row.get("executionDurationNs"), default=-1)
        if duration_ns >= 0:
            durations.append(duration_ns)
    return durations


def maybe_adjust_timing_for_ignored_first_ops(
    *,
    measured_ms: float,
    measured_source: str,
    trace_jsonl: Path,
    ignore_first_ops: int,
) -> tuple[float, str, dict[str, Any]]:
    if ignore_first_ops <= 0:
        return measured_ms, measured_source, {
            "uploadIgnoreFirstOps": 0,
            "uploadIgnoreFirstApplied": False,
        }

    durations_ns = parse_execution_duration_ns_rows(trace_jsonl)
    if not durations_ns:
        return measured_ms, measured_source, {
            "uploadIgnoreFirstOps": ignore_first_ops,
            "uploadIgnoreFirstApplied": False,
            "uploadIgnoreFirstReason": "trace has no executionDurationNs rows",
        }

    if len(durations_ns) <= ignore_first_ops:
        return measured_ms, measured_source, {
            "uploadIgnoreFirstOps": ignore_first_ops,
            "uploadIgnoreFirstApplied": False,
            "uploadIgnoreFirstReason": (
                "trace row count is not greater than ignore count "
                f"({len(durations_ns)} <= {ignore_first_ops})"
            ),
        }

    adjusted_ns = sum(durations_ns[ignore_first_ops:])
    adjusted_ms = float(adjusted_ns) / 1_000_000.0
    adjusted_source = "fawn-execution-row-total-ns+ignore-first-ops"
    return adjusted_ms, adjusted_source, {
        "uploadIgnoreFirstOps": ignore_first_ops,
        "uploadIgnoreFirstApplied": True,
        "uploadIgnoreFirstBaseTimingSource": measured_source,
        "uploadIgnoreFirstAdjustedTimingSource": "fawn-execution-row-total-ns",
        "uploadRowsTotal": len(durations_ns),
        "uploadRowsIncluded": len(durations_ns) - ignore_first_ops,
        "uploadTimingRawMsBeforeIgnore": measured_ms,
        "uploadTimingRawMsAfterIgnore": adjusted_ms,
    }


def canonical_timing_source(source: str) -> str:
    if not source:
        return ""
    return source.split("+", 1)[0]


def classify_timing_source(source: str) -> str:
    canonical = canonical_timing_source(source)
    if canonical in (
        "fawn-execution-total-ns",
        "fawn-execution-row-total-ns",
        "fawn-execution-dispatch-window-ns",
        "fawn-execution-encode-ns",
        "fawn-execution-gpu-timestamp-ns",
        "dawn-perf-wall-time",
        "dawn-perf-cpu-time",
        "dawn-perf-gpu-time",
        "dawn-perf-wall-ns",
        "fawn-trace-window",
    ):
        return "operation"
    if canonical == "wall-time":
        return "process-wall"
    return "unknown"


def pick_measured_timing_ms(
    wall_ms: float,
    trace_meta: dict[str, Any],
    trace_jsonl: Path,
    required_timing_class: str,
    benchmark_policy: Any,
) -> tuple[float, str, dict[str, Any]]:
    if required_timing_class == "process-wall":
        timing_meta = {
            "source": "wall-time",
            "wallTimeMs": wall_ms,
            "timingSelectionPolicy": "forced-process-wall",
        }
        return wall_ms, "wall-time", timing_meta

    meta_timing_ms = safe_float(trace_meta.get("timingMs"))
    meta_source = trace_meta.get("timingSource")
    if meta_timing_ms is not None and meta_timing_ms >= 0.0:
        source = meta_source if isinstance(meta_source, str) and meta_source else "trace-meta"
        if source == "wall-time":
            timing_meta = {
                "source": "wall-time",
                "traceMetaSource": "wall-time",
                "traceMetaTimingMs": meta_timing_ms,
                "wallTimeMs": wall_ms,
                "timingSelectionPolicy": "outer-process-wall-time",
            }
            return wall_ms, "wall-time", timing_meta
        timing_meta = {
            "source": "trace-meta",
            "traceMetaSource": source,
            "traceMetaTimingMs": meta_timing_ms,
            "wallTimeMs": wall_ms,
        }
        return meta_timing_ms, source, timing_meta

    execution_total_ns = safe_int(trace_meta.get("executionTotalNs"), default=-1)
    execution_encode_total_ns = safe_int(trace_meta.get("executionEncodeTotalNs"), default=-1)
    execution_submit_wait_total_ns = safe_int(
        trace_meta.get("executionSubmitWaitTotalNs"), default=-1
    )
    execution_dispatch_count = safe_int(trace_meta.get("executionDispatchCount"), default=0)
    execution_row_count = safe_int(trace_meta.get("executionRowCount"), default=0)
    execution_success_count = safe_int(trace_meta.get("executionSuccessCount"), default=0)

    gpu_timestamp_total_ns = safe_int(
        trace_meta.get("executionGpuTimestampTotalNs"), default=-1
    )
    if gpu_timestamp_total_ns > 0:
        measured_ms = float(gpu_timestamp_total_ns) / 1_000_000.0
        timing_meta = {
            "source": "trace-meta",
            "traceMetaSource": "fawn-execution-gpu-timestamp-ns",
            "traceMetaTimingMs": measured_ms,
            "executionGpuTimestampTotalNs": gpu_timestamp_total_ns,
            "executionDispatchCount": execution_dispatch_count,
            "wallTimeMs": wall_ms,
        }
        return measured_ms, "fawn-execution-gpu-timestamp-ns", timing_meta

    has_execution_evidence = (
        execution_dispatch_count > 0
        or execution_row_count > 0
        or execution_success_count > 0
    )
    dispatch_window_ns = -1
    dispatch_window_rejected: dict[str, Any] | None = None
    if execution_encode_total_ns >= 0 and execution_submit_wait_total_ns >= 0:
        dispatch_window_ns = execution_encode_total_ns + execution_submit_wait_total_ns
        if dispatch_window_ns > 0 and has_execution_evidence:
            if (
                execution_dispatch_count == 0
                and execution_encode_total_ns == 0
                and execution_total_ns > 0
            ):
                coverage_percent = (
                    float(dispatch_window_ns) / float(execution_total_ns)
                ) * 100.0
                if (
                    dispatch_window_ns
                    < benchmark_policy.min_dispatch_window_ns_without_encode
                    and coverage_percent
                    < benchmark_policy.min_dispatch_window_coverage_percent_without_encode
                ):
                    dispatch_window_rejected = {
                        "reason": "dispatch-window-too-small-without-encode",
                        "dispatchWindowNs": dispatch_window_ns,
                        "dispatchWindowCoveragePercentOfExecutionTotal": coverage_percent,
                        "minDispatchWindowNs": benchmark_policy.min_dispatch_window_ns_without_encode,
                        "minDispatchWindowCoveragePercentOfExecutionTotal": benchmark_policy.min_dispatch_window_coverage_percent_without_encode,
                    }
                else:
                    measured_ms = float(dispatch_window_ns) / 1_000_000.0
                    timing_meta = {
                        "source": "trace-meta",
                        "traceMetaSource": "fawn-execution-dispatch-window-ns",
                        "traceMetaTimingMs": measured_ms,
                        "executionEncodeTotalNs": execution_encode_total_ns,
                        "executionSubmitWaitTotalNs": execution_submit_wait_total_ns,
                        "executionDispatchCount": execution_dispatch_count,
                        "executionRowCount": execution_row_count,
                        "executionSuccessCount": execution_success_count,
                        "wallTimeMs": wall_ms,
                    }
                    return measured_ms, "fawn-execution-dispatch-window-ns", timing_meta
            else:
                measured_ms = float(dispatch_window_ns) / 1_000_000.0
                timing_meta = {
                    "source": "trace-meta",
                    "traceMetaSource": "fawn-execution-dispatch-window-ns",
                    "traceMetaTimingMs": measured_ms,
                    "executionEncodeTotalNs": execution_encode_total_ns,
                    "executionSubmitWaitTotalNs": execution_submit_wait_total_ns,
                    "executionDispatchCount": execution_dispatch_count,
                    "executionRowCount": execution_row_count,
                    "executionSuccessCount": execution_success_count,
                    "wallTimeMs": wall_ms,
                }
                return measured_ms, "fawn-execution-dispatch-window-ns", timing_meta

    if execution_total_ns > 0 and has_execution_evidence:
        measured_ms = float(execution_total_ns) / 1_000_000.0
        timing_meta = {
            "source": "trace-meta",
            "traceMetaSource": "fawn-execution-total-ns",
            "traceMetaTimingMs": measured_ms,
            "executionDispatchCount": execution_dispatch_count,
            "executionRowCount": execution_row_count,
            "executionSuccessCount": execution_success_count,
            "wallTimeMs": wall_ms,
        }
        if dispatch_window_rejected is not None:
            timing_meta["dispatchWindowSelectionRejected"] = dispatch_window_rejected
        return measured_ms, "fawn-execution-total-ns", timing_meta

    trace_rows = parse_trace_rows(trace_jsonl)
    timing_meta: dict[str, Any] = {
        "source": "wall-time",
        "wallTimeMs": wall_ms,
        "traceRows": len(trace_rows),
    }
    if not trace_rows:
        return wall_ms, "wall-time", timing_meta

    timestamps: list[int] = []
    for row in trace_rows:
        ts = row.get("timestampMonoNs")
        if isinstance(ts, int):
            timestamps.append(ts)
    if len(timestamps) < 2:
        timing_meta["traceRows"] = len(timestamps)
        return wall_ms, "wall-time", timing_meta

    first = min(timestamps)
    last = max(timestamps)
    measured_ms = float(last - first) / 1_000_000.0
    if measured_ms < 0:
        timing_meta["traceRows"] = len(timestamps)
        return wall_ms, "wall-time", timing_meta

    timing_meta.update(
        {
            "source": "fawn-trace-window",
            "traceWindowStartMonoNs": first,
            "traceWindowEndMonoNs": last,
            "traceRows": len(timestamps),
            "rowCount": safe_int(trace_meta.get("rowCount"), default=0),
        }
    )
    return measured_ms, "fawn-trace-window", timing_meta
