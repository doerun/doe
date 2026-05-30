#!/usr/bin/env python3
"""Tests for the browser GPU scheduler probe checker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-gpu-scheduler.sample.json"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-gpu-scheduler.py"
BUILDER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-gpu-scheduler.py"


def _load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_checker():
    spec = importlib.util.spec_from_file_location("browser_gpu_scheduler", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_browser_gpu_scheduler", BUILDER_PATH)
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
                    "recovery": {
                        "deviceLost": {
                            "pass": True,
                            "promiseAvailable": True,
                            "state": "pending",
                        }
                    },
                    "renderTriangle": {
                        "pass": True,
                    },
                },
                "benches": {
                    "writeBuffer64kbUsPerOp": 12.5,
                    "computeDispatchUsPerOp": 3.5,
                },
            }
        ],
    }


def test_browser_gpu_scheduler_sample_passes_structural_check() -> None:
    checker = _load_checker()

    assert checker.check_probe(_load_sample()) == []


def test_browser_gpu_scheduler_reports_missing_required_surface() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["workClasses"] = [
        work_class
        for work_class in sample["workClasses"]
        if work_class["surface"] != "local_ai"
    ]

    failures = checker.check_probe(sample)

    assert {
        "code": "missing_surface",
        "path": "workClasses",
        "message": "missing surface local_ai",
    } in failures


def test_browser_gpu_scheduler_reports_missing_probe_kind() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["probes"] = [
        probe
        for probe in sample["probes"]
        if probe["probeKind"] != "device_loss"
    ]

    failures = checker.check_probe(sample)

    assert {
        "code": "missing_probe_kind",
        "path": "probes",
        "message": "missing probe kind device_loss",
    } in failures


def test_browser_gpu_scheduler_reports_unknown_work_class() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["probes"][0]["workClassIds"].append("work:missing")

    failures = checker.check_probe(sample)

    assert {
        "code": "unknown_work_class",
        "path": "probes[0].workClassIds[3]",
        "message": "probe references unknown work class 'work:missing'",
    } in failures


def test_browser_gpu_scheduler_rejects_duplicate_ids() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["workClasses"][1]["workClassId"] = sample["workClasses"][0]["workClassId"]
    sample["probes"][1]["probeId"] = sample["probes"][0]["probeId"]

    failures = checker.check_probe(sample)

    assert {
        "code": "duplicate_work_class_id",
        "path": "workClasses[1].workClassId",
        "message": "duplicate workClassId work:webgpu",
    } in failures
    assert {
        "code": "duplicate_probe_id",
        "path": "probes[1].probeId",
        "message": "duplicate probeId probe:priority",
    } in failures


def test_browser_gpu_scheduler_requires_fallback_reason() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["probes"][-1].pop("reasonCode")

    failures = checker.check_probe(sample)

    assert {
        "code": "missing_fallback_reason",
        "path": "probes[5].reasonCode",
        "message": "fallback behavior probe requires reasonCode",
    } in failures


def test_browser_gpu_scheduler_builder_extracts_smoke_runtime_evidence() -> None:
    builder = _load_builder()
    checker = _load_checker()

    artifact = builder.build_probe(
        _smoke_report(),
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "browser-gpu-scheduler-smoke",
    )

    assert artifact["artifactKind"] == "browser_gpu_scheduler_probe"
    assert artifact["runtimeIdentity"] == {
        "runtimeIdentityPath": "browser/chromium/artifacts/smoke.json",
        "selectedRuntime": "doe",
        "fallbackApplied": False,
    }
    assert {item["surface"] for item in artifact["workClasses"]} == {
        "webgpu",
        "canvas",
        "video",
        "css_effects",
        "local_ai",
        "compositor_adjacent",
    }
    assert [probe["probeKind"] for probe in artifact["probes"]] == [
        "priority",
        "fairness",
        "frame_deadline",
        "origin_quota",
        "device_loss",
        "fallback_behavior",
    ]
    assert artifact["probes"][4]["status"] == "pass"
    assert artifact["probes"][5]["status"] == "pass"
    assert artifact["probes"][5]["reasonCode"] == "hidden_fallback_disabled"
    assert checker.check_probe(artifact) == []


def test_browser_gpu_scheduler_builder_marks_hidden_fallback_failure() -> None:
    builder = _load_builder()
    report = _smoke_report()
    report["modeResults"][0]["runtimeSelection"]["fallbackApplied"] = True

    artifact = builder.build_probe(
        report,
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "browser-gpu-scheduler-smoke",
    )

    assert artifact["runtimeIdentity"]["fallbackApplied"] is True
    assert artifact["probes"][5]["status"] == "fail"
    assert artifact["probes"][5]["reasonCode"] == "hidden_fallback_applied"
