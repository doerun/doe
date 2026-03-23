#!/usr/bin/env python3
"""Adversarial/negative config-schema validation tests.

For each config/*.json that has a matching *.schema.json (via schema-targets.json),
verify:
  a. The config validates against its schema (positive case).
  b. Removing each required field causes validation failure (negative).
  c. Adding an unknown field causes failure IF additionalProperties=false.
  d. Setting a string field to a number causes failure.

Run: python3 bench/test_config_schemas.py
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file: validate each line against the schema individually."""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def collect_string_field_paths(schema: dict, prefix: str = "") -> list[tuple[str, list[str]]]:
    """Walk a schema and collect JSON-pointer-style paths to string-typed properties.

    Returns a list of (dotted_path, key_chain) pairs for top-level and one-level
    nested string properties that are safe to mutate in tests.
    """
    results: list[tuple[str, list[str]]] = []
    props = schema.get("properties", {})
    for key, prop_schema in props.items():
        full_path = f"{prefix}.{key}" if prefix else key
        resolved = prop_schema
        if resolved.get("type") == "string":
            results.append((full_path, full_path.split(".")))
        elif resolved.get("type") == "object" and "properties" in resolved:
            results.extend(collect_string_field_paths(resolved, full_path))
    return results


def has_additional_properties_false(schema: dict) -> bool:
    return schema.get("additionalProperties") is False


def collect_required_fields(schema: dict) -> list[str]:
    return list(schema.get("required", []))


class SchemaTargetEntry:
    """Represents one schema-to-data mapping from schema-targets.json."""

    def __init__(self, schema_path: Path, data_path: Path, is_jsonl: bool = False):
        self.schema_path = schema_path
        self.data_path = data_path
        self.is_jsonl = is_jsonl

    @property
    def label(self) -> str:
        return self.data_path.name


def load_targets() -> list[SchemaTargetEntry]:
    targets_path = REPO_ROOT / "config" / "schema-targets.json"
    raw = load_json(targets_path)
    entries: list[SchemaTargetEntry] = []
    for t in raw.get("targets", []):
        schema_rel = t["schema"]
        data_rel = t["data"]
        schema_path = REPO_ROOT / schema_rel
        data_path = REPO_ROOT / data_rel
        if not schema_path.exists():
            continue
        if not data_path.exists():
            continue
        is_jsonl = data_path.suffix == ".jsonl"
        entries.append(SchemaTargetEntry(schema_path, data_path, is_jsonl))
    return entries


class ConfigSchemaFuzzTests(unittest.TestCase):
    """Test suite generated dynamically per schema-target pair."""


def _make_positive_test(entry: SchemaTargetEntry):
    """Factory: config validates against its schema."""

    def test(self: unittest.TestCase) -> None:
        schema = load_json(entry.schema_path)
        if entry.is_jsonl:
            records = load_jsonl(entry.data_path)
            self.assertGreater(len(records), 0, f"{entry.label}: JSONL file is empty")
            for i, record in enumerate(records):
                try:
                    jsonschema.validate(record, schema)
                except jsonschema.ValidationError as exc:
                    self.fail(f"{entry.label} line {i}: positive validation failed: {exc.message}")
        else:
            data = load_json(entry.data_path)
            try:
                jsonschema.validate(data, schema)
            except jsonschema.ValidationError as exc:
                self.fail(f"{entry.label}: positive validation failed: {exc.message}")

    return test


def _make_missing_required_test(entry: SchemaTargetEntry):
    """Factory: removing each required field causes validation failure."""

    def test(self: unittest.TestCase) -> None:
        schema = load_json(entry.schema_path)
        required = collect_required_fields(schema)
        if not required:
            self.skipTest(f"{entry.label}: schema has no required fields")
            return

        if entry.is_jsonl:
            records = load_jsonl(entry.data_path)
            if not records:
                self.skipTest(f"{entry.label}: JSONL file is empty")
                return
            data = records[0]
        else:
            data = load_json(entry.data_path)

        if not isinstance(data, dict):
            self.skipTest(f"{entry.label}: top-level value is not an object")
            return

        for field in required:
            if field not in data:
                continue
            mutated = copy.deepcopy(data)
            del mutated[field]
            with self.assertRaises(
                jsonschema.ValidationError,
                msg=f"{entry.label}: removing required field '{field}' should fail validation",
            ):
                jsonschema.validate(mutated, schema)

    return test


