"""Shared browser runtime-identity reference checks."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any


RUNTIME_IDENTITY_KIND = "browser_runtime_identity"
SMOKE_REPORT_KIND = "chromium-webgpu-playwright-smoke"


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def resolve_repo_path(root: Path, path_text: str) -> Path | None:
    if not safe_repo_path(path_text):
        return None
    resolved = root.joinpath(*PurePosixPath(path_text).parts).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _runtime_identity_fallback(payload: dict[str, Any]) -> bool | None:
    runtime_selection = payload.get("runtimeSelection")
    if runtime_selection is None:
        return False
    if isinstance(runtime_selection, dict) and isinstance(runtime_selection.get("fallbackApplied"), bool):
        return runtime_selection["fallbackApplied"]
    return None


def _smoke_runtime_rows(payload: dict[str, Any]) -> list[tuple[str, bool]]:
    rows: list[tuple[str, bool]] = []
    for mode_result in payload.get("modeResults", []):
        if not isinstance(mode_result, dict):
            continue
        runtime_selection = mode_result.get("runtimeSelection")
        if not isinstance(runtime_selection, dict):
            continue
        selected_runtime = runtime_selection.get("selectedRuntime")
        fallback_applied = runtime_selection.get("fallbackApplied")
        if isinstance(selected_runtime, str) and isinstance(fallback_applied, bool):
            rows.append((selected_runtime, fallback_applied))
    return rows


def _reference_rows(payload: dict[str, Any]) -> tuple[list[tuple[str, bool]], list[dict[str, str]]]:
    if payload.get("artifactKind") == RUNTIME_IDENTITY_KIND:
        selected_runtime = payload.get("selectedRuntime")
        fallback_applied = _runtime_identity_fallback(payload)
        if not isinstance(selected_runtime, str) or fallback_applied is None:
            return [], [
                failure(
                    "invalid_runtime_identity_reference",
                    "runtimeIdentity.runtimeIdentityPath",
                    "runtime identity artifact must expose selectedRuntime and fallback state",
                )
            ]
        return [(selected_runtime, fallback_applied)], []

    if payload.get("reportKind") == SMOKE_REPORT_KIND:
        rows = _smoke_runtime_rows(payload)
        if rows:
            return rows, []
        return [], [
            failure(
                "invalid_runtime_identity_reference",
                "runtimeIdentity.runtimeIdentityPath",
                "smoke report must contain modeResults runtimeSelection rows",
            )
        ]

    return [], [
        failure(
            "invalid_runtime_identity_reference_kind",
            "runtimeIdentity.runtimeIdentityPath",
            "runtimeIdentityPath must point to browser_runtime_identity or browser smoke report",
        )
    ]


def check_runtime_identity_reference(
    payload: dict[str, Any],
    root: Path,
    *,
    path_prefix: str = "runtimeIdentity",
) -> list[dict[str, str]]:
    runtime_identity = payload.get("runtimeIdentity")
    if not isinstance(runtime_identity, dict):
        return [
            failure(
                "missing_runtime_identity",
                path_prefix,
                "artifact must carry runtimeIdentity",
            )
        ]

    selected_runtime = runtime_identity.get("selectedRuntime")
    fallback_applied = runtime_identity.get("fallbackApplied")
    path_text = runtime_identity.get("runtimeIdentityPath")
    failures: list[dict[str, str]] = []
    if not isinstance(selected_runtime, str) or not selected_runtime:
        failures.append(
            failure(
                "missing_runtime_selected_runtime",
                f"{path_prefix}.selectedRuntime",
                "runtimeIdentity.selectedRuntime is required",
            )
        )
    if not isinstance(fallback_applied, bool):
        failures.append(
            failure(
                "missing_runtime_fallback_applied",
                f"{path_prefix}.fallbackApplied",
                "runtimeIdentity.fallbackApplied must be boolean",
            )
        )
    if not isinstance(path_text, str) or not path_text:
        failures.append(
            failure(
                "missing_runtime_identity_path",
                f"{path_prefix}.runtimeIdentityPath",
                "runtime identity path is required",
            )
        )
        return failures
    if failures:
        return failures

    resolved = resolve_repo_path(root, path_text)
    if resolved is None:
        return [
            failure(
                "unsafe_runtime_identity_path",
                f"{path_prefix}.runtimeIdentityPath",
                "runtime identity path must be repo-relative",
            )
        ]
    if not resolved.is_file():
        return [
            failure(
                "missing_runtime_identity_file",
                f"{path_prefix}.runtimeIdentityPath",
                f"runtime identity source not found: {path_text}",
            )
        ]

    try:
        reference = load_json(resolved)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [
            failure(
                "invalid_runtime_identity_reference",
                f"{path_prefix}.runtimeIdentityPath",
                f"runtime identity source is not valid JSON object: {exc}",
            )
        ]

    rows, row_failures = _reference_rows(reference)
    if row_failures:
        return row_failures
    expected = (selected_runtime, fallback_applied)
    if expected not in rows:
        return [
            failure(
                "runtime_identity_reference_mismatch",
                path_prefix,
                "runtimeIdentity selectedRuntime/fallbackApplied must match referenced runtime evidence",
            )
        ]
    return []
