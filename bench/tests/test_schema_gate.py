#!/usr/bin/env python3
"""Tests for the schema gate target handling."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


MODULE_PATH = Path(__file__).resolve().parents[1] / "gates" / "schema_gate.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("schema_gate", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load schema_gate from {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_schema(root: Path) -> None:
    path = root / "config" / "sample.schema.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
            }
        ),
        encoding="utf-8",
    )


def test_missing_generated_bench_out_target_is_optional() -> None:
    module = _load_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_schema(root)

        failures = module.validate_target(
            root,
            module.ValidationTarget(
                schema_rel="config/sample.schema.json",
                data_rel="bench/out/generated/receipt.json",
            ),
        )

    assert failures == []


def test_missing_non_generated_target_still_fails() -> None:
    module = _load_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_schema(root)

        failures = module.validate_target(
            root,
            module.ValidationTarget(
                schema_rel="config/sample.schema.json",
                data_rel="examples/missing.json",
            ),
        )

    assert failures == ["missing data: examples/missing.json"]
