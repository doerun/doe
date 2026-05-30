#!/usr/bin/env python3
"""Tests for the browser claim policy checker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "config" / "browser-claim-policy.json"
RELEASE_POLICY_PATH = REPO_ROOT / "config" / "browser-claim-policy.release.json"
CHECKER_PATH = REPO_ROOT / "bench" / "tools" / "check_browser_claim_policy.py"


def _load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_checker() -> Any:
    spec = importlib.util.spec_from_file_location("browser_claim_policy", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_browser_claim_policy_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_policy(_load_policy()) == []


def test_browser_release_claim_policy_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_policy(_load_policy(RELEASE_POLICY_PATH)) == []


def test_browser_release_claim_policy_requires_p99() -> None:
    checker = _load_checker()
    payload = _load_policy(RELEASE_POLICY_PATH)
    payload["requiredPositivePercentiles"].remove("p99Percent")

    failures = checker.check_policy(payload)

    assert {
        "code": "release_missing_p99",
        "path": "requiredPositivePercentiles",
        "message": "release browser claim policy must require p99Percent",
    } in failures


def test_browser_claim_policy_rejects_data_url_fallback() -> None:
    checker = _load_checker()
    payload = _load_policy()
    payload["allowDataUrlFallback"] = True

    failures = checker.check_policy(payload)

    assert {
        "code": "data_url_fallback_allowed",
        "path": "allowDataUrlFallback",
        "message": "data URL fallback must be disabled",
    } in failures


def test_browser_claim_policy_requires_both_modes() -> None:
    checker = _load_checker()
    payload = _load_policy()
    payload["requireModes"] = ["doe"]

    failures = checker.check_policy(payload)

    assert {
        "code": "invalid_require_modes",
        "path": "requireModes",
        "message": "requireModes must be exactly dawn and doe",
    } in failures
