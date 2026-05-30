#!/usr/bin/env python3
"""Tests for the browser canvas/WebGPU fusion probe checker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-canvas-webgpu-fusion.sample.json"
CHECKER_PATH = (
    REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-canvas-webgpu-fusion.py"
)
BUILDER_PATH = (
    REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-canvas-webgpu-fusion.py"
)


def _load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_checker():
    spec = importlib.util.spec_from_file_location("browser_canvas_webgpu_fusion", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_browser_canvas_webgpu_fusion", BUILDER_PATH)
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
                },
                "webgpuCanvasApi": {
                    "offscreenCanvasAvailable": True,
                    "webgpuContextAvailable": True,
                    "webgpuContextHasConfigure": True,
                    "webgpuContextHasGetCurrentTexture": True,
                    "preferredCanvasFormatSupported": True,
                    "preferredCanvasFormat": "bgra8unorm",
                },
                "smoke": {
                    "renderTriangle": {
                        "pass": True,
                        "centerRgba": [255, 0, 0, 255],
                        "error": None,
                    },
                },
                "benches": {
                    "writeBuffer64kbUsPerOp": 4.5,
                    "computeDispatchUsPerOp": 7.25,
                },
            }
        ],
    }


def test_canvas_webgpu_fusion_sample_passes_structural_check() -> None:
    checker = _load_checker()

    assert checker.check_probe(_load_sample()) == []


def test_canvas_webgpu_fusion_reports_missing_surface_reference() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["graph"]["nodes"][0]["surfaceId"] = "surface:missing"

    failures = checker.check_probe(sample)

    assert {
        "code": "missing_surface_reference",
        "path": "graph.nodes[0].surfaceId",
        "message": "node references unknown surface 'surface:missing'",
    } in failures


def test_canvas_webgpu_fusion_rejects_duplicate_graph_ids() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["surfaces"][1]["surfaceId"] = sample["surfaces"][0]["surfaceId"]
    sample["graph"]["nodes"][1]["nodeId"] = sample["graph"]["nodes"][0]["nodeId"]

    failures = checker.check_probe(sample)

    assert {
        "code": "duplicate_surface_id",
        "path": "surfaces[1].surfaceId",
        "message": "duplicate surfaceId surface:canvas2d",
    } in failures
    assert {
        "code": "duplicate_node_id",
        "path": "graph.nodes[1].nodeId",
        "message": "duplicate nodeId node:canvas_draw",
    } in failures


def test_canvas_webgpu_fusion_builder_extracts_smoke_canvas_results() -> None:
    builder = _load_builder()
    checker = _load_checker()

    artifact = builder.build_probe(
        _smoke_report(),
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "canvas-webgpu-fusion-smoke",
    )

    assert artifact["artifactKind"] == "browser_canvas_webgpu_fusion_probe"
    assert artifact["runtimeIdentity"] == {
        "runtimeIdentityPath": "browser/chromium/artifacts/smoke.json",
        "selectedRuntime": "doe",
        "fallbackApplied": False,
    }
    assert {surface["kind"] for surface in artifact["surfaces"]} == {
        "canvas_2d",
        "webgpu",
        "image_filter",
        "presentation",
    }
    assert artifact["fallbackReasons"] == []
    assert checker.check_probe(artifact) == []


def test_canvas_webgpu_fusion_builder_records_render_fallback_reason() -> None:
    builder = _load_builder()
    report = _smoke_report()
    report["modeResults"][0]["smoke"]["renderTriangle"] = {
        "pass": False,
        "centerRgba": None,
        "error": "render failed",
    }

    artifact = builder.build_probe(
        report,
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "canvas-webgpu-fusion-smoke",
    )

    assert {
        "surfaceId": "surface:webgpu",
        "reasonCode": "webgpu_render_failed",
        "message": "render failed",
    } in artifact["fallbackReasons"]
