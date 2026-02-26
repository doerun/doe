"""Metal synchronization contract helpers."""

from __future__ import annotations

from typing import Any


def valid_sync_mode(value: Any) -> bool:
    return isinstance(value, str) and value in {"per-command", "deferred"}


def evaluate_sync_meta(trace_meta: dict[str, Any], expected: str) -> list[str]:
    errors: list[str] = []
    sync_mode = trace_meta.get("queueSyncMode")
    if not valid_sync_mode(sync_mode):
        errors.append("queueSyncMode missing/invalid")
        return errors
    if expected != "either" and sync_mode != expected:
        errors.append(f"queueSyncMode mismatch: expected {expected}, got {sync_mode}")

    success = trace_meta.get("executionSuccessCount")
    if not isinstance(success, int) or success < 0:
        errors.append("executionSuccessCount missing/invalid")

    error_count = trace_meta.get("executionErrorCount")
    if not isinstance(error_count, int) or error_count < 0:
        errors.append("executionErrorCount missing/invalid")

    return errors
