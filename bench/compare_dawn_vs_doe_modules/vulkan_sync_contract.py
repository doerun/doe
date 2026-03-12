"""Vulkan synchronization contract helpers."""

from __future__ import annotations

from typing import Any

from compare_dawn_vs_doe_modules.reporting import safe_int, valid_sync_mode
from compare_dawn_vs_doe_modules.timing_selection import (
    canonical_timing_source,
    classify_timing_source,
)


def evaluate_sync_meta(
    sample: dict[str, Any],
    expected_sync_mode: str,
    *,
    required_timing_class: str = "any",
    require_upload_ignore_first_source: str = "",
) -> list[str]:
    errors: list[str] = []
    trace_meta = sample.get("traceMeta", {})
    if not isinstance(trace_meta, dict):
        errors.append("traceMeta missing/invalid")
        return errors

    sync_mode = trace_meta.get("queueSyncMode")
    if not valid_sync_mode(sync_mode):
        errors.append("queueSyncMode missing/invalid")
        return errors
    if expected_sync_mode != "either" and sync_mode != expected_sync_mode:
        errors.append(
            f"queueSyncMode mismatch: expected {expected_sync_mode}, got {sync_mode}"
        )

    success = safe_int(trace_meta.get("executionSuccessCount"), default=-1)
    error_count = safe_int(trace_meta.get("executionErrorCount"), default=-1)
    row_count = safe_int(trace_meta.get("executionRowCount"), default=-1)
    skipped_count = safe_int(trace_meta.get("executionSkippedCount"), default=-1)
    unsupported_count = safe_int(trace_meta.get("executionUnsupportedCount"), default=-1)
    total_ns = safe_int(trace_meta.get("executionTotalNs"), default=-1)

    if success < 0:
        errors.append("executionSuccessCount missing/invalid")
    if error_count < 0:
        errors.append("executionErrorCount missing/invalid")
    if row_count < 0:
        errors.append("executionRowCount missing/invalid")
    if skipped_count < 0:
        errors.append("executionSkippedCount missing/invalid")
    if unsupported_count < 0:
        errors.append("executionUnsupportedCount missing/invalid")
    if total_ns < 0:
        errors.append("executionTotalNs missing/invalid")

    if (
        row_count >= 0
        and success >= 0
        and error_count >= 0
        and skipped_count >= 0
        and unsupported_count >= 0
    ):
        if success == 0 and error_count == 0 and skipped_count == 0 and unsupported_count == 0:
            errors.append("no execution outcome recorded in traceMeta")
        if success > row_count:
            errors.append("executionSuccessCount exceeds executionRowCount")

    timing_source_raw = sample.get("timingSource")
    if isinstance(timing_source_raw, str) and timing_source_raw:
        canonical = canonical_timing_source(timing_source_raw)
        if required_timing_class not in ("any", ""):
            source_class = classify_timing_source(canonical)
            if source_class != "unknown" and source_class != required_timing_class:
                errors.append(
                    f"timingClass mismatch: expected {required_timing_class}, "
                    f"got {source_class} for timingSource={canonical!r}"
                )
            elif source_class == "unknown":
                errors.append(f"unknown timingSource {canonical!r} for contract validation")

    if (
        required_timing_class in {"operation", "process-wall"}
        and require_upload_ignore_first_source
    ):
        timing = sample.get("timing", {})
        if not isinstance(timing, dict):
            errors.append("timing metadata missing/invalid")
            return errors

        ignore_ops = safe_int(timing.get("uploadIgnoreFirstOps"), default=0)
        if row_count >= 0 and ignore_ops > 0 and row_count <= ignore_ops:
            errors.append(
                f"upload ignore-first invalid: row count {row_count} <= ignore count {ignore_ops}"
            )

        if timing.get("uploadIgnoreFirstApplied") is True:
            base_source = str(timing.get("uploadIgnoreFirstBaseTimingSource", ""))
            adjusted_source = str(
                timing.get("uploadIgnoreFirstAdjustedTimingSource", "")
            )
            if not base_source:
                errors.append("uploadIgnoreFirstBaseTimingSource missing while ignore-first is applied")
            if not adjusted_source:
                errors.append("uploadIgnoreFirstAdjustedTimingSource missing while ignore-first is applied")
            else:
                if canonical_timing_source(adjusted_source) != canonical_timing_source(
                    require_upload_ignore_first_source
                ):
                    errors.append(
                        f"upload adjusted ignore-first source mismatch: expected "
                        f"{require_upload_ignore_first_source!r}, got {adjusted_source!r}"
                    )
            if base_source and adjusted_source and canonical_timing_source(
                base_source
            ) != canonical_timing_source(adjusted_source):
                errors.append(
                    "upload ignore-first uses mixed base/adjusted timing sources "
                    f"({base_source!r} != {adjusted_source!r})"
                )

    return errors
