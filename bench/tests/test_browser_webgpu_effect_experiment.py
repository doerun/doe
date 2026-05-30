#!/usr/bin/env python3
"""Tests for browser WebGPU effect experiment checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-webgpu-effect-experiment.sample.json"
CHECKER_PATH = (
    REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-webgpu-effect-experiment.py"
)
BUILDER_PATH = (
    REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-webgpu-effect-experiment.py"
)


def _load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_checker():
    spec = importlib.util.spec_from_file_location("browser_webgpu_effect_experiment", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_browser_webgpu_effect_experiment", BUILDER_PATH)
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
                "webgpuCanvasApi": {
                    "webgpuContextAvailable": True,
                },
                "smoke": {
                    "renderTriangle": {
                        "pass": True,
                        "centerRgba": [0, 255, 0, 255],
                        "error": None,
                    }
                },
                "benches": {
                    "computeDispatchUsPerOp": 3.5,
                },
            }
        ],
    }


def test_browser_webgpu_effect_experiment_sample_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_experiment(_load_sample()) == []


def test_browser_webgpu_effect_experiment_requires_browser_semantics() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["surfaces"][0]["layoutOwner"] = "doe"

    failures = checker.check_experiment(sample)

    assert {
        "code": "browser_semantics_escaped",
        "path": "surfaces[0].layoutOwner",
        "message": "layoutOwner must remain browser-owned",
    } in failures


def test_browser_webgpu_effect_experiment_reports_unknown_pipeline_surface() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["pipelines"][0]["surfaceIds"].append("surface:missing")

    failures = checker.check_experiment(sample)

    assert {
        "code": "unknown_pipeline_surface",
        "path": "pipelines[0].surfaceIds[2]",
        "message": "pipeline references unknown surface 'surface:missing'",
    } in failures


def test_browser_webgpu_effect_experiment_rejects_duplicate_ids() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["surfaces"][1]["surfaceId"] = sample["surfaces"][0]["surfaceId"]
    sample["pipelines"].append(dict(sample["pipelines"][0]))
    sample["probes"][1]["probeId"] = sample["probes"][0]["probeId"]

    failures = checker.check_experiment(sample)

    assert {
        "code": "duplicate_surface_id",
        "path": "surfaces[1].surfaceId",
        "message": "duplicate surfaceId surface:hero-filter",
    } in failures
    assert {
        "code": "duplicate_pipeline_id",
        "path": "pipelines[1].pipelineId",
        "message": "duplicate pipelineId pipeline:blur-pass",
    } in failures
    assert {
        "code": "duplicate_probe_id",
        "path": "probes[1].probeId",
        "message": "duplicate probeId probe:output-hash",
    } in failures


def test_browser_webgpu_effect_experiment_requires_fallback_reason() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["probes"][2].pop("reasonCode")

    failures = checker.check_experiment(sample)

    assert {
        "code": "missing_fallback_reason",
        "path": "probes[2].reasonCode",
        "message": "fallback behavior probe requires reasonCode",
    } in failures


def test_browser_webgpu_effect_experiment_builder_extracts_smoke_evidence() -> None:
    builder = _load_builder()
    checker = _load_checker()

    artifact = builder.build_experiment(
        _smoke_report(),
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "webgpu-effect-smoke",
    )

    assert artifact["artifactKind"] == "browser_webgpu_effect_experiment"
    assert artifact["runtimeIdentity"] == {
        "runtimeIdentityPath": "browser/chromium/artifacts/smoke.json",
        "selectedRuntime": "doe",
        "fallbackApplied": False,
    }
    assert {surface["sourceKind"] for surface in artifact["surfaces"]} == {
        "canvas_overlay",
        "presentation_filter",
    }
    assert all(surface["layoutOwner"] == "browser" for surface in artifact["surfaces"])
    assert artifact["pipelines"][0]["backendTarget"] == "wgsl"
    assert [probe["probeKind"] for probe in artifact["probes"]] == [
        "output_hash",
        "semantics_boundary",
        "fallback_behavior",
        "frame_timing",
        "security_policy",
    ]
    assert artifact["probes"][0]["status"] == "pass"
    assert artifact["probes"][2]["status"] == "pass"
    assert artifact["probes"][2]["reasonCode"] == "hidden_fallback_disabled"
    assert checker.check_experiment(artifact) == []


def test_browser_webgpu_effect_experiment_builder_marks_failed_render() -> None:
    builder = _load_builder()
    report = _smoke_report()
    report["modeResults"][0]["smoke"]["renderTriangle"] = {
        "pass": False,
        "centerRgba": None,
        "error": "render failed",
    }

    artifact = builder.build_experiment(
        report,
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "webgpu-effect-smoke",
    )

    assert artifact["probes"][0]["status"] == "fail"
    assert artifact["probes"][0]["reasonCode"] == "render_probe_failed"
