#!/usr/bin/env python3
"""Tests for browser local AI workload receipt checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-local-ai-workloads.sample.json"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-local-ai-workloads.py"
BUILDER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-local-ai-workloads.py"


def _load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_checker():
    spec = importlib.util.spec_from_file_location("browser_local_ai_workloads", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_browser_local_ai_workloads", BUILDER_PATH)
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
                },
                "smoke": {
                    "computeIncrement": {
                        "pass": True,
                        "actual": [2, 3, 4, 5],
                        "expected": [2, 3, 4, 5],
                        "error": None,
                    }
                },
                "benches": {
                    "computeDispatchUsPerOp": 3.5,
                },
            }
        ],
    }


def test_browser_local_ai_workloads_sample_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_workloads(_load_sample()) == []


def test_browser_local_ai_workloads_reports_missing_workload_kind() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["workloads"] = [
        workload
        for workload in sample["workloads"]
        if workload["workloadKind"] != "video_transform"
    ]

    failures = checker.check_workloads(sample)

    assert {
        "code": "missing_workload_kind",
        "path": "workloads",
        "message": "missing workload kind video_transform",
    } in failures


def test_browser_local_ai_workloads_reports_missing_shader_identity() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["workloads"][0]["shaderIdentity"].pop("backendOutputSha256")

    failures = checker.check_workloads(sample)

    assert {
        "code": "missing_receipt_field",
        "path": "workloads[0].shaderIdentity.backendOutputSha256",
        "message": "missing receipt field backendOutputSha256",
    } in failures


def test_browser_local_ai_workloads_rejects_duplicate_workload_ids() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["workloads"][1]["workloadId"] = sample["workloads"][0]["workloadId"]

    failures = checker.check_workloads(sample)

    assert {
        "code": "duplicate_workload_id",
        "path": "workloads[1].workloadId",
        "message": "duplicate workloadId local-ai:embedding",
    } in failures


def test_browser_local_ai_workloads_requires_fallback_reason() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["workloads"][0]["fallbackStatus"]["fallbackApplied"] = True

    failures = checker.check_workloads(sample)

    assert {
        "code": "missing_fallback_reason",
        "path": "workloads[0].fallbackStatus.reasonCode",
        "message": "applied fallback requires reasonCode",
    } in failures


def test_browser_local_ai_workloads_builder_extracts_smoke_compute_evidence() -> None:
    builder = _load_builder()
    checker = _load_checker()

    artifact = builder.build_workloads(
        _smoke_report(),
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "browser-local-ai-smoke",
    )

    assert artifact["artifactKind"] == "browser_local_ai_workloads"
    assert artifact["runtimeIdentity"] == {
        "runtimeIdentityPath": "browser/chromium/artifacts/smoke.json",
        "selectedRuntime": "doe",
        "fallbackApplied": False,
    }
    assert [row["workloadKind"] for row in artifact["workloads"]] == [
        "embedding",
        "ranking",
        "image_transform",
        "video_transform",
        "model_inference",
    ]
    assert all(row["pipelineCache"]["cacheState"] == "created" for row in artifact["workloads"])
    assert all(row["shaderIdentity"]["irSha256"] for row in artifact["workloads"])
    assert all(row["shaderIdentity"]["backendOutputSha256"] for row in artifact["workloads"])
    assert all(row["inputContract"]["redaction"] == "hashed" for row in artifact["workloads"])
    assert all(row["fallbackStatus"]["hiddenFallbackAllowed"] is False for row in artifact["workloads"])
    assert checker.check_workloads(artifact) == []


def test_browser_local_ai_workloads_builder_marks_hidden_fallback() -> None:
    builder = _load_builder()
    report = _smoke_report()
    report["modeResults"][0]["runtimeSelection"]["fallbackApplied"] = True

    artifact = builder.build_workloads(
        report,
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "browser-local-ai-smoke",
    )

    assert artifact["runtimeIdentity"]["fallbackApplied"] is True
    assert artifact["workloads"][0]["fallbackStatus"] == {
        "fallbackApplied": True,
        "hiddenFallbackAllowed": False,
        "reasonCode": "hidden_fallback_applied",
    }
