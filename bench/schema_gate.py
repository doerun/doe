#!/usr/bin/env python3
"""Blocking schema gate for config/data contracts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema


@dataclass(frozen=True)
class ValidationTarget:
    schema_rel: str
    data_rel: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="",
        help="Repository root. Auto-detected when omitted.",
    )
    return parser.parse_args()


def detect_repo_root(explicit_root: str) -> Path:
    if explicit_root:
        root = Path(explicit_root)
        if not root.exists():
            raise ValueError(f"invalid --root path: {root}")
        return root.resolve()

    cwd = Path.cwd()
    direct_root = cwd
    nested_root = cwd / "fawn"

    if (direct_root / "config").is_dir() and (direct_root / "bench").is_dir():
        return direct_root.resolve()
    if (nested_root / "config").is_dir() and (nested_root / "bench").is_dir():
        return nested_root.resolve()

    raise ValueError(
        "unable to auto-detect repository root; pass --root with a path containing config/ and bench/"
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def format_error_path(error: jsonschema.ValidationError) -> str:
    if not error.absolute_path:
        return "<root>"
    return ".".join(str(part) for part in error.absolute_path)


def validate_target(root: Path, target: ValidationTarget) -> list[str]:
    schema_path = root / target.schema_rel
    data_path = root / target.data_rel
    failures: list[str] = []

    if not schema_path.exists():
        failures.append(f"missing schema: {target.schema_rel}")
        return failures
    if not data_path.exists():
        failures.append(f"missing data: {target.data_rel}")
        return failures

    try:
        schema_payload = load_json(schema_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        failures.append(f"{target.schema_rel}: schema parse failed: {exc}")
        return failures
    try:
        data_payload = load_json(data_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        failures.append(f"{target.data_rel}: data parse failed: {exc}")
        return failures

    try:
        validator = jsonschema.Draft202012Validator(schema_payload)
    except jsonschema.SchemaError as exc:
        failures.append(f"{target.schema_rel}: invalid schema: {exc.message}")
        return failures

    payloads: list[tuple[int | None, Any]]
    if isinstance(data_payload, list):
        payloads = list(enumerate(data_payload))
    else:
        payloads = [(None, data_payload)]

    for entry_idx, payload in payloads:
        errors = sorted(
            validator.iter_errors(payload),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
        for err in errors:
            location = format_error_path(err)
            if entry_idx is not None:
                if location == "<root>":
                    location = f"[{entry_idx}]"
                else:
                    location = f"[{entry_idx}].{location}"
            failures.append(f"{target.data_rel}: {location}: {err.message}")
    return failures


def load_schema_target_registry(root: Path) -> list[ValidationTarget]:
    registry_path = root / "config" / "schema-targets.json"
    if not registry_path.exists():
        raise ValueError(f"missing schema target registry: {registry_path}")
    registry_payload = load_json(registry_path)

    schema_path = root / "config" / "schema-targets.schema.json"
    if not schema_path.exists():
        raise ValueError(f"missing schema target registry schema: {schema_path}")
    schema_payload = load_json(schema_path)
    registry_validator = jsonschema.Draft202012Validator(schema_payload)

    registry_errors = sorted(
        registry_validator.iter_errors(registry_payload),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if registry_errors:
        messages = [f"{format_error_path(error)}: {error.message}" for error in registry_errors]
        raise ValueError("schema-targets.json is invalid: " + "; ".join(messages))

    targets: list[ValidationTarget] = []
    for target in registry_payload.get("targets", []):
        schema_rel = target.get("schema")
        data_rel = target.get("data")
        if not isinstance(schema_rel, str) or not isinstance(data_rel, str):
            raise ValueError(f"invalid registry target entry: {target}")
        targets.append(
            ValidationTarget(
                schema_rel=schema_rel,
                data_rel=data_rel,
            )
        )

    for glob_target in registry_payload.get("globTargets", []):
        schema_rel = glob_target.get("schema")
        glob_pattern = glob_target.get("glob")
        if not isinstance(schema_rel, str) or not isinstance(glob_pattern, str):
            raise ValueError(f"invalid registry glob target entry: {glob_target}")
        var_found = False
        for data_path in sorted(root.glob(glob_pattern)):
            if not data_path.is_file():
                continue
            var_found = True
            targets.append(
                ValidationTarget(
                    schema_rel=schema_rel,
                    data_rel=str(data_path.relative_to(root)),
                )
            )
        if not var_found:
            raise ValueError(f"schema target glob has no matches: {glob_pattern}")

    return targets


def collect_targets(root: Path) -> list[ValidationTarget]:
    return load_schema_target_registry(root)


def main() -> int:
    args = parse_args()
    try:
        root = detect_repo_root(args.root)
        targets = collect_targets(root)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1

    failures: list[str] = []
    for target in targets:
        failures.extend(validate_target(root, target))

    if failures:
        print("FAIL: schema gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