def _make_additional_properties_test(entry: SchemaTargetEntry):
    """Factory: adding unknown field causes failure when additionalProperties=false."""

    def test(self: unittest.TestCase) -> None:
        schema = load_json(entry.schema_path)
        if not has_additional_properties_false(schema):
            self.skipTest(f"{entry.label}: additionalProperties is not false at top level")
            return

        if entry.is_jsonl:
            records = load_jsonl(entry.data_path)
            if not records:
                self.skipTest(f"{entry.label}: JSONL file is empty")
                return
            data = records[0]
        else:
            data = load_json(entry.data_path)

        if not isinstance(data, dict):
            self.skipTest(f"{entry.label}: top-level value is not an object")
            return

        mutated = copy.deepcopy(data)
        mutated["__fawn_adversarial_unknown_field__"] = "bad"
        with self.assertRaises(
            jsonschema.ValidationError,
            msg=f"{entry.label}: adding unknown field should fail with additionalProperties=false",
        ):
            jsonschema.validate(mutated, schema)

    return test


def _make_type_mismatch_test(entry: SchemaTargetEntry):
    """Factory: setting a string field to a number causes failure."""

    def test(self: unittest.TestCase) -> None:
        schema = load_json(entry.schema_path)
        string_paths = collect_string_field_paths(schema)
        if not string_paths:
            self.skipTest(f"{entry.label}: no string properties found in schema")
            return

        if entry.is_jsonl:
            records = load_jsonl(entry.data_path)
            if not records:
                self.skipTest(f"{entry.label}: JSONL file is empty")
                return
            data = records[0]
        else:
            data = load_json(entry.data_path)

        if not isinstance(data, dict):
            self.skipTest(f"{entry.label}: top-level value is not an object")
            return

        tested_any = False
        for dotted_path, key_chain in string_paths:
            mutated = copy.deepcopy(data)
            target = mutated
            reachable = True
            for key in key_chain[:-1]:
                if isinstance(target, dict) and key in target:
                    target = target[key]
                else:
                    reachable = False
                    break
            if not reachable or not isinstance(target, dict):
                continue
            final_key = key_chain[-1]
            if final_key not in target:
                continue
            if not isinstance(target[final_key], str):
                continue

            target[final_key] = 99999
            tested_any = True
            try:
                jsonschema.validate(mutated, schema)
                self.fail(
                    f"{entry.label}: setting string field '{dotted_path}' to a number "
                    "should have caused validation failure"
                )
            except jsonschema.ValidationError:
                pass

        if not tested_any:
            self.skipTest(f"{entry.label}: no reachable string fields in data to mutate")

    return test


def _register_tests() -> None:
    """Dynamically add test methods for each schema-target entry."""
    targets = load_targets()
    for entry in targets:
        safe_name = entry.data_path.stem.replace("-", "_").replace(".", "_")

        setattr(
            ConfigSchemaFuzzTests,
            f"test_positive__{safe_name}",
            _make_positive_test(entry),
        )
        setattr(
            ConfigSchemaFuzzTests,
            f"test_missing_required__{safe_name}",
            _make_missing_required_test(entry),
        )
        setattr(
            ConfigSchemaFuzzTests,
            f"test_additional_properties__{safe_name}",
            _make_additional_properties_test(entry),
        )
        setattr(
            ConfigSchemaFuzzTests,
            f"test_type_mismatch__{safe_name}",
            _make_type_mismatch_test(entry),
        )


_register_tests()


if __name__ == "__main__":
    unittest.main(verbosity=2)
