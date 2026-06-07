#!/usr/bin/env python3
"""Tests for bench/config_validation.py shared validation helper.

Covers load_validated_config, schema inference, missing schema,
malformed JSON, and edge cases.
Runs without network or GPU access.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.lib import config_validation as cv

# jsonschema is a dependency of the module under test
import jsonschema


def _make_schema(*, required: list[str] | None = None, properties: dict | None = None) -> dict:
    """Build a minimal JSON Schema for testing."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
    }
    if required:
        schema["required"] = required
    if properties:
        schema["properties"] = properties
    return schema


class TestLoadValidatedConfig(unittest.TestCase):
    """load_validated_config: valid config passes, invalid raises."""

    def test_valid_config(self):
        schema = _make_schema(
            required=["name"],
            properties={"name": {"type": "string"}},
        )
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "test.json"
            sch_path = Path(td) / "test.schema.json"
            cfg_path.write_text(json.dumps({"name": "hello"}), encoding="utf-8")
            sch_path.write_text(json.dumps(schema), encoding="utf-8")
            result = cv.load_validated_config(cfg_path)
            self.assertEqual(result["name"], "hello")

    def test_valid_config_explicit_schema(self):
        schema = _make_schema(
            required=["version"],
            properties={"version": {"type": "integer"}},
        )
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "test.json"
            sch_path = Path(td) / "custom.schema.json"
            cfg_path.write_text(json.dumps({"version": 1}), encoding="utf-8")
            sch_path.write_text(json.dumps(schema), encoding="utf-8")
            result = cv.load_validated_config(cfg_path, schema_path=sch_path)
            self.assertEqual(result["version"], 1)

    def test_invalid_config_raises_validation_error(self):
        schema = _make_schema(
            required=["name"],
            properties={"name": {"type": "string"}},
        )
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "test.json"
            sch_path = Path(td) / "test.schema.json"
            # name is integer, not string
            cfg_path.write_text(json.dumps({"name": 42}), encoding="utf-8")
            sch_path.write_text(json.dumps(schema), encoding="utf-8")
            with self.assertRaises(jsonschema.ValidationError):
                cv.load_validated_config(cfg_path)

    def test_missing_required_field_raises(self):
        schema = _make_schema(
            required=["name", "version"],
            properties={
                "name": {"type": "string"},
                "version": {"type": "integer"},
            },
        )
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "test.json"
            sch_path = Path(td) / "test.schema.json"
            cfg_path.write_text(json.dumps({"name": "x"}), encoding="utf-8")
            sch_path.write_text(json.dumps(schema), encoding="utf-8")
            with self.assertRaises(jsonschema.ValidationError):
                cv.load_validated_config(cfg_path)

    def test_config_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nonexistent.json"
            with self.assertRaises(FileNotFoundError):
                cv.load_validated_config(missing)

    def test_non_object_config_raises_value_error(self):
        schema = _make_schema()
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "test.json"
            sch_path = Path(td) / "test.schema.json"
            cfg_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            sch_path.write_text(json.dumps(schema), encoding="utf-8")
            with self.assertRaises(ValueError):
                cv.load_validated_config(cfg_path)

    def test_string_config_raises_value_error(self):
        schema = _make_schema()
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "test.json"
            sch_path = Path(td) / "test.schema.json"
            cfg_path.write_text('"just a string"', encoding="utf-8")
            sch_path.write_text(json.dumps(schema), encoding="utf-8")
            with self.assertRaises(ValueError):
                cv.load_validated_config(cfg_path)


