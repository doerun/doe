#!/usr/bin/env python3
"""Tests for browser shader-link artifacts built from flight recorders."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FLIGHT_RECORDER_SAMPLE = REPO_ROOT / "examples" / "browser-gpu-flight-recorder.sample.json"
SHADER_LINKS_SAMPLE = REPO_ROOT / "examples" / "browser-shader-links.sample.json"
BUILDER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-shader-links.py"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-shader-links.py"


def _load_flight_recorder_sample() -> dict:
    return json.loads(FLIGHT_RECORDER_SAMPLE.read_text(encoding="utf-8"))


def _load_builder():
    spec = importlib.util.spec_from_file_location("browser_shader_links", BUILDER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_browser_shader_links", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shader_link_builder_emits_source_ir_backend_links() -> None:
    builder = _load_builder()

    artifact = builder.build_shader_links(
        _load_flight_recorder_sample(),
        "examples/browser-gpu-flight-recorder.sample.json",
    )

    assert artifact["artifactKind"] == "browser_shader_links"
    assert artifact["linkStatus"] == "pass"
    assert artifact["failureCodes"] == []
    assert artifact["shaders"] == [
        {
            "shaderId": "shader:webgpu_prefix_sum",
            "sourceLanguage": "wgsl",
            "sourcePath": "bench/fixtures/wgsl-corpus/webgpu/sample-prefix-sum.wgsl",
            "sourceSha256": "a8a642a54aaca908b707d20666566db8db62dbb5c9bfd518fbe98925da22c416",
            "irPath": "bench/out/browser-flight-recorder/prefix-sum.ir.json",
            "irSha256": "3" * 64,
            "loweringReceiptPath": "examples/wgsl-lowering-link-receipt.sample.json",
            "loweringReceiptRowId": "webgpu-prefix-sum",
            "backendTarget": "spirv",
            "backendOutputPath": "bench/out/browser-flight-recorder/prefix-sum.spv",
            "backendOutputSha256": "2" * 64,
            "diagnosticStatus": "ok",
        }
    ]


def test_shader_link_builder_reports_missing_backend_anchor() -> None:
    builder = _load_builder()
    sample = _load_flight_recorder_sample()
    sample["shaders"][0].pop("backendOutputPath")

    artifact = builder.build_shader_links(
        sample,
        "examples/browser-gpu-flight-recorder.sample.json",
    )

    assert artifact["linkStatus"] == "fail"
    assert artifact["shaders"] == []
    assert {
        "code": "missing_shader_anchor",
        "severity": "error",
        "source": "browser_shader_links",
        "message": "shader row missing anchors: backendOutputPath",
        "path": "shaders[0]",
    } in artifact["failureCodes"]


def test_shader_link_checker_accepts_sample() -> None:
    checker = _load_checker()
    payload = json.loads(SHADER_LINKS_SAMPLE.read_text(encoding="utf-8"))

    assert checker.check_shader_links(payload, verify_flight_recorder_root=REPO_ROOT) == []


def test_shader_link_checker_verifies_lowering_receipt() -> None:
    checker = _load_checker()
    payload = json.loads(SHADER_LINKS_SAMPLE.read_text(encoding="utf-8"))

    assert checker.check_shader_links(
        payload,
        verify_flight_recorder_root=REPO_ROOT,
        verify_lowering_root=REPO_ROOT,
    ) == []


def test_shader_link_checker_rejects_lowering_receipt_mismatch() -> None:
    checker = _load_checker()
    payload = json.loads(SHADER_LINKS_SAMPLE.read_text(encoding="utf-8"))
    payload["shaders"][0]["backendOutputSha256"] = "9" * 64

    failures = checker.check_shader_links(payload, verify_lowering_root=REPO_ROOT)

    assert {
        "code": "lowering_receipt_hash_mismatch",
        "path": "shaders[0].backendOutputSha256",
        "message": "backendOutputSha256 does not match lowering receipt row webgpu-prefix-sum",
    } in failures


def test_shader_link_checker_requires_source_flight_recorder_shader() -> None:
    checker = _load_checker()
    payload = json.loads(SHADER_LINKS_SAMPLE.read_text(encoding="utf-8"))
    payload["shaders"] = []

    failures = checker.check_shader_links(payload, verify_flight_recorder_root=REPO_ROOT)

    assert {
        "code": "missing_shader_links",
        "path": "shaders",
        "message": "shader links must be non-empty",
    } in failures


def test_shader_link_checker_rejects_flight_recorder_shader_drift() -> None:
    checker = _load_checker()
    payload = json.loads(SHADER_LINKS_SAMPLE.read_text(encoding="utf-8"))
    payload["shaders"][0]["sourceSha256"] = "9" * 64

    failures = checker.check_shader_links(payload, verify_flight_recorder_root=REPO_ROOT)

    assert {
        "code": "flight_recorder_shader_mismatch",
        "path": "shaders[0].sourceSha256",
        "message": (
            "expected sourceSha256='a8a642a54aaca908b707d20666566db8db62dbb5c9bfd518fbe98925da22c416' "
            "from flight recorder, got '9999999999999999999999999999999999999999999999999999999999999999'"
        ),
    } in failures


def test_shader_link_checker_reports_bad_digest() -> None:
    checker = _load_checker()
    payload = json.loads(SHADER_LINKS_SAMPLE.read_text(encoding="utf-8"))
    payload["shaders"][0]["irSha256"] = "not-a-digest"

    failures = checker.check_shader_links(payload)

    assert {
        "code": "invalid_shader_link_hash",
        "path": "shaders[0].irSha256",
        "message": "irSha256 must be sha256 hex",
    } in failures
