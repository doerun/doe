#!/usr/bin/env python3
"""Tests for browser artifact identity coverage checks."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from bench.tools import check_browser_artifact_identity_coverage as coverage


REPO_ROOT = Path(__file__).resolve().parents[2]
COVERAGE_PATH = REPO_ROOT / "config" / "browser-artifact-identity-coverage.json"


def _load() -> dict:
    return json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))


def test_browser_artifact_identity_coverage_passes_check() -> None:
    assert coverage.check_coverage(_load(), root=REPO_ROOT) == []


def test_browser_artifact_identity_coverage_reports_missing_anchor(tmp_path: Path) -> None:
    manifest = copy.deepcopy(_load())
    artifact = json.loads((REPO_ROOT / "examples" / "browser-media-path-probe.sample.json").read_text(encoding="utf-8"))
    del artifact["runtimeIdentity"]["runtimeIdentityPath"]
    artifact_path = tmp_path / "browser-media-path-probe.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    manifest["artifacts"] = [
        {
            "artifactPath": "browser-media-path-probe.json",
            "kindField": "artifactKind",
            "expectedKind": "browser_media_path_probe",
            "identityMode": "runtime_identity_anchor",
            "requiredPointers": ["/runtimeIdentity/runtimeIdentityPath"],
        }
    ]

    assert {
        "code": "missing_identity_anchor",
        "path": "browser-media-path-probe.json/runtimeIdentity/runtimeIdentityPath",
        "message": "required identity anchor is missing or empty",
    } in coverage.check_coverage(manifest, root=tmp_path)


def test_browser_artifact_identity_coverage_reports_kind_mismatch(tmp_path: Path) -> None:
    manifest = copy.deepcopy(_load())
    artifact = json.loads((REPO_ROOT / "examples" / "browser-media-path-probe.sample.json").read_text(encoding="utf-8"))
    artifact["artifactKind"] = "wrong_kind"
    artifact_path = tmp_path / "browser-media-path-probe.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    manifest["artifacts"] = [
        {
            "artifactPath": "browser-media-path-probe.json",
            "kindField": "artifactKind",
            "expectedKind": "browser_media_path_probe",
            "identityMode": "runtime_identity_anchor",
            "requiredPointers": ["/runtimeIdentity/runtimeIdentityPath"],
        }
    ]

    assert {
        "code": "artifact_kind_mismatch",
        "path": "artifacts[0].expectedKind",
        "message": "browser-media-path-probe.json has artifactKind='wrong_kind'",
    } in coverage.check_coverage(manifest, root=tmp_path)
