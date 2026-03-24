"""Host-plan artifact contract helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


def load_schema(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid host-plan schema: {path}")
    return payload


def artifact_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_artifact(
    path: Path,
    schema: dict[str, Any],
    *,
    expected_hash: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing host-plan artifact: {path}"]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        return [f"{path}: invalid JSON: {exc}"]

    validator = jsonschema.Draft202012Validator(schema)
    for err in validator.iter_errors(payload):
        location = ".".join(str(part) for part in err.absolute_path) or "<root>"
        errors.append(f"{path}: {location}: {err.message}")

    if expected_hash is not None:
        actual_hash = artifact_sha256(path)
        if actual_hash != expected_hash:
            errors.append(
                f"{path}: sha256 mismatch expected={expected_hash} got={actual_hash}"
            )

    return errors
