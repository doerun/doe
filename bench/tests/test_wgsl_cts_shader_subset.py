#!/usr/bin/env python3
"""Tests for WGSL CTS shader subset ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import build_wgsl_cts_shader_subset as cts_subset
from bench.tools import check_wgsl_cts_shader_subset as check_cts_subset


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "config" / "wgsl-browser-corpus.json"
CTS_EVIDENCE_PATH = REPO_ROOT / "config" / "webgpu-cts-evidence.json"
SAMPLE_PATH = REPO_ROOT / "examples" / "wgsl-cts-shader-subset.sample.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_cts_evidence() -> dict:
    return json.loads(CTS_EVIDENCE_PATH.read_text(encoding="utf-8"))


def test_wgsl_cts_shader_subset_builds_from_manifest_and_evidence() -> None:
    artifact = cts_subset.build_subset(
        _load_manifest(),
        _load_cts_evidence(),
        manifest_path="config/wgsl-browser-corpus.json",
        cts_evidence_path="config/webgpu-cts-evidence.json",
    )

    assert artifact["subsetStatus"] == "pass"
    assert artifact["failureCodes"] == []
    assert artifact["rows"][0]["shaderId"] == "cts-texture-dimensions"
    assert artifact["rows"][0]["ctsQuery"] == "webgpu:shader,execution,expression,call,builtin,textureDimensions:*"
    assert check_cts_subset.check_subset(artifact) == []


def test_wgsl_cts_shader_subset_checker_accepts_sample() -> None:
    assert check_cts_subset.check_subset(json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))) == []


def test_wgsl_cts_shader_subset_checker_rejects_duplicate_query() -> None:
    artifact = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    artifact["rows"].append(dict(artifact["rows"][0], shaderId="cts-texture-dimensions-copy"))

    assert {
        "code": "duplicate_cts_query",
        "path": "rows[1].ctsQuery",
        "message": "duplicate ctsQuery webgpu:shader,execution,expression,call,builtin,textureDimensions:*",
    } in check_cts_subset.check_subset(artifact)


def test_wgsl_cts_shader_subset_rejects_unsafe_paths() -> None:
    artifact = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    artifact["rows"][0]["sourcePath"] = "../fixture.wgsl"
    artifact["rows"][0]["ctsArtifactPath"] = "/tmp/cts.json"

    failures = check_cts_subset.check_subset(artifact)

    assert {
        "code": "unsafe_source_path",
        "path": "rows[0].sourcePath",
        "message": "sourcePath must be repo-relative",
    } in failures
    assert {
        "code": "unsafe_cts_artifact_path",
        "path": "rows[0].ctsArtifactPath",
        "message": "ctsArtifactPath must be repo-relative",
    } in failures


def test_wgsl_cts_shader_subset_builder_rejects_unsafe_source_path() -> None:
    manifest = _load_manifest()
    for row in manifest["rows"]:
        if row["shaderId"] == "cts-texture-dimensions":
            row["sourcePath"] = "/tmp/texture-dimensions.wgsl"

    artifact = cts_subset.build_subset(
        manifest,
        _load_cts_evidence(),
        manifest_path="config/wgsl-browser-corpus.json",
        cts_evidence_path="config/webgpu-cts-evidence.json",
    )

    assert artifact["subsetStatus"] == "fail"
    assert {
        "code": "unsafe_source_path",
        "path": "rows[5].sourcePath",
        "message": "sourcePath must be repo-relative",
    } in artifact["failureCodes"]


def test_wgsl_cts_shader_subset_reports_missing_cts_evidence() -> None:
    manifest = _load_manifest()
    cts_evidence = _load_cts_evidence()
    cts_evidence["evidence"] = [
        row
        for row in cts_evidence["evidence"]
        if row["query"] != "webgpu:shader,execution,expression,call,builtin,textureDimensions:*"
    ]

    artifact = cts_subset.build_subset(
        manifest,
        cts_evidence,
        manifest_path="config/wgsl-browser-corpus.json",
        cts_evidence_path="config/webgpu-cts-evidence.json",
    )

    assert artifact["subsetStatus"] == "fail"
    assert {
        "code": "missing_cts_evidence",
        "path": "rows[5].provenance.origin",
        "message": "missing CTS evidence for query 'webgpu:shader,execution,expression,call,builtin,textureDimensions:*'",
    } in artifact["failureCodes"]


def test_wgsl_cts_shader_subset_requires_cts_rows() -> None:
    manifest = _load_manifest()
    for row in manifest["rows"]:
        if row["shaderId"] == "cts-texture-dimensions":
            row["provenance"]["sourceKind"] = "repo_fixture"

    artifact = cts_subset.build_subset(
        manifest,
        _load_cts_evidence(),
        manifest_path="config/wgsl-browser-corpus.json",
        cts_evidence_path="config/webgpu-cts-evidence.json",
    )

    assert artifact["subsetStatus"] == "fail"
    assert {
        "code": "missing_cts_shader_row",
        "path": "rows",
        "message": "manifest has no CTS shader subset rows",
    } in artifact["failureCodes"]
