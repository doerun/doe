#!/usr/bin/env python3
"""Tests for browser unsupported reason taxonomy checks."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from bench.tools import check_browser_unsupported_reason_taxonomy as taxonomy


REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = REPO_ROOT / "config" / "browser-unsupported-reason-taxonomy.json"


def _load() -> dict:
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def test_browser_unsupported_reason_taxonomy_passes_check() -> None:
    assert taxonomy.check_taxonomy(_load()) == []


def test_browser_unsupported_reason_taxonomy_rejects_duplicate_code() -> None:
    payload = _load()
    payload["codes"].append(copy.deepcopy(payload["codes"][0]))

    assert any(
        failure["code"] == "duplicate_reason_code"
        for failure in taxonomy.check_taxonomy(payload)
    )


def test_browser_unsupported_reason_taxonomy_requires_core_code() -> None:
    payload = _load()
    payload["codes"] = [
        row for row in payload["codes"] if row["reasonCode"] != "profile_denylisted"
    ]

    assert {
        "code": "missing_required_reason_code",
        "path": "codes",
        "message": "missing required reasonCode profile_denylisted",
    } in taxonomy.check_taxonomy(payload)


def test_browser_unsupported_reason_taxonomy_rejects_invalid_category() -> None:
    payload = _load()
    payload["codes"][0]["category"] = "maybe"

    assert {
        "code": "invalid_category",
        "path": "codes[0].category",
        "message": "category must use the browser unsupported reason taxonomy",
    } in taxonomy.check_taxonomy(payload)


def test_browser_unsupported_reason_taxonomy_restricts_nonvisible_codes_to_diagnostics() -> None:
    payload = _load()
    payload["codes"][0]["developerVisible"] = False
    payload["codes"][0]["notes"] = ""

    failures = taxonomy.check_taxonomy(payload)

    assert {
        "code": "nonvisible_reason_not_diagnostic",
        "path": "codes[0].developerVisible",
        "message": "non-visible reason codes must remain diagnostic-only",
    } in failures
    assert {
        "code": "missing_notes",
        "path": "codes[0].notes",
        "message": "developer-visible reason codes require notes",
    } in failures


def test_browser_unsupported_reason_taxonomy_rejects_duplicate_status() -> None:
    payload = _load()
    payload["codes"][0]["statuses"].append(payload["codes"][0]["statuses"][0])

    assert {
        "code": "duplicate_status",
        "path": "codes[0].statuses",
        "message": "statuses must be unique",
    } in taxonomy.check_taxonomy(payload)


def test_browser_unsupported_reason_taxonomy_rejects_category_status_mismatch() -> None:
    payload = _load()
    payload["codes"][0]["statuses"] = ["blocked"]

    assert {
        "code": "category_status_mismatch",
        "path": "codes[0].statuses",
        "message": "category 'supported' requires status 'supported'",
    } in taxonomy.check_taxonomy(payload)
