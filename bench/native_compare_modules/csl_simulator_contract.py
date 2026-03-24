"""Helpers for the governed CSL compile/run/parity lane."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def load_schema(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    return payload


def artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def resolve_relative_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def validate_artifact(
    path: Path,
    schema: dict[str, Any],
    *,
    expected_hash: str | None = None,
) -> list[str]:
    if not path.exists():
        return [f"missing artifact: {path}"]

    try:
        payload = load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"{path}: invalid JSON: {exc}"]

    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for err in validator.iter_errors(payload):
        location = ".".join(str(part) for part in err.absolute_path) or "<root>"
        errors.append(f"{path}: {location}: {err.message}")

    if expected_hash is not None:
        actual_hash = artifact_sha256(path)
        if actual_hash != expected_hash:
            errors.append(f"{path}: sha256 mismatch expected={expected_hash} got={actual_hash}")

    return errors


def evaluate_trace_parity(trace_payload: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_count = expected.get("compiledTargetCount")
    if expected_count is not None and trace_payload.get("compiledTargetCount") != expected_count:
        errors.append(
            "compiledTargetCount mismatch "
            f"expected={expected_count} got={trace_payload.get('compiledTargetCount')}"
        )

    for field in ("prefillLaunchCount", "decodeLaunchCount"):
        expected_value = expected.get(field)
        if expected_value is not None and trace_payload.get(field) != expected_value:
            errors.append(f"{field} mismatch expected={expected_value} got={trace_payload.get(field)}")

    expected_grid = expected.get("peGrid")
    actual_grid = trace_payload.get("peGrid")
    if isinstance(expected_grid, dict):
        if not isinstance(actual_grid, dict):
            errors.append("peGrid missing/invalid in trace payload")
        else:
            for axis in ("width", "height"):
                if expected_grid.get(axis) != actual_grid.get(axis):
                    errors.append(
                        f"peGrid.{axis} mismatch expected={expected_grid.get(axis)} got={actual_grid.get(axis)}"
                    )

    return errors
