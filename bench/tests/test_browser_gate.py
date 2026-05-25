#!/usr/bin/env python3
"""Tests for browser gate runtime-selection evidence."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bench.browser.browser_gate import validate_runtime_selection


SHA256 = "a" * 64


def _runtime_selection(mode: str = "dawn") -> dict:
    return {
        "selectionMode": mode,
        "selectedRuntime": mode,
        "forcedMode": mode,
        "fallbackApplied": False,
        "fallbackReasonCode": "",
        "hiddenFallbackAllowed": False,
        "selectorVersion": "browser-runtime-selector-v1",
        "launchArgsHash": SHA256,
        "artifactIdentity": {
            "browserExecutablePath": "/tmp/chrome",
            "browserExecutableSha256": SHA256,
            "doeLibPath": "/tmp/libwebgpu_doe.dylib" if mode == "doe" else None,
            "doeLibSha256": SHA256 if mode == "doe" else None,
        },
    }


def test_runtime_selection_requires_browser_executable_hash() -> None:
    payload = _runtime_selection("dawn")
    payload["artifactIdentity"].pop("browserExecutableSha256")

    errors = validate_runtime_selection(payload, "dawn", "smoke dawn")

    assert "smoke dawn artifactIdentity.browserExecutableSha256 must be sha256 hex" in errors


def test_runtime_selection_accepts_browser_executable_hash_for_dawn() -> None:
    assert validate_runtime_selection(_runtime_selection("dawn"), "dawn", "smoke dawn") == []


def test_runtime_selection_accepts_browser_executable_hash_for_doe() -> None:
    assert validate_runtime_selection(_runtime_selection("doe"), "doe", "smoke doe") == []
