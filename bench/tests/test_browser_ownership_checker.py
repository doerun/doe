#!/usr/bin/env python3
"""Tests for the browser ownership checker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP_PATH = REPO_ROOT / "config" / "browser-ownership.json"
CHECKER_PATH = REPO_ROOT / "bench" / "tools" / "check_browser_ownership.py"


def _load_ownership() -> dict[str, Any]:
    return json.loads(OWNERSHIP_PATH.read_text(encoding="utf-8"))


def _load_checker() -> Any:
    spec = importlib.util.spec_from_file_location("browser_ownership", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_browser_ownership_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_ownership(_load_ownership()) == []


def test_browser_ownership_requires_all_areas() -> None:
    checker = _load_checker()
    payload = _load_ownership()
    del payload["areas"]["browser_runtime_integration"]

    failures = checker.check_ownership(payload)

    assert {
        "code": "missing_area",
        "path": "areas.browser_runtime_integration",
        "message": "missing area browser_runtime_integration",
    } in failures


def test_browser_ownership_requires_owner_fields() -> None:
    checker = _load_checker()
    payload = _load_ownership()
    payload["areas"]["browser_compatibility"]["qualityOwner"] = ""

    failures = checker.check_ownership(payload)

    assert {
        "code": "missing_ownership_field",
        "path": "areas.browser_compatibility.qualityOwner",
        "message": "browser_compatibility requires non-empty qualityOwner",
    } in failures


def test_browser_ownership_requires_nursery_exit_approval() -> None:
    checker = _load_checker()
    payload = _load_ownership()
    payload["areas"]["browser_performance_methodology"]["nurseryExitApproved"] = False

    failures = checker.check_ownership(payload)

    assert {
        "code": "nursery_exit_not_approved",
        "path": "areas.browser_performance_methodology.nurseryExitApproved",
        "message": "browser_performance_methodology nurseryExitApproved must be true",
    } in failures
