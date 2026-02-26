"""Backend contract helpers for Dawn-vs-Doe compare reports."""

from __future__ import annotations

from typing import Any

REQUIRED_BACKEND_KEYS = (
    "backendId",
    "backendSelectionReason",
    "fallbackUsed",
    "selectionPolicyHash",
)


def trace_meta_backend_fields(trace_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "backendId": trace_meta.get("backendId"),
        "backendSelectionReason": trace_meta.get("backendSelectionReason"),
        "fallbackUsed": trace_meta.get("fallbackUsed"),
        "selectionPolicyHash": trace_meta.get("selectionPolicyHash"),
    }


def is_backend_telemetry_present(trace_meta: dict[str, Any]) -> bool:
    return all(key in trace_meta for key in REQUIRED_BACKEND_KEYS)


def backend_telemetry_errors(trace_meta: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    backend_id = trace_meta.get("backendId")
    if not isinstance(backend_id, str) or not backend_id:
        errors.append("backendId missing/invalid")

    reason = trace_meta.get("backendSelectionReason")
    if not isinstance(reason, str) or not reason:
        errors.append("backendSelectionReason missing/invalid")

    fallback_used = trace_meta.get("fallbackUsed")
    if not isinstance(fallback_used, bool):
        errors.append("fallbackUsed missing/invalid")

    policy_hash = trace_meta.get("selectionPolicyHash")
    if not isinstance(policy_hash, str) or not policy_hash:
        errors.append("selectionPolicyHash missing/invalid")

    return errors
