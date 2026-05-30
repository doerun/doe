#!/usr/bin/env python3
"""Tests for WGSL robustness fixture coverage."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_wgsl_robustness_fixtures as robustness


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PATH = REPO_ROOT / "config" / "wgsl-robustness-fixtures.json"


def _load() -> dict:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def test_wgsl_robustness_fixtures_pass_check() -> None:
    assert robustness.check_fixtures(_load()) == []


def test_wgsl_robustness_fixtures_require_all_pattern_classes() -> None:
    payload = _load()
    payload["rows"] = [
        row for row in payload["rows"] if row["patternClass"] != "texture_dimension"
    ]

    assert {
        "code": "missing_pattern_class",
        "path": "rows",
        "message": "missing robustness fixture class texture_dimension",
    } in robustness.check_fixtures(payload)


def test_wgsl_robustness_fixtures_reject_hash_drift() -> None:
    payload = _load()
    payload["rows"][0]["normalizedSourceSha256"] = "0" * 64

    failures = robustness.check_fixtures(payload)

    assert failures[0]["code"] == "source_hash_mismatch"
    assert failures[0]["path"] == "rows[0].normalizedSourceSha256"


def test_wgsl_robustness_fixtures_reject_unsafe_source_path() -> None:
    payload = _load()
    payload["rows"][0]["sourcePath"] = "../fixtures/bounds-storage-buffer-1d.wgsl"

    assert {
        "code": "unsafe_source_path",
        "path": "rows[0].sourcePath",
        "message": "sourcePath must be repo-relative",
    } in robustness.check_fixtures(payload)


def test_wgsl_robustness_fixtures_require_source_needles() -> None:
    payload = _load()
    payload["rows"][0]["requiredNeedles"] = ["missing sentinel"]

    assert {
        "code": "missing_required_needle",
        "path": "rows[0].requiredNeedles",
        "message": "fixture source does not contain 'missing sentinel'",
    } in robustness.check_fixtures(payload)
