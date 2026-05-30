#!/usr/bin/env python3
"""Tests for the Chromium WebGPU integration overlay checker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OVERLAY_PATH = REPO_ROOT / "config" / "webgpu-integration-chromium.json"
CHECKER_PATH = REPO_ROOT / "bench" / "tools" / "check_webgpu_integration_chromium.py"


def _load_overlay() -> dict[str, Any]:
    return json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))


def _load_checker() -> Any:
    spec = importlib.util.spec_from_file_location("webgpu_integration_chromium", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_webgpu_integration_chromium_overlay_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_overlay(_load_overlay()) == []


def test_webgpu_integration_chromium_overlay_links_existing_smoke_artifact() -> None:
    checker = _load_checker()

    assert checker.check_overlay(
        _load_overlay(),
        verify_artifact_root=REPO_ROOT,
    ) == []


def test_webgpu_integration_chromium_requires_core_capability() -> None:
    checker = _load_checker()
    payload = _load_overlay()
    payload["coverage"] = [
        row for row in payload["coverage"]
        if row["capability"] != "requestAdapter"
    ]

    failures = checker.check_overlay(payload)

    assert {
        "code": "missing_required_capability",
        "path": "coverage",
        "message": "missing required capability requestAdapter",
    } in failures


def test_webgpu_integration_chromium_rejects_passing_blocked_row() -> None:
    checker = _load_checker()
    payload = _load_overlay()
    payload["integrationPhase"] = "chromium_runtime_active"
    payload["wireProtocolNotes"]["architecture"] = "DoeCommandDecoder source selector active"
    payload["coverage"][0]["status"] = "passing"
    payload["coverage"][0]["blockedBy"] = "unexpected-blocker"

    failures = checker.check_overlay(payload)

    assert {
        "code": "passing_row_blocked",
        "path": "coverage[0].blockedBy",
        "message": "passing rows must not carry blockedBy",
    } in failures


def test_webgpu_integration_chromium_rejects_passing_before_source_runtime_active() -> None:
    checker = _load_checker()
    payload = _load_overlay()
    payload["coverage"][0]["status"] = "passing"

    failures = checker.check_overlay(payload)

    assert {
        "code": "passing_before_source_runtime_active",
        "path": "coverage[0].status",
        "message": "passing Chromium rows require integrationPhase=chromium_runtime_active",
    } in failures


def test_webgpu_integration_chromium_verifies_smoke_artifact(tmp_path: Path) -> None:
    checker = _load_checker()
    payload = _load_overlay()
    payload["smokeTestArtifact"] = "artifacts/smoke.json"
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "smoke.json").write_text(
        json.dumps({
            "reportKind": "chromium-webgpu-playwright-smoke",
            "benchmarkClass": "diagnostic",
        }),
        encoding="utf-8",
    )

    assert checker.check_overlay(payload, verify_artifact_root=tmp_path) == []


def test_webgpu_integration_chromium_reports_missing_smoke_artifact(tmp_path: Path) -> None:
    checker = _load_checker()
    payload = _load_overlay()
    payload["smokeTestArtifact"] = "artifacts/missing.json"

    failures = checker.check_overlay(payload, verify_artifact_root=tmp_path)

    assert failures == [
        {
            "code": "missing_smoke_artifact_file",
            "path": "smokeTestArtifact",
            "message": f"missing smoke artifact {tmp_path / 'artifacts/missing.json'}",
        }
    ]


def test_webgpu_integration_chromium_rejects_unsafe_smoke_artifact_path(tmp_path: Path) -> None:
    checker = _load_checker()
    payload = _load_overlay()
    payload["smokeTestArtifact"] = "../smoke.json"

    failures = checker.check_overlay(payload, verify_artifact_root=tmp_path)

    assert failures == [
        {
            "code": "unsafe_smoke_artifact_path",
            "path": "smokeTestArtifact",
            "message": "smokeTestArtifact must be repo-relative",
        }
    ]
