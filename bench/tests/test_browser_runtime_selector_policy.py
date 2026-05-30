#!/usr/bin/env python3
"""Tests for the browser runtime selector policy checker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "config" / "browser-runtime-selector-policy.json"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-runtime-selector-policy.py"


def _load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _load_checker():
    spec = importlib.util.spec_from_file_location("browser_runtime_selector_policy", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_browser_runtime_selector_policy_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_policy(_load_policy()) == []


def test_browser_runtime_selector_policy_rejects_missing_mode() -> None:
    checker = _load_checker()
    policy = _load_policy()
    policy["selectionModes"] = ["dawn", "auto"]

    failures = checker.check_policy(policy)

    assert {
        "code": "invalid_selection_modes",
        "path": "selectionModes",
        "message": "selection modes must be exactly dawn, doe, auto",
    } in failures


def test_browser_runtime_selector_policy_rejects_forced_doe_fallback() -> None:
    checker = _load_checker()
    policy = _load_policy()
    policy["forcedDoeFailure"]["fallbackToDawn"] = True

    failures = checker.check_policy(policy)

    assert {
        "code": "forced_doe_not_fail_closed",
        "path": "forcedDoeFailure",
        "message": "forced Doe must fail closed without falling back to Dawn",
    } in failures


def test_browser_runtime_selector_policy_requires_observability_field() -> None:
    checker = _load_checker()
    policy = _load_policy()
    policy["observabilityFields"].remove("artifactIdentity.dawnRuntimeSha256")

    failures = checker.check_policy(policy)

    assert {
        "code": "missing_observability_field",
        "path": "observabilityFields",
        "message": "missing observability field artifactIdentity.dawnRuntimeSha256",
    } in failures
