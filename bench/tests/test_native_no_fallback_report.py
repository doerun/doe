#!/usr/bin/env python3
"""Tests for native no-fallback reports."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import jsonschema

from bench.tools import build_native_no_fallback_report as no_fallback
from bench.tools import check_native_no_fallback_report as check_no_fallback


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_RECEIPT_PATH = REPO_ROOT / "examples" / "run-receipt.sample.json"
SCHEMA_PATH = REPO_ROOT / "config" / "native-no-fallback-report.schema.json"
SAMPLE_PATH = REPO_ROOT / "examples" / "native-no-fallback-report.sample.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_native_no_fallback_report_passes_for_native_doe_receipt() -> None:
    report = no_fallback.build_report([RUN_RECEIPT_PATH])

    jsonschema.Draft202012Validator(_load(SCHEMA_PATH)).validate(report)
    assert report["rows"][0]["runReceiptPath"] == "examples/run-receipt.sample.json"
    assert report["status"] == "pass"
    assert report["summary"]["failureCodes"] == []
    assert check_no_fallback.check_report(report) == []


def test_native_no_fallback_report_checker_accepts_sample() -> None:
    assert check_no_fallback.check_report(_load(SAMPLE_PATH)) == []


def test_native_no_fallback_report_checker_verifies_sample_files() -> None:
    assert check_no_fallback.check_report(_load(SAMPLE_PATH), REPO_ROOT) == []


def test_native_no_fallback_report_rejects_non_doe_backend() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "run.json"
        payload = _load(RUN_RECEIPT_PATH)
        payload["runtimeIdentity"]["executionBackend"] = "dawn_vulkan"
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = no_fallback.build_report([path])

    assert report["status"] == "fail"
    assert report["summary"]["failureCodes"][0]["code"] == "non_doe_execution_backend"


def test_native_no_fallback_report_rejects_sample_fallback_marker() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "run.json"
        payload = _load(RUN_RECEIPT_PATH)
        payload["samples"][0]["traceMeta"]["fallbackUsed"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = no_fallback.build_report([path])

    codes = {item["code"] for item in report["summary"]["failureCodes"]}
    assert "sample_fallback_used" in codes


def test_native_no_fallback_report_rejects_non_native_host() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "run.json"
        payload = _load(RUN_RECEIPT_PATH)
        payload["runtimeIdentity"]["runtimeHost"] = "browser"
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = no_fallback.build_report([path])

    codes = {item["code"] for item in report["summary"]["failureCodes"]}
    assert "non_native_runtime_host" in codes


def test_native_no_fallback_report_checker_verifies_run_receipt_hash(tmp_path: Path) -> None:
    receipt_path = tmp_path / "run-receipt.json"
    receipt_path.write_text("{}\n", encoding="utf-8")
    report = _load(SAMPLE_PATH)
    report["rows"][0]["runReceiptPath"] = "run-receipt.json"
    report["rows"][0]["runReceiptSha256"] = "0" * 64

    assert any(
        item["code"] == "run_receipt_hash_mismatch"
        for item in check_no_fallback.check_report(report, tmp_path)
    )


def test_native_no_fallback_report_rejects_unsafe_run_receipt_path() -> None:
    report = _load(SAMPLE_PATH)
    report["rows"][0]["runReceiptPath"] = "../run-receipt.sample.json"

    assert {
        "code": "unsafe_run_receipt_path",
        "path": "rows[0].runReceiptPath",
        "message": "runReceiptPath must be repo-relative",
    } in check_no_fallback.check_report(report, REPO_ROOT)
