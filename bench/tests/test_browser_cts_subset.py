#!/usr/bin/env python3
"""Tests for browser CTS subset checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-cts-subset.sample.json"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-cts-subset.py"
BUILDER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-cts-subset.py"


def _load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_checker():
    spec = importlib.util.spec_from_file_location("browser_cts_subset", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_browser_cts_subset", BUILDER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _smoke_report() -> dict:
    def mode_result(mode: str) -> dict:
        return {
            "mode": mode,
            "runtimeSelection": {
                "selectedRuntime": mode,
                "fallbackApplied": False,
                "hiddenFallbackAllowed": False,
            },
            "webgpuAvailable": True,
            "adapterAvailable": True,
            "smoke": {
                "computeIncrement": {
                    "pass": True,
                },
                "recovery": {
                    "validationError": {
                        "pass": True,
                    }
                },
            },
        }

    return {
        "schemaVersion": 1,
        "reportKind": "chromium-webgpu-playwright-smoke",
        "modeResults": [mode_result("dawn"), mode_result("doe")],
    }


def test_browser_cts_subset_sample_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_subset(_load_sample()) == []


def test_browser_cts_subset_reports_missing_bucket() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["rows"] = [
        row
        for row in sample["rows"]
        if row["bucket"] != "validation"
    ]

    failures = checker.check_subset(sample)

    assert {
        "code": "missing_cts_bucket",
        "path": "rows",
        "message": "missing CTS bucket validation",
    } in failures


def test_browser_cts_subset_requires_dawn_and_doe_lanes() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["browserArtifacts"]["forcedDoeArtifactPath"] = ""

    failures = checker.check_subset(sample)

    assert {
        "code": "missing_browser_lane",
        "path": "browserArtifacts.forcedDoeArtifactPath",
        "message": "missing forced-Doe CTS artifact path",
    } in failures


def test_browser_cts_subset_rejects_unsafe_artifact_paths() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["browserArtifacts"]["dawnArtifactPath"] = "../dawn-cts.json"
    sample["rows"][0]["artifactPath"] = "/tmp/cts-row.json"

    failures = checker.check_subset(sample)

    assert {
        "code": "unsafe_artifact_path",
        "path": "browserArtifacts.dawnArtifactPath",
        "message": "Dawn CTS artifact path must be repo-relative",
    } in failures
    assert {
        "code": "unsafe_artifact_path",
        "path": "rows[0].artifactPath",
        "message": "CTS row artifact path must be repo-relative",
    } in failures


def test_browser_cts_subset_checks_match_status() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["rows"][0]["parityStatus"] = "match"
    sample["rows"][0]["forcedDoeStatus"] = "fail"

    failures = checker.check_subset(sample)

    assert {
        "code": "cts_parity_status_mismatch",
        "path": "rows[0].parityStatus",
        "message": "match parity requires identical Dawn and forced-Doe statuses",
    } in failures


def test_browser_cts_subset_builder_projects_paired_smoke_buckets() -> None:
    builder = _load_builder()
    checker = _load_checker()

    artifact = builder.build_subset(
        _smoke_report(),
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "browser-cts-subset-smoke",
        "browser/chromium/scripts/webgpu-playwright-smoke.mjs",
        "smoke-derived",
    )

    assert artifact["artifactKind"] == "browser_cts_subset"
    assert artifact["browserArtifacts"] == {
        "dawnArtifactPath": "browser/chromium/artifacts/smoke.json#modeResults[dawn]",
        "forcedDoeArtifactPath": "browser/chromium/artifacts/smoke.json#modeResults[doe]",
    }
    assert {row["bucket"] for row in artifact["rows"]} == {
        "adapter",
        "buffer",
        "command_buffer",
        "queue",
        "validation",
        "shader_execution",
    }
    assert all(row["parityStatus"] == "match" for row in artifact["rows"])
    assert checker.check_subset(artifact) == []


def test_browser_cts_subset_builder_marks_missing_mode_diagnostic() -> None:
    builder = _load_builder()
    report = _smoke_report()
    report["modeResults"] = [report["modeResults"][0]]

    artifact = builder.build_subset(
        report,
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "browser-cts-subset-smoke",
        "browser/chromium/scripts/webgpu-playwright-smoke.mjs",
        "smoke-derived",
    )

    assert artifact["rows"][0]["forcedDoeStatus"] == "not_run"
    assert artifact["rows"][0]["parityStatus"] == "diagnostic"
    assert artifact["rows"][0]["reasonCode"] == "smoke_bucket_not_fully_exercised"
