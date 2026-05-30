#!/usr/bin/env python3
"""Tests for the browser runtime identity checker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-runtime-identity.sample.json"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-runtime-identity.py"


def _load_sample() -> dict[str, Any]:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_checker() -> Any:
    spec = importlib.util.spec_from_file_location("browser_runtime_identity", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_browser_runtime_identity_sample_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_identity(_load_sample()) == []


def test_wrapper_probe_cannot_claim_doe_runtime_active() -> None:
    checker = _load_checker()
    payload = _load_sample()
    payload["doeRuntimeActive"] = True

    failures = checker.check_identity(payload)

    assert {
        "code": "wrapper_claims_doe_active",
        "path": "doeRuntimeActive",
        "message": "browser wrapper probes cannot claim Doe runtime execution",
    } in failures


def test_runtime_selection_artifact_rejects_selected_runtime_drift() -> None:
    checker = _load_checker()
    payload = {
        **_load_sample(),
        "evidenceSource": "runtime_selection_artifact",
        "selectedRuntime": "doe",
        "executionOwner": "chromium_runtime_selector",
        "doeRuntimeActive": True,
        "webgpuAvailable": True,
        "runtimeSelection": {
            "selectedRuntime": "dawn",
            "fallbackApplied": False,
            "fallbackReasonCode": "",
            "hiddenFallbackAllowed": False,
            "selectorVersion": "browser-runtime-selector-v1",
        },
    }

    failures = checker.check_identity(payload)

    assert {
        "code": "selected_runtime_mismatch",
        "path": "runtimeSelection.selectedRuntime",
        "message": "runtimeSelection.selectedRuntime must match selectedRuntime",
    } in failures


def test_runtime_selection_artifact_requires_explicit_hidden_fallback_false() -> None:
    checker = _load_checker()
    payload = {
        **_load_sample(),
        "evidenceSource": "runtime_selection_artifact",
        "selectedRuntime": "doe",
        "executionOwner": "chromium_runtime_selector",
        "doeRuntimeActive": True,
        "webgpuAvailable": True,
        "runtimeSelection": {
            "selectedRuntime": "doe",
            "fallbackApplied": False,
            "fallbackReasonCode": "",
            "selectorVersion": "browser-runtime-selector-v1",
        },
    }

    failures = checker.check_identity(payload)

    assert {
        "code": "hidden_fallback_not_disabled",
        "path": "runtimeSelection.hiddenFallbackAllowed",
        "message": "hidden fallback must be explicitly false",
    } in failures


def test_runtime_selection_artifact_checks_doe_active_state() -> None:
    checker = _load_checker()
    payload = {
        **_load_sample(),
        "evidenceSource": "runtime_selection_artifact",
        "selectedRuntime": "doe",
        "executionOwner": "chromium_runtime_selector",
        "doeRuntimeActive": False,
        "webgpuAvailable": True,
        "runtimeSelection": {
            "selectedRuntime": "doe",
            "fallbackApplied": False,
            "fallbackReasonCode": "",
            "hiddenFallbackAllowed": False,
            "selectorVersion": "browser-runtime-selector-v1",
        },
    }

    failures = checker.check_identity(payload)

    assert {
        "code": "doe_runtime_active_mismatch",
        "path": "doeRuntimeActive",
        "message": "doeRuntimeActive must match selected runtime and fallback state",
    } in failures
