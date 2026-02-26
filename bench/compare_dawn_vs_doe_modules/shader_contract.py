"""Shader artifact contract helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema


def load_schema(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid shader artifact schema: {path}")
    return payload


def validate_manifest(path: Path, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing shader manifest: {path}"]

    payload = json.loads(path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for err in validator.iter_errors(payload):
        location = ".".join(str(part) for part in err.absolute_path) or "<root>"
        errors.append(f"{path}: {location}: {err.message}")
    return errors