class TestSchemaInference(unittest.TestCase):
    """Schema path inference: foo.json -> foo.schema.json."""

    def test_simple_inference(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "workload.json"
            sch_path = Path(td) / "workload.schema.json"
            cfg_path.touch()
            sch_path.touch()
            inferred = cv._infer_schema_path(cfg_path)
            self.assertEqual(inferred, sch_path)

    def test_variant_inference_with_existing_base(self):
        """claim-cycle.active.json -> claim-cycle.schema.json when it exists."""
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "claim-cycle.active.json"
            base_sch = Path(td) / "claim-cycle.schema.json"
            cfg_path.touch()
            base_sch.touch()
            inferred = cv._infer_schema_path(cfg_path)
            self.assertEqual(inferred, base_sch)

    def test_variant_falls_back_to_full_stem(self):
        """claim-cycle.active.json -> claim-cycle.active.schema.json when base missing."""
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "claim-cycle.active.json"
            cfg_path.touch()
            # No base schema, so it should fall back to full stem
            inferred = cv._infer_schema_path(cfg_path)
            self.assertEqual(inferred.name, "claim-cycle.active.schema.json")

    def test_no_json_suffix_raises(self):
        with self.assertRaises(ValueError):
            cv._infer_schema_path(Path("/some/config.yaml"))

    def test_simple_name_no_dots(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "simple.json"
            cfg_path.touch()
            inferred = cv._infer_schema_path(cfg_path)
            self.assertEqual(inferred.name, "simple.schema.json")

    def test_deeply_dotted_name(self):
        """a.b.c.json -> tries a.b.schema.json first, falls back to a.b.c.schema.json."""
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "a.b.c.json"
            cfg_path.touch()
            # No a.b.schema.json exists, so falls back
            inferred = cv._infer_schema_path(cfg_path)
            self.assertEqual(inferred.name, "a.b.c.schema.json")

    def test_deeply_dotted_with_base_schema(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "a.b.c.json"
            base_sch = Path(td) / "a.b.schema.json"
            cfg_path.touch()
            base_sch.touch()
            inferred = cv._infer_schema_path(cfg_path)
            self.assertEqual(inferred, base_sch)


class TestMissingSchema(unittest.TestCase):
    """Config without a corresponding schema should raise FileNotFoundError."""

    def test_no_schema_file(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "orphan.json"
            cfg_path.write_text(json.dumps({"x": 1}), encoding="utf-8")
            # No schema file at all
            with self.assertRaises(FileNotFoundError):
                cv.load_validated_config(cfg_path)

    def test_explicit_missing_schema(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "test.json"
            cfg_path.write_text(json.dumps({"x": 1}), encoding="utf-8")
            missing_sch = Path(td) / "nonexistent.schema.json"
            with self.assertRaises(FileNotFoundError):
                cv.load_validated_config(cfg_path, schema_path=missing_sch)


class TestMalformedJSON(unittest.TestCase):
    """Invalid JSON in config should raise JSONDecodeError."""

    def test_invalid_json_syntax(self):
        schema = _make_schema()
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "bad.json"
            sch_path = Path(td) / "bad.schema.json"
            cfg_path.write_text("{invalid json content", encoding="utf-8")
            sch_path.write_text(json.dumps(schema), encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                cv.load_validated_config(cfg_path)

    def test_truncated_json(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "trunc.json"
            sch_path = Path(td) / "trunc.schema.json"
            cfg_path.write_text('{"name": "hello', encoding="utf-8")
            sch_path.write_text(json.dumps(_make_schema()), encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                cv.load_validated_config(cfg_path)

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "empty.json"
            sch_path = Path(td) / "empty.schema.json"
            cfg_path.write_text("", encoding="utf-8")
            sch_path.write_text(json.dumps(_make_schema()), encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                cv.load_validated_config(cfg_path)


class TestFormatPath(unittest.TestCase):
    """_format_path helper."""

    def test_root_path(self):
        from collections import deque
        err = jsonschema.ValidationError("test", path=deque())
        self.assertEqual(cv._format_path(err), "<root>")

    def test_nested_path(self):
        from collections import deque
        err = jsonschema.ValidationError("test", path=deque(["a", "b", 0]))
        self.assertEqual(cv._format_path(err), "a.b.0")


class TestRealConfigs(unittest.TestCase):
    """Smoke test: load real configs from the repo if they exist."""

    def _try_load(self, config_rel_path: str, schema_rel_path: str | None = None):
        repo_root = Path(__file__).resolve().parents[2]
        cfg = repo_root / config_rel_path
        if not cfg.exists():
            self.skipTest(f"{config_rel_path} not found")
        if schema_rel_path:
            sch = repo_root / schema_rel_path
            if not sch.exists():
                self.skipTest(f"{schema_rel_path} not found")
            return cv.load_validated_config(cfg, schema_path=sch)
        return cv.load_validated_config(cfg)

    def test_quirks_schema_exists(self):
        repo_root = Path(__file__).resolve().parents[2]
        sch = repo_root / "config" / "quirks.schema.json"
        self.assertTrue(sch.exists(), "quirks.schema.json should exist")

    def test_trace_schema_exists(self):
        repo_root = Path(__file__).resolve().parents[2]
        sch = repo_root / "config" / "trace.schema.json"
        self.assertTrue(sch.exists(), "trace.schema.json should exist")

    def test_trace_meta_schema_exists(self):
        repo_root = Path(__file__).resolve().parents[2]
        sch = repo_root / "config" / "trace-meta.schema.json"
        self.assertTrue(sch.exists(), "trace-meta.schema.json should exist")

    def test_trace_meta_workload_unit_wall_source_is_enum_constrained(self):
        repo_root = Path(__file__).resolve().parents[2]
        sch = repo_root / "config" / "trace-meta.schema.json"
        schema = json.loads(sch.read_text(encoding="utf-8"))
        valid = {
            "traceVersion": 1,
            "module": "alpha",
            "seqMax": 0,
            "rowCount": 0,
            "hash": "0x1",
            "previousHash": "0x0",
            "workloadUnitWallSource": "trace-meta-process-wall",
        }
        jsonschema.validate(valid, schema)
        invalid = dict(valid)
        invalid["workloadUnitWallSource"] = "trace-meta-processwall"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_trace_meta_accepts_shader_source_receipts(self):
        repo_root = Path(__file__).resolve().parents[2]
        sch = repo_root / "config" / "trace-meta.schema.json"
        schema = json.loads(sch.read_text(encoding="utf-8"))
        valid = {
            "traceVersion": 1,
            "module": "doe-gpu/package",
            "seqMax": 0,
            "rowCount": 0,
            "hash": "sha256:" + ("1" * 64),
            "previousHash": "sha256:" + ("0" * 64),
            "shaderSourceReceiptsHash": "2" * 64,
            "shaderSourceReceipts": [
                {
                    "moduleId": "multiply",
                    "sourceKind": "path",
                    "path": "bench/kernels/multiply.wgsl",
                    "entryPoint": "main",
                    "byteLength": 3,
                    "sha256": "3" * 64,
                }
            ],
        }
        jsonschema.validate(valid, schema)

    def test_trace_meta_accepts_package_native_queue_sync_info(self):
        repo_root = Path(__file__).resolve().parents[2]
        sch = repo_root / "config" / "trace-meta.schema.json"
        schema = json.loads(sch.read_text(encoding="utf-8"))
        valid = {
            "traceVersion": 1,
            "module": "doe-gpu/package",
            "seqMax": 0,
            "rowCount": 0,
            "hash": "sha256:" + ("1" * 64),
            "previousHash": "sha256:" + ("0" * 64),
            "packageNativeQueueSyncInfo": {
                "backendVulkan": True,
                "timelineSemaphore": True,
                "fencePool": True,
                "deferredSubmissions": False,
            },
        }
        jsonschema.validate(valid, schema)
        invalid = json.loads(json.dumps(valid))
        del invalid["packageNativeQueueSyncInfo"]["timelineSemaphore"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)

    def test_trace_meta_determinism_accepts_stable_token_summary(self):
        repo_root = Path(__file__).resolve().parents[2]
        sch = repo_root / "config" / "trace-meta.schema.json"
        schema = json.loads(sch.read_text(encoding="utf-8"))
        valid = {
            "traceVersion": 1,
            "module": "doe-gpu/determinism",
            "seqMax": 0,
            "rowCount": 0,
            "hash": "sha256:" + ("1" * 64),
            "previousHash": "sha256:" + ("0" * 64),
            "determinism": {
                "mode": "stable-token",
                "policyRegistryPath": "config/determinism-policy.json",
                "policyRegistryVersion": "2026-03-28",
                "policyId": "stable-token/lowest-index-among-max-v1",
                "comparator": "scalar-f32-greedy",
                "tieBreakRule": "lowest-index-among-max",
                "selectedBy": "stable-token-policy",
                "logitsSha256": "a" * 64,
                "token": 7,
                "proofArtifactPath": "pipeline/lean/artifacts/proven-conditions.json",
                "proofTheorems": ["stableTokenChoose_mem_tiedMaxIndices"],
            },
        }
        jsonschema.validate(valid, schema)

    def test_trace_meta_determinism_rejects_missing_policy_registry_version(self):
        repo_root = Path(__file__).resolve().parents[2]
        sch = repo_root / "config" / "trace-meta.schema.json"
        schema = json.loads(sch.read_text(encoding="utf-8"))
        invalid = {
            "traceVersion": 1,
            "module": "doe-gpu/determinism",
            "seqMax": 0,
            "rowCount": 0,
            "hash": "sha256:" + ("1" * 64),
            "previousHash": "sha256:" + ("0" * 64),
            "determinism": {
                "mode": "stable-token",
                "policyRegistryPath": "config/determinism-policy.json",
                "policyId": "stable-token/lowest-index-among-max-v1",
                "comparator": "scalar-f32-greedy",
                "tieBreakRule": "lowest-index-among-max",
                "selectedBy": "stable-token-policy",
                "logitsSha256": "a" * 64,
                "token": 7,
                "proofArtifactPath": "pipeline/lean/artifacts/proven-conditions.json",
                "proofTheorems": ["stableTokenChoose_mem_tiedMaxIndices"],
            },
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


if __name__ == "__main__":
    unittest.main()
