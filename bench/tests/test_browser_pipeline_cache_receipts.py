#!/usr/bin/env python3
"""Tests for browser pipeline cache receipt artifacts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKLOADS_SAMPLE = REPO_ROOT / "examples" / "browser-local-ai-workloads.sample.json"
RECEIPTS_SAMPLE = REPO_ROOT / "examples" / "browser-pipeline-cache-receipts.sample.json"
BUILDER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "build-browser-pipeline-cache-receipts.py"
CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-pipeline-cache-receipts.py"


def _load_workloads_sample() -> dict:
    return json.loads(WORKLOADS_SAMPLE.read_text(encoding="utf-8"))


def _load_builder():
    spec = importlib.util.spec_from_file_location("browser_pipeline_cache_receipts", BUILDER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_browser_pipeline_cache_receipts", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pipeline_cache_receipt_builder_emits_workload_receipts() -> None:
    builder = _load_builder()

    artifact = builder.build_cache_receipts(
        _load_workloads_sample(),
        "examples/browser-local-ai-workloads.sample.json",
    )

    assert artifact["artifactKind"] == "browser_pipeline_cache_receipts"
    assert artifact["sourceWorkloadsPath"] == "examples/browser-local-ai-workloads.sample.json"
    assert artifact["receiptStatus"] == "pass"
    assert artifact["failureCodes"] == []
    assert len(artifact["receipts"]) == 5
    assert artifact["receipts"][0] == {
        "receiptId": "cache:local-ai:embedding",
        "workloadId": "local-ai:embedding",
        "workloadKind": "embedding",
        "shaderId": "shader:embedding",
        "sourceSha256": "b000000000000000000000000000000000000000000000000000000000000001",
        "irSha256": "e000000000000000000000000000000000000000000000000000000000000001",
        "backendOutputSha256": "f000000000000000000000000000000000000000000000000000000000000001",
        "cacheKey": "cache:embedding",
        "cacheState": "created",
        "pipelineCreationPath": "bench/out/browser-local-ai/embedding.pipeline.json",
        "creationStatus": "created",
        "fallbackApplied": False,
        "hiddenFallbackAllowed": False,
    }


def test_pipeline_cache_receipt_builder_reports_missing_cache_field() -> None:
    builder = _load_builder()
    sample = _load_workloads_sample()
    sample["workloads"][0]["pipelineCache"].pop("cacheKey")

    artifact = builder.build_cache_receipts(sample)

    assert artifact["receiptStatus"] == "fail"
    assert artifact["receipts"] == []
    assert {
        "code": "missing_cache_receipt_field",
        "severity": "error",
        "source": "browser_pipeline_cache_receipts",
        "message": "missing cache receipt field cacheKey",
        "path": "workloads[0].pipelineCache.cacheKey",
    } in artifact["failureCodes"]


def test_pipeline_cache_receipt_builder_reports_missing_fallback_reason() -> None:
    builder = _load_builder()
    sample = _load_workloads_sample()
    sample["workloads"][0]["fallbackStatus"]["fallbackApplied"] = True

    artifact = builder.build_cache_receipts(sample)

    assert artifact["receiptStatus"] == "fail"
    assert {
        "code": "missing_fallback_reason",
        "severity": "error",
        "source": "browser_pipeline_cache_receipts",
        "message": "applied fallback requires reasonCode",
        "path": "workloads[0].fallbackStatus.reasonCode",
    } in artifact["failureCodes"]


def test_pipeline_cache_receipt_checker_accepts_sample() -> None:
    checker = _load_checker()
    payload = json.loads(RECEIPTS_SAMPLE.read_text(encoding="utf-8"))

    assert checker.check_receipts(payload, REPO_ROOT) == []


def test_pipeline_cache_receipt_checker_reports_cache_status_mismatch() -> None:
    checker = _load_checker()
    payload = json.loads(RECEIPTS_SAMPLE.read_text(encoding="utf-8"))
    payload["receipts"][0]["cacheState"] = "hit"
    payload["receipts"][0]["creationStatus"] = "created"

    failures = checker.check_receipts(payload)

    assert {
        "code": "cache_creation_status_mismatch",
        "path": "receipts[0].creationStatus",
        "message": "cache hit must use creationStatus=reused",
    } in failures


def test_pipeline_cache_receipt_checker_requires_every_source_workload() -> None:
    checker = _load_checker()
    payload = json.loads(RECEIPTS_SAMPLE.read_text(encoding="utf-8"))
    payload["receipts"] = payload["receipts"][:-1]

    failures = checker.check_receipts(payload, REPO_ROOT)

    assert {
        "code": "missing_workload_receipt",
        "path": "receipts",
        "message": "missing pipeline cache receipt for source workload local-ai:model-inference",
    } in failures


def test_pipeline_cache_receipt_checker_rejects_unsafe_source_workload_path() -> None:
    checker = _load_checker()
    payload = json.loads(RECEIPTS_SAMPLE.read_text(encoding="utf-8"))
    payload["sourceWorkloadsPath"] = "../browser-local-ai-workloads.sample.json"

    failures = checker.check_receipts(payload, REPO_ROOT)

    assert {
        "code": "unsafe_source_workloads_path",
        "path": "sourceWorkloadsPath",
        "message": "sourceWorkloadsPath must be repo-relative",
    } in failures


def test_pipeline_cache_receipt_checker_reports_invalid_source_workload_json(tmp_path: Path) -> None:
    checker = _load_checker()
    payload = json.loads(RECEIPTS_SAMPLE.read_text(encoding="utf-8"))
    source = tmp_path / "workloads.json"
    source.write_text("[]\n", encoding="utf-8")
    payload["sourceWorkloadsPath"] = "workloads.json"

    failures = checker.check_receipts(payload, tmp_path)

    assert any(
        failure["code"] == "invalid_source_workloads"
        and failure["path"] == "sourceWorkloadsPath"
        for failure in failures
    )


def test_pipeline_cache_receipt_checker_rejects_shader_identity_drift() -> None:
    checker = _load_checker()
    payload = json.loads(RECEIPTS_SAMPLE.read_text(encoding="utf-8"))
    payload["receipts"][0]["irSha256"] = "0" * 64

    failures = checker.check_receipts(payload, REPO_ROOT)

    assert any(
        failure["code"] == "receipt_workload_mismatch"
        and failure["path"] == "receipts[0].irSha256"
        for failure in failures
    )
