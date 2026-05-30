#!/usr/bin/env python3
"""Tests for top-level browser checker artifactKind guards."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Callable


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


def _cases() -> list[tuple[str, str, str, Callable[[Any, dict[str, Any]], list[dict[str, str]]]]]:
    return [
        (
            "check_browser_canvas_webgpu_fusion",
            "browser-canvas-webgpu-fusion.sample.json",
            "browser_canvas_webgpu_fusion_probe",
            lambda module, payload: module.check_probe(payload),
        ),
        (
            "check_browser_cts_subset",
            "browser-cts-subset.sample.json",
            "browser_cts_subset",
            lambda module, payload: module.check_subset(payload),
        ),
        (
            "check_browser_fallback_explanations",
            "browser-fallback-explanations.sample.json",
            "browser_fallback_explanations",
            lambda module, payload: module.check_explanations(payload),
        ),
        (
            "check_browser_gpu_scheduler",
            "browser-gpu-scheduler.sample.json",
            "browser_gpu_scheduler_probe",
            lambda module, payload: module.check_probe(payload),
        ),
        (
            "check_browser_local_ai_workloads",
            "browser-local-ai-workloads.sample.json",
            "browser_local_ai_workloads",
            lambda module, payload: module.check_workloads(payload),
        ),
        (
            "check_browser_media_path_probe",
            "browser-media-path-probe.sample.json",
            "browser_media_path_probe",
            lambda module, payload: module.check_probe(payload),
        ),
        (
            "check_browser_pipeline_cache_receipts",
            "browser-pipeline-cache-receipts.sample.json",
            "browser_pipeline_cache_receipts",
            lambda module, payload: module.check_receipts(payload),
        ),
        (
            "check_browser_recovery_parity",
            "browser-recovery-parity.sample.json",
            "browser_recovery_parity",
            lambda module, payload: module.check_parity(payload),
        ),
        (
            "check_browser_shader_links",
            "browser-shader-links.sample.json",
            "browser_shader_links",
            lambda module, payload: module.check_shader_links(payload),
        ),
        (
            "check_browser_webgpu_effect_experiment",
            "browser-webgpu-effect-experiment.sample.json",
            "browser_webgpu_effect_experiment",
            lambda module, payload: module.check_experiment(payload),
        ),
    ]


def test_browser_checkers_reject_wrong_artifact_kind() -> None:
    for module_name, sample_name, expected_kind, check in _cases():
        script_name = module_name.replace("_", "-") + ".py"
        module = _load_module(module_name, SCRIPTS / script_name)
        payload = _load_sample(sample_name)
        payload["artifactKind"] = "wrong_artifact_kind"

        failures = check(module, payload)

        assert {
            "code": "invalid_artifact_kind",
            "path": "artifactKind",
            "message": f"artifactKind must be {expected_kind}",
        } in failures


def test_browser_checkers_reject_wrong_schema_version() -> None:
    for module_name, sample_name, _expected_kind, check in _cases():
        script_name = module_name.replace("_", "-") + ".py"
        module = _load_module(module_name, SCRIPTS / script_name)
        payload = _load_sample(sample_name)
        payload["schemaVersion"] = 2

        failures = check(module, payload)

        assert {
            "code": "invalid_schema_version",
            "path": "schemaVersion",
            "message": "schemaVersion must be 1",
        } in failures
