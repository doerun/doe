#!/usr/bin/env python3
"""Tests for WGSL corpus manifest materialization."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from bench.tools import check_wgsl_corpus_materialization as check_materialization
from bench.tools import materialize_wgsl_corpus_manifest as corpus


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "config" / "wgsl-browser-corpus.json"
MATERIALIZATION_SAMPLE = REPO_ROOT / "examples" / "wgsl-corpus-materialization.sample.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_wgsl_browser_corpus_manifest_passes_structural_check() -> None:
    assert corpus.check_manifest(_load_manifest()) == []


def test_wgsl_browser_corpus_materializes_normalized_sources() -> None:
    manifest = _load_manifest()
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "materialized"

        receipt = corpus.materialize_manifest(
            manifest,
            manifest_path="config/wgsl-browser-corpus.json",
            out_dir=out_dir,
        )

        assert receipt["materializationStatus"] == "pass"
        assert receipt["failureCodes"] == []
        assert len(receipt["rows"]) == len(manifest["rows"])
        for row in receipt["rows"]:
            materialized_path = Path(row["materializedPath"])
            assert materialized_path.is_file()
            assert corpus.normalized_sha256(materialized_path) == row["normalizedSourceSha256"]
        assert check_materialization.check_receipt(receipt) == []
        assert check_materialization.check_receipt(receipt, Path("/")) == []


def test_wgsl_corpus_materialization_checker_accepts_sample() -> None:
    payload = json.loads(MATERIALIZATION_SAMPLE.read_text(encoding="utf-8"))

    assert check_materialization.check_receipt(payload) == []


def test_wgsl_corpus_materialization_checker_verifies_sample_files() -> None:
    payload = json.loads(MATERIALIZATION_SAMPLE.read_text(encoding="utf-8"))

    assert check_materialization.check_receipt(payload, REPO_ROOT) == []


def test_wgsl_browser_corpus_rejects_unsafe_source_path() -> None:
    manifest = _load_manifest()
    manifest["rows"][0]["sourcePath"] = "../fixtures/basic-fragment.wgsl"

    failures = corpus.check_manifest(manifest)

    assert {
        "code": "unsafe_source_path",
        "path": "rows[0].sourcePath",
        "message": "sourcePath must be repo-relative",
    } in failures


def test_wgsl_corpus_materialization_checker_rejects_unsafe_source_path() -> None:
    payload = json.loads(MATERIALIZATION_SAMPLE.read_text(encoding="utf-8"))
    payload["rows"][0]["sourcePath"] = "/tmp/basic-fragment.wgsl"

    failures = check_materialization.check_receipt(payload)

    assert {
        "code": "unsafe_source_path",
        "path": "rows[0].sourcePath",
        "message": "sourcePath must be repo-relative",
    } in failures


def test_wgsl_corpus_materialization_checker_rejects_materialized_path_escape(tmp_path: Path) -> None:
    payload = json.loads(MATERIALIZATION_SAMPLE.read_text(encoding="utf-8"))
    payload["rows"][0]["materializedPath"] = "../materialized/basic-fragment.wgsl"

    failures = check_materialization.check_receipt(payload, tmp_path)

    assert {
        "code": "unsafe_materialized_path",
        "path": "rows[0].materializedPath",
        "message": "materializedPath must resolve under verify-files-root",
    } in failures


def test_wgsl_corpus_materialization_checker_rejects_hash_mismatch(tmp_path: Path) -> None:
    materialized = tmp_path / "shader.wgsl"
    materialized.write_text("@compute @workgroup_size(1) fn main() {}\n", encoding="utf-8")
    payload = json.loads(MATERIALIZATION_SAMPLE.read_text(encoding="utf-8"))
    payload["rows"] = [
        dict(
            payload["rows"][0],
            materializedPath=str(materialized),
            normalizedSourceSha256="0" * 64,
        )
    ]

    assert any(
        item["code"] == "materialized_hash_mismatch"
        for item in check_materialization.check_receipt(payload, tmp_path)
    )


def test_wgsl_browser_corpus_reports_hash_mismatch() -> None:
    manifest = _load_manifest()
    manifest["rows"][0]["normalizedSourceSha256"] = "0" * 64

    failures = corpus.check_manifest(manifest)

    assert failures[0]["code"] == "source_hash_mismatch"
    assert failures[0]["path"] == "rows[0].normalizedSourceSha256"


def test_wgsl_browser_corpus_reports_missing_category() -> None:
    manifest = _load_manifest()
    manifest["rows"] = [
        row
        for row in manifest["rows"]
        if row["category"] != "game_engine_shader"
    ]

    failures = corpus.check_manifest(manifest)

    assert {
        "code": "missing_category",
        "path": "rows",
        "message": "missing WGSL corpus category game_engine_shader",
    } in failures
