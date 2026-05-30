#!/usr/bin/env python3
"""Tests for native pipeline cache receipt checks."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_native_pipeline_cache_receipts as cache_check


REPO_ROOT = Path(__file__).resolve().parents[2]
RECEIPTS_PATH = REPO_ROOT / "examples" / "native-pipeline-cache-receipts.sample.json"


def _load() -> dict:
    return json.loads(RECEIPTS_PATH.read_text(encoding="utf-8"))


def test_native_pipeline_cache_receipts_pass_check() -> None:
    assert cache_check.check_receipts(_load()) == []


def test_native_pipeline_cache_receipts_require_cold_warm_pair() -> None:
    payload = _load()
    payload["rows"] = [payload["rows"][0]]

    assert {
        "code": "missing_cold_warm_pair",
        "path": "rows",
        "message": "workload 'compute_test' must carry cold and warm rows",
    } in cache_check.check_receipts(payload)


def test_native_pipeline_cache_receipts_reject_warm_created_state() -> None:
    payload = _load()
    payload["rows"][1]["cacheState"] = "created"

    assert {
        "code": "warm_mode_not_warm",
        "path": "rows[1].cacheState",
        "message": "warm mode must report hit or disabled",
    } in cache_check.check_receipts(payload)


def test_native_pipeline_cache_receipts_require_path_asymmetry_note() -> None:
    payload = _load()
    payload["rows"][0]["pathAsymmetry"] = True

    assert {
        "code": "missing_path_asymmetry_note",
        "path": "rows[0].pathAsymmetryNote",
        "message": "path asymmetry requires a note",
    } in cache_check.check_receipts(payload)
