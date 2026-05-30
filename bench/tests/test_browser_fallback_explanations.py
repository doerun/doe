#!/usr/bin/env python3
"""Tests for browser fallback explanation checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-fallback-explanations.sample.json"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-fallback-explanations.py"
BUILDER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-fallback-explanations.py"


def _load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_checker():
    spec = importlib.util.spec_from_file_location("browser_fallback_explanations", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_browser_fallback_explanations", BUILDER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _smoke_report() -> dict:
    return {
        "schemaVersion": 1,
        "reportKind": "chromium-webgpu-playwright-smoke",
        "modeResults": [
            {
                "mode": "doe",
                "runtimeSelection": {
                    "selectedRuntime": "doe",
                    "fallbackApplied": False,
                    "hiddenFallbackAllowed": False,
                    "fallbackReasonCode": "",
                },
                "webgpuAvailable": True,
                "adapterAvailable": True,
            }
        ],
    }


class Args:
    mode = "doe"
    explanation_set_id = "browser-fallback-smoke"
    taxonomy = "config/browser-unsupported-reason-taxonomy.json"
    canvas_webgpu_fusion = ""
    media_path_probe = ""
    gpu_scheduler = ""
    webgpu_effect_experiment = ""
    local_ai_workloads = ""
    pipeline_cache_receipts = ""
    shader_links = ""


def test_browser_fallback_explanations_sample_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_explanations(_load_sample()) == []


def test_browser_fallback_explanations_rejects_hidden_fallback() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["explanations"][0]["hiddenFallbackAllowed"] = True

    failures = checker.check_explanations(sample)

    assert {
        "code": "hidden_fallback_allowed",
        "path": "explanations[0].hiddenFallbackAllowed",
        "message": "hidden fallback must be false",
    } in failures


def test_browser_fallback_explanations_rejects_unsafe_evidence_path() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["explanations"][0]["evidencePath"] = "../runtime-identity.json"

    failures = checker.check_explanations(sample)

    assert {
        "code": "unsafe_artifact_path",
        "path": "explanations[0].evidencePath",
        "message": "fallback explanation evidence path must be repo-relative",
    } in failures


def test_browser_fallback_explanations_require_developer_action() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["explanations"][0]["developerAction"] = ""

    failures = checker.check_explanations(sample)

    assert {
        "code": "missing_developer_action",
        "path": "explanations[0].developerAction",
        "message": "explanation requires developerAction",
    } in failures


def test_browser_fallback_explanations_rejects_unknown_reason_code() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["explanations"][0]["reasonCode"] = "unknown_reason"

    failures = checker.check_explanations(sample)

    assert {
        "code": "unknown_reason_code",
        "path": "explanations[0].reasonCode",
        "message": "reasonCode 'unknown_reason' is not defined in browser unsupported reason taxonomy",
    } in failures


def test_browser_fallback_explanations_check_fallback_status() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["explanations"][0]["fallbackApplied"] = True

    failures = checker.check_explanations(sample)

    assert {
        "code": "fallback_status_mismatch",
        "path": "explanations[0].status",
        "message": "applied fallback requires status=fallback",
    } in failures


def test_browser_fallback_explanations_builder_emits_unsupported_artifact_rows() -> None:
    builder = _load_builder()
    checker = _load_checker()

    artifact = builder.build_explanations(
        _smoke_report(),
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        Args(),
    )

    assert artifact["artifactKind"] == "browser_fallback_explanations"
    assert artifact["taxonomyPath"] == "config/browser-unsupported-reason-taxonomy.json"
    assert artifact["runtimeIdentity"] == {
        "runtimeIdentityPath": "browser/chromium/artifacts/smoke.json",
        "selectedRuntime": "doe",
        "fallbackApplied": False,
    }
    assert [row["capability"] for row in artifact["explanations"]] == [
        "webgpu_runtime",
        "canvas_fusion",
        "external_texture",
        "scheduler",
        "webgpu_effect",
        "local_ai",
        "pipeline_cache",
        "shader_link",
    ]
    assert artifact["explanations"][0]["status"] == "supported"
    assert artifact["explanations"][1]["status"] == "unsupported"
    assert artifact["explanations"][1]["reasonCode"] == "canvas_fusion_artifact_missing"
    assert checker.check_explanations(artifact) == []


def test_browser_fallback_explanations_builder_marks_runtime_fallback() -> None:
    builder = _load_builder()
    report = _smoke_report()
    report["modeResults"][0]["runtimeSelection"]["fallbackApplied"] = True
    report["modeResults"][0]["runtimeSelection"]["fallbackReasonCode"] = "profile_denylisted"

    artifact = builder.build_explanations(
        report,
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        Args(),
    )

    assert artifact["runtimeIdentity"]["fallbackApplied"] is True
    assert artifact["explanations"][0]["status"] == "fallback"
    assert artifact["explanations"][0]["fallbackApplied"] is True
    assert artifact["explanations"][0]["reasonCode"] == "profile_denylisted"
