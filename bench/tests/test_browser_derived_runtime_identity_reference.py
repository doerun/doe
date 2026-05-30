#!/usr/bin/env python3
"""Tests for derived browser artifact runtime identity reference checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "browser" / "chromium" / "scripts"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_sample(name: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_derived_browser_artifacts_verify_runtime_identity_reference() -> None:
    canvas = _load_module("check_browser_canvas_webgpu_fusion", SCRIPTS / "check-browser-canvas-webgpu-fusion.py")
    media = _load_module("check_browser_media_path_probe", SCRIPTS / "check-browser-media-path-probe.py")
    scheduler = _load_module("check_browser_gpu_scheduler", SCRIPTS / "check-browser-gpu-scheduler.py")
    effect = _load_module("check_browser_webgpu_effect_experiment", SCRIPTS / "check-browser-webgpu-effect-experiment.py")
    local_ai = _load_module("check_browser_local_ai_workloads", SCRIPTS / "check-browser-local-ai-workloads.py")
    fallback = _load_module("check_browser_fallback_explanations", SCRIPTS / "check-browser-fallback-explanations.py")
    pipeline = _load_module("check_browser_pipeline_cache_receipts", SCRIPTS / "check-browser-pipeline-cache-receipts.py")

    assert canvas.check_probe(_load_sample("browser-canvas-webgpu-fusion.sample.json"), REPO_ROOT) == []
    assert media.check_probe(_load_sample("browser-media-path-probe.sample.json"), REPO_ROOT, REPO_ROOT) == []
    assert scheduler.check_probe(_load_sample("browser-gpu-scheduler.sample.json"), REPO_ROOT) == []
    assert effect.check_experiment(_load_sample("browser-webgpu-effect-experiment.sample.json"), REPO_ROOT) == []
    assert local_ai.check_workloads(_load_sample("browser-local-ai-workloads.sample.json"), REPO_ROOT) == []
    assert fallback.check_explanations(_load_sample("browser-fallback-explanations.sample.json"), REPO_ROOT, REPO_ROOT) == []
    assert pipeline.check_receipts(_load_sample("browser-pipeline-cache-receipts.sample.json"), REPO_ROOT, REPO_ROOT) == []


def test_derived_browser_artifact_rejects_runtime_identity_drift() -> None:
    local_ai = _load_module("check_browser_local_ai_workloads", SCRIPTS / "check-browser-local-ai-workloads.py")
    payload = _load_sample("browser-local-ai-workloads.sample.json")
    payload["runtimeIdentity"]["selectedRuntime"] = "doe"

    failures = local_ai.check_workloads(payload, REPO_ROOT)

    assert {
        "code": "runtime_identity_reference_mismatch",
        "path": "runtimeIdentity",
        "message": "runtimeIdentity selectedRuntime/fallbackApplied must match referenced runtime evidence",
    } in failures
