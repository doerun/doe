#!/usr/bin/env python3
"""Tests for browser media path probe checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "examples" / "browser-media-path-probe.sample.json"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-media-path-probe.py"
BUILDER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-media-path-probe.py"


def _load_sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _load_checker():
    spec = importlib.util.spec_from_file_location("browser_media_path_probe", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_browser_media_path_probe", BUILDER_PATH)
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
                "smoke": {
                    "copyExternalImageToTexture": {
                        "pass": True,
                        "topLeftRgba": [0, 255, 0, 255],
                        "sourceType": "ImageBitmap",
                        "attempts": [
                            {
                                "sourceType": "ImageBitmap",
                                "topLeftRgba": [0, 255, 0, 255],
                            }
                        ],
                        "error": None,
                    },
                    "importExternalTexture": {
                        "pass": True,
                        "centerRgba": [255, 0, 0, 255],
                        "error": None,
                    },
                },
            }
        ],
    }


def test_browser_media_path_probe_sample_passes_check() -> None:
    checker = _load_checker()

    assert checker.check_probe(_load_sample()) == []


def test_browser_media_path_probe_requires_capture_policy() -> None:
    checker = _load_checker()
    sample = _load_sample()
    del sample["capturePolicy"]

    assert {
        "code": "missing_capture_policy",
        "path": "capturePolicy",
        "message": "media probes must reference browser capture policy",
    } in checker.check_probe(sample)


def test_browser_media_path_probe_rejects_unsafe_media_source_path() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["mediaSources"][0]["sourcePath"] = "../video-frame.rgba.digest"

    failures = checker.check_probe(sample)

    assert {
        "code": "unsafe_artifact_path",
        "path": "mediaSources[0].sourcePath",
        "message": "media source path must be repo-relative",
    } in failures


def test_browser_media_path_probe_rejects_unsafe_evidence_path() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["probes"][0]["evidencePath"] = "/tmp/media-probe.json"

    failures = checker.check_probe(sample)

    assert {
        "code": "unsafe_artifact_path",
        "path": "probes[0].evidencePath",
        "message": "media probe evidence path must be repo-relative",
    } in failures


def test_browser_media_path_probe_requires_media_capture_surface(tmp_path: Path) -> None:
    checker = _load_checker()
    sample = _load_sample()
    policy = json.loads((REPO_ROOT / "config" / "browser-capture-policy.json").read_text(encoding="utf-8"))
    policy["surfaces"] = [
        surface for surface in policy["surfaces"] if surface["surfaceId"] != "media_path_probe"
    ]
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    sample["capturePolicy"]["capturePolicyPath"] = "policy.json"

    assert {
        "code": "missing_capture_surface",
        "path": "capturePolicy.surfaceId",
        "message": "browser capture policy must define media_path_probe surface",
    } in checker.check_probe(sample, tmp_path)


def test_browser_media_path_probe_reports_missing_probe_kind() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["probes"] = [
        probe
        for probe in sample["probes"]
        if probe["probeKind"] != "shared_texture_import"
    ]

    failures = checker.check_probe(sample)

    assert {
        "code": "missing_probe_kind",
        "path": "probes",
        "message": "missing probe kind shared_texture_import",
    } in failures


def test_browser_media_path_probe_reports_unknown_media_source() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["probes"][0]["mediaSourceIds"].append("media:missing")

    failures = checker.check_probe(sample)

    assert {
        "code": "unknown_media_source",
        "path": "probes[0].mediaSourceIds[1]",
        "message": "probe references unknown media source 'media:missing'",
    } in failures


def test_browser_media_path_probe_requires_unsupported_reason() -> None:
    checker = _load_checker()
    sample = _load_sample()
    sample["probes"][0]["status"] = "unsupported"

    failures = checker.check_probe(sample)

    assert {
        "code": "missing_fallback_reason",
        "path": "probes[0].reasonCode",
        "message": "fallback or unsupported media probe requires reasonCode",
    } in failures


def test_browser_media_path_probe_builder_extracts_smoke_media_results() -> None:
    builder = _load_builder()
    checker = _load_checker()

    artifact = builder.build_probe(
        _smoke_report(),
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "browser-media-path-smoke",
    )

    assert artifact["artifactKind"] == "browser_media_path_probe"
    assert artifact["runtimeIdentity"] == {
        "runtimeIdentityPath": "browser/chromium/artifacts/smoke.json",
        "selectedRuntime": "doe",
        "fallbackApplied": False,
    }
    assert artifact["capturePolicy"] == {
        "capturePolicyPath": "config/browser-capture-policy.json",
        "surfaceId": "media_path_probe",
    }
    assert [probe["probeKind"] for probe in artifact["probes"]] == [
        "gpu_external_texture",
        "copy_external_image_to_texture",
        "shared_texture_import",
    ]
    assert artifact["probes"][0]["status"] == "pass"
    assert artifact["probes"][1]["status"] == "pass"
    assert artifact["probes"][2]["status"] == "unsupported"
    assert artifact["probes"][2]["reasonCode"] == "not_reported_by_smoke"
    assert checker.check_probe(artifact) == []


def test_browser_media_path_probe_builder_marks_unavailable_external_texture() -> None:
    builder = _load_builder()
    report = _smoke_report()
    report["modeResults"][0]["smoke"]["importExternalTexture"] = {
        "pass": False,
        "centerRgba": None,
        "error": "createVideoFrame: Error: VideoFrame is unavailable",
    }

    artifact = builder.build_probe(
        report,
        REPO_ROOT / "browser" / "chromium" / "artifacts" / "smoke.json",
        "doe",
        "browser-media-path-smoke",
    )

    assert artifact["probes"][0]["status"] == "unsupported"
    assert artifact["probes"][0]["reasonCode"] == "browser_capability_unavailable"
