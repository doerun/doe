#!/usr/bin/env python3
"""Tests for WGSL diagnostic fixture checks."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_wgsl_diagnostic_fixtures as diagnostics


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PATH = REPO_ROOT / "config" / "wgsl-diagnostic-fixtures.json"
MANIFEST_PATH = REPO_ROOT / "config" / "wgsl-browser-corpus.json"
TAXONOMY_PATH = REPO_ROOT / "config" / "shader-error-taxonomy.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_wgsl_diagnostic_fixtures_pass_check() -> None:
    assert diagnostics.check_fixtures(
        _load(FIXTURES_PATH),
        _load(MANIFEST_PATH),
        _load(TAXONOMY_PATH),
    ) == []


def test_wgsl_diagnostic_fixtures_reject_free_form_comparison() -> None:
    fixtures = _load(FIXTURES_PATH)
    fixtures["rows"][0]["evidencePolicy"]["freeFormTextCompared"] = True

    failures = diagnostics.check_fixtures(fixtures, _load(MANIFEST_PATH), _load(TAXONOMY_PATH))

    assert {
        "code": "free_form_text_comparison",
        "path": "rows[0].evidencePolicy.freeFormTextCompared",
        "message": "diagnostic fixtures must compare typed categories, not free-form text",
    } in failures


def test_wgsl_diagnostic_fixtures_require_taxonomy_code() -> None:
    fixtures = _load(FIXTURES_PATH)
    fixtures["rows"][0]["expected"]["doe"]["taxonomyCode"] = "missing_code"

    failures = diagnostics.check_fixtures(fixtures, _load(MANIFEST_PATH), _load(TAXONOMY_PATH))

    assert {
        "code": "unknown_taxonomy_code",
        "path": "rows[0].expected.doe.taxonomyCode",
        "message": "unknown shader taxonomy code 'missing_code'",
    } in failures


def test_wgsl_diagnostic_fixtures_reject_unsafe_source_path() -> None:
    fixtures = _load(FIXTURES_PATH)
    fixtures["rows"][0]["sourcePath"] = "/tmp/missing-return.wgsl"

    failures = diagnostics.check_fixtures(fixtures, _load(MANIFEST_PATH), _load(TAXONOMY_PATH))

    assert {
        "code": "unsafe_source_path",
        "path": "rows[0].sourcePath",
        "message": "sourcePath must be repo-relative",
    } in failures


def test_wgsl_diagnostic_fixtures_require_invalid_manifest_coverage() -> None:
    fixtures = _load(FIXTURES_PATH)
    fixtures["rows"] = []

    failures = diagnostics.check_fixtures(fixtures, _load(MANIFEST_PATH), _load(TAXONOMY_PATH))

    assert {
        "code": "missing_invalid_fixture",
        "path": "rows",
        "message": "missing diagnostic fixture for invalid shader invalid-missing-return",
    } in failures
