#!/usr/bin/env python3
"""Tests for native upload path receipt checks."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_native_upload_path_receipts as upload_check


REPO_ROOT = Path(__file__).resolve().parents[2]
RECEIPTS_PATH = REPO_ROOT / "examples" / "native-upload-path-receipts.sample.json"


def _load() -> dict:
    return json.loads(RECEIPTS_PATH.read_text(encoding="utf-8"))


def test_native_upload_path_receipts_pass_check() -> None:
    assert upload_check.check_receipts(_load()) == []


def test_native_upload_path_receipts_reject_asymmetric_claim() -> None:
    payload = _load()
    payload["rows"][1]["claimEligible"] = True

    assert {
        "code": "asymmetric_path_claimable",
        "path": "rows[1].claimEligible",
        "message": "path-asymmetric upload rows cannot be claim-eligible",
    } in upload_check.check_receipts(payload)


def test_native_upload_path_receipts_reject_strict_non_staging_path() -> None:
    payload = _load()
    payload["rows"][0]["uploadPath"] = "shared_memory_write"

    assert {
        "code": "strict_upload_not_staging_copy",
        "path": "rows[0].uploadPath",
        "message": "strict comparable upload rows must use staging_copy",
    } in upload_check.check_receipts(payload)


def test_native_upload_path_receipts_require_copy_commands_for_staging() -> None:
    payload = _load()
    payload["rows"][0]["copyCommandsRecorded"] = 0

    assert {
        "code": "missing_staging_copy_command",
        "path": "rows[0].copyCommandsRecorded",
        "message": "staging_copy rows must record copy commands",
    } in upload_check.check_receipts(payload)
