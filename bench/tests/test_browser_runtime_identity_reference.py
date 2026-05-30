#!/usr/bin/env python3
"""Tests for browser runtime identity reference checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "browser_runtime_identity_reference.py"


def _load_helper() -> Any:
    spec = importlib.util.spec_from_file_location("browser_runtime_identity_reference", HELPER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_identity_reference_accepts_identity_artifact() -> None:
    helper = _load_helper()
    payload = {
        "runtimeIdentity": {
            "runtimeIdentityPath": "examples/browser-runtime-identity.sample.json",
            "selectedRuntime": "browser_navigator_gpu",
            "fallbackApplied": False,
        }
    }

    assert helper.check_runtime_identity_reference(payload, REPO_ROOT) == []


def test_runtime_identity_reference_accepts_smoke_report() -> None:
    helper = _load_helper()
    payload = {
        "runtimeIdentity": {
            "runtimeIdentityPath": "examples/browser-smoke-report.sample.json",
            "selectedRuntime": "doe",
            "fallbackApplied": False,
        }
    }

    assert helper.check_runtime_identity_reference(payload, REPO_ROOT) == []


def test_runtime_identity_reference_rejects_mismatch() -> None:
    helper = _load_helper()
    payload = {
        "runtimeIdentity": {
            "runtimeIdentityPath": "examples/browser-runtime-identity.sample.json",
            "selectedRuntime": "doe",
            "fallbackApplied": False,
        }
    }

    failures = helper.check_runtime_identity_reference(payload, REPO_ROOT)

    assert {
        "code": "runtime_identity_reference_mismatch",
        "path": "runtimeIdentity",
        "message": "runtimeIdentity selectedRuntime/fallbackApplied must match referenced runtime evidence",
    } in failures


def test_runtime_identity_reference_rejects_unsafe_path() -> None:
    helper = _load_helper()
    payload = {
        "runtimeIdentity": {
            "runtimeIdentityPath": "../browser-runtime-identity.sample.json",
            "selectedRuntime": "browser_navigator_gpu",
            "fallbackApplied": False,
        }
    }

    failures = helper.check_runtime_identity_reference(payload, REPO_ROOT)

    assert {
        "code": "unsafe_runtime_identity_path",
        "path": "runtimeIdentity.runtimeIdentityPath",
        "message": "runtime identity path must be repo-relative",
    } in failures
