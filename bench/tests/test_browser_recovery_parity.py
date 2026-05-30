#!/usr/bin/env python3
"""Tests for browser recovery parity checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-recovery-parity.sample.json"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-recovery-parity.py"
BUILDER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-recovery-parity.py"


def _load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_checker():
    spec = importlib.util.spec_from_file_location("browser_recovery_parity", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_browser_recovery_parity", BUILDER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mode_result(mode: str) -> dict:
    return {
        "mode": mode,
        "runtimeSelection": {
            "selectorVersion": "browser-runtime-selector-v1",
            "selectedRuntime": mode,
            "fallbackApplied": False,
        },
        "smoke": {
            "recovery": {
                "validationError": {
                    "pass": True,
                    "captured": True,
                    "messageCount": 1,
                    "error": None,
                },
                "deviceLost": {
                    "pass": True,
                    "promiseAvailable": True,
                    "error": None,
                },
                "postValidationCompute": {
                    "pass": True,
                    "actual": [2, 3, 4, 5],
                    "expected": [2, 3, 4, 5],
                    "error": None,
                },
            },
        },
    }


def _smoke_report() -> dict:
    return {
        "schemaVersion": 1,
        "reportKind": "chromium-webgpu-playwright-smoke",
        "modeResults": [
            _mode_result("dawn"),
            _mode_result("doe"),
        ],
    }


def test_browser_recovery_parity_sample_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_parity(_load_sample()) == []


def test_browser_recovery_parity_reports_missing_case() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["cases"] = [
        case
        for case in sample["cases"]
        if case["caseKind"] != "device_loss"
    ]

    failures = checker.check_parity(sample)

    assert {
        "code": "missing_case_kind",
        "path": "cases",
        "message": "missing recovery parity case device_loss",
    } in failures


def test_browser_recovery_parity_checks_match_status() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["cases"][0]["parityStatus"] = "match"
    sample["cases"][0]["doeStatus"] = "fail"

    failures = checker.check_parity(sample)

    assert {
        "code": "parity_status_mismatch",
        "path": "cases[0].parityStatus",
        "message": "match parity requires identical Dawn and Doe statuses",
    } in failures


def test_browser_recovery_parity_requires_reason_for_diagnostic() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["cases"][0].pop("reasonCode")

    failures = checker.check_parity(sample)

    assert {
        "code": "missing_reason_code",
        "path": "cases[0].reasonCode",
        "message": "diagnostic or mismatch parity requires reasonCode",
    } in failures


def test_browser_recovery_parity_rejects_unsafe_artifact_paths() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["dawnArtifactPath"] = "/tmp/dawn-recovery.json"
    sample["cases"][0]["evidencePath"] = "../recovery-evidence.json"

    failures = checker.check_parity(sample)

    assert {
        "code": "unsafe_artifact_path",
        "path": "dawnArtifactPath",
        "message": "Dawn recovery artifact path must be repo-relative",
    } in failures
    assert {
        "code": "unsafe_artifact_path",
        "path": "cases[0].evidencePath",
        "message": "recovery evidence path must be repo-relative",
    } in failures


def test_browser_recovery_parity_builder_extracts_paired_smoke_results() -> None:
    builder = _load_builder()
    checker = _load_checker()

    artifact = builder.build_parity(
        _smoke_report(),
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "browser-recovery-parity-smoke",
    )

    assert artifact["artifactKind"] == "browser_recovery_parity"
    assert artifact["runtimeSelector"] == {
        "selectorVersion": "browser-runtime-selector-v1",
        "doeMode": "forced_doe",
        "hiddenFallbackAllowed": False,
    }
    cases = {case["caseKind"]: case for case in artifact["cases"]}
    assert cases["validation_error"]["parityStatus"] == "match"
    assert cases["device_loss"]["parityStatus"] == "match"
    assert cases["recovery"]["parityStatus"] == "match"
    assert cases["crash"]["parityStatus"] == "diagnostic"
    assert cases["crash"]["reasonCode"] == "not_exercised_by_smoke"
    assert checker.check_parity(artifact) == []


def test_browser_recovery_parity_builder_marks_mismatch() -> None:
    builder = _load_builder()
    report = _smoke_report()
    report["modeResults"][1]["smoke"]["recovery"]["postValidationCompute"] = {
        "pass": False,
        "actual": None,
        "expected": [2, 3, 4, 5],
        "error": "compute failed",
    }

    artifact = builder.build_parity(
        report,
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "browser-recovery-parity-smoke",
    )

    cases = {case["caseKind"]: case for case in artifact["cases"]}
    assert cases["recovery"]["dawnStatus"] == "pass"
    assert cases["recovery"]["doeStatus"] == "fail"
    assert cases["recovery"]["parityStatus"] == "mismatch"
    assert cases["recovery"]["reasonCode"] == "post_validation_compute_failed"
