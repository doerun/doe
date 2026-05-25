#!/usr/bin/env python3
"""Tests for the Doe-vs-Tint compiler evidence gate."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "bench" / "gates" / "tint_compiler_evidence_gate.py"
SCHEMA_PATH = REPO_ROOT / "config" / "tint-compiler-evidence.schema.json"
SAMPLE_PATH = REPO_ROOT / "examples" / "tint-compiler-evidence.sample.json"

sys.path.insert(0, str(REPO_ROOT))


def load_module():
    spec = importlib.util.spec_from_file_location("tint_compiler_evidence_gate", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load tint_compiler_evidence_gate from {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def side_payload(output_digit: str) -> dict:
    return {
        "status": "ok",
        "diagnosticCode": "",
        "outputSha256": output_digit * 64,
        "irSha256": None,
        "validationStatus": "passed",
        "validationTool": "validator",
        "phaseTimingsNs": {
            "parse": 1,
            "sema": 1,
            "lower": 1,
            "emit": 1,
            "total": 4,
        },
        "receiptPath": f"bench/out/scratch/{output_digit}.json",
    }


def claimable_report() -> dict:
    return {
        "schemaVersion": 1,
        "artifactKind": "tint-compiler-evidence",
        "generatedAt": "2026-05-25T00:00:00Z",
        "comparisonStatus": "comparable",
        "claimStatus": "claimable",
        "corpus": {
            "id": "unit",
            "source": "unit",
            "sourceSha256": "0" * 64,
            "manifestPath": "",
        },
        "toolchains": {
            "doe": {
                "name": "doe-wgsl",
                "version": "unit",
                "command": ["doe"],
                "sourceRevision": "unit",
                "artifactPath": "",
                "artifactSha256": None,
            },
            "tint": {
                "name": "tint",
                "version": "unit",
                "command": ["tint"],
                "sourceRevision": "unit",
                "artifactPath": "",
                "artifactSha256": None,
            },
        },
        "phaseModel": {
            "timingScope": "phase",
            "units": "ns",
            "requiredPhases": ["parse", "sema", "lower", "emit", "total"],
        },
        "rows": [
            {
                "shaderId": "shader-a",
                "sourceSha256": "1" * 64,
                "target": "spirv",
                "shaderStage": "compute",
                "doe": side_payload("2"),
                "tint": side_payload("3"),
                "comparability": {
                    "status": "comparable",
                    "reasons": [],
                },
                "claimability": {
                    "status": "claimable",
                    "reasons": [],
                    "deltaPercent": {
                        "p50": 12.5,
                        "p95": 8.0,
                        "p99": 4.0,
                    },
                },
            }
        ],
        "summary": {
            "rowCount": 1,
            "comparableRows": 1,
            "claimableRows": 1,
            "reasons": [],
        },
    }


class TintCompilerEvidenceGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_sample_report_is_schema_valid_and_diagnostic(self) -> None:
        payload = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(self.schema).validate(payload)
        result = self.module.evaluate_report(payload)
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["claimStatus"], "diagnostic")
        self.assertEqual(result["summary"]["comparableRows"], 0)

    def test_claimable_report_passes(self) -> None:
        payload = claimable_report()
        jsonschema.Draft202012Validator(self.schema).validate(payload)
        result = self.module.evaluate_report(payload, require_claimable=True)
        self.assertTrue(result["ok"], result["failures"])
        self.assertEqual(result["summary"]["claimableRows"], 1)

    def test_claimable_report_rejects_missing_tint_validation(self) -> None:
        payload = claimable_report()
        payload["rows"][0]["tint"]["validationStatus"] = "not_run"
        result = self.module.evaluate_report(payload, require_claimable=True)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("tint: ok result requires validationStatus=passed" in item for item in result["failures"])
        )

    def test_comparable_row_rejects_diagnostic_reasons(self) -> None:
        payload = claimable_report()
        payload["rows"][0]["comparability"]["reasons"] = ["stale timing scope"]
        result = self.module.evaluate_report(payload, require_claimable=True)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("comparable row must not carry comparability reasons" in item for item in result["failures"])
        )

    def test_claimable_row_rejects_diagnostic_reasons(self) -> None:
        payload = claimable_report()
        payload["rows"][0]["claimability"]["reasons"] = ["missing warm tint samples"]
        result = self.module.evaluate_report(payload, require_claimable=True)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("claimable row must not carry claimability reasons" in item for item in result["failures"])
        )

    def test_summary_counts_must_match_rows(self) -> None:
        payload = claimable_report()
        payload["summary"]["claimableRows"] = 0
        result = self.module.evaluate_report(payload, require_claimable=True)
        self.assertFalse(result["ok"])
        self.assertTrue(any("summary.claimableRows must be 1" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
