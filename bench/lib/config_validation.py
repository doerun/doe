"""Shared config-loading helper with JSON Schema validation.

All policy config files loaded in bench tooling should pass through
load_validated_config() so that schema violations surface immediately
instead of trickling through as cryptic KeyError / type mismatches
deep in gate logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema


def _infer_schema_path(config_path: Path) -> Path:
    """Derive the schema path from a config path (foo.json -> foo.schema.json).

    Handles multi-segment basenames like ``claim-cycle.active.json`` by
    stripping the final ``.json`` suffix and appending ``.schema.json``.
    For paths like ``claim-cycle.active.json`` the inferred schema is
    ``claim-cycle.schema.json`` (strip the rightmost dotted segment
    before ``.json`` when it looks like a variant qualifier).
    """
    name = config_path.name
    if not name.endswith(".json"):
        raise ValueError(
            f"cannot infer schema path for {config_path}: file must end with .json"
        )
    # Strip .json, then check for variant qualifiers like ".active", ".release"
    stem = name[: -len(".json")]
    # If stem contains a dot, the last segment may be a variant qualifier --
    # try the base name first (e.g. claim-cycle.active -> claim-cycle)
    if "." in stem:
        base_stem = stem.rsplit(".", 1)[0]
        candidate = config_path.parent / f"{base_stem}.schema.json"
        if candidate.exists():
            return candidate
    # Direct mapping: foo.json -> foo.schema.json
    return config_path.parent / f"{stem}.schema.json"


def load_validated_config(
    config_path: str | Path,
    schema_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load a JSON config file and validate it against its schema.

    Parameters
    ----------
    config_path:
        Path to the JSON config file to load.
    schema_path:
        Optional explicit path to the JSON Schema file. When omitted the
        schema is inferred from *config_path* using the convention
        ``foo.json`` -> ``foo.schema.json``.

    Returns
    -------
    dict[str, Any]
        The validated config payload.

    Raises
    ------
    FileNotFoundError
        When the config or schema file does not exist.
    ValueError
        When the config is not a JSON object.
    jsonschema.ValidationError
        When the config does not conform to the schema.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"config file not found: {config_path}")

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid config: expected JSON object in {config_path}")

    resolved_schema_path = (
        Path(schema_path) if schema_path is not None else _infer_schema_path(config_path)
    )
    if not resolved_schema_path.exists():
        raise FileNotFoundError(
            f"schema file not found: {resolved_schema_path} "
            f"(for config {config_path})"
        )

    schema = json.loads(resolved_schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda e: tuple(str(p) for p in e.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{_format_path(e)}: {e.message}" for e in errors[:5]
        )
        count_note = (
            f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
        )
        raise jsonschema.ValidationError(
            f"config {config_path.name} failed schema validation "
            f"({resolved_schema_path.name}): {details}{count_note}"
        )
    return payload


def _format_path(error: jsonschema.ValidationError) -> str:
    if not error.absolute_path:
        return "<root>"
    return ".".join(str(part) for part in error.absolute_path)
