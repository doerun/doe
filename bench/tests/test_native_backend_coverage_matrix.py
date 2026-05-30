#!/usr/bin/env python3
"""Tests for native backend coverage matrix checks."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_native_backend_coverage_matrix as coverage


REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "config" / "native-backend-coverage-matrix.json"


def _load() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_native_backend_coverage_matrix_passes_check() -> None:
    assert coverage.check_matrix(_load()) == []
    assert coverage.check_matrix(_load(), REPO_ROOT) == []


def test_native_backend_coverage_matrix_requires_all_rows() -> None:
    payload = _load()
    payload["rows"] = [
        row for row in payload["rows"] if not (row["backend"] == "doe_d3d12" and row["coverageClass"] == "tails")
    ]

    assert {
        "code": "missing_coverage_row",
        "path": "rows",
        "message": "missing coverage row doe_d3d12:tails",
    } in coverage.check_matrix(payload)


def test_native_backend_coverage_matrix_requires_evidence_for_covered_rows() -> None:
    payload = _load()
    payload["rows"][0]["evidencePath"] = ""

    assert {
        "code": "covered_row_missing_evidence",
        "path": "rows[0].evidencePath",
        "message": "covered rows require evidencePath",
    } in coverage.check_matrix(payload)


def test_native_backend_coverage_matrix_requires_reason_for_diagnostic_rows() -> None:
    payload = _load()
    payload["rows"][3]["reasonCode"] = ""

    assert {
        "code": "diagnostic_row_missing_reason",
        "path": "rows[3].reasonCode",
        "message": "diagnostic and missing rows require reasonCode",
    } in coverage.check_matrix(payload)


def test_native_backend_coverage_matrix_verifies_evidence_file_exists() -> None:
    payload = _load()
    payload["rows"][0]["evidencePath"] = "examples/missing-native-evidence.json"

    assert {
        "code": "evidence_file_missing",
        "path": "rows[0].evidencePath",
        "message": "evidence file not found: examples/missing-native-evidence.json",
    } in coverage.check_matrix(payload, REPO_ROOT)


def test_native_backend_coverage_matrix_rejects_unsafe_evidence_path() -> None:
    payload = _load()
    payload["rows"][0]["evidencePath"] = "/tmp/native-upload.json"

    assert {
        "code": "unsafe_evidence_path",
        "path": "rows[0].evidencePath",
        "message": "evidencePath must be repo-relative",
    } in coverage.check_matrix(payload, REPO_ROOT)


def test_native_backend_coverage_matrix_verifies_evidence_kind() -> None:
    payload = _load()
    payload["rows"][0]["evidencePath"] = "examples/native-pipeline-cache-receipts.sample.json"

    failures = coverage.check_matrix(payload, REPO_ROOT)

    assert any(item["code"] == "evidence_artifact_kind_mismatch" for item in failures)
