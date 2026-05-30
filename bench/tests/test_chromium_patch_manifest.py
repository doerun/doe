#!/usr/bin/env python3
"""Tests for Chromium patch manifest checks."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_chromium_patch_manifest as manifest_check


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "config" / "chromium-patch-manifest.json"
POLICY_PATH = REPO_ROOT / "config" / "chromium-fork-maintenance-policy.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _check(payload: dict) -> list[dict[str, str]]:
    return manifest_check.check_manifest(
        payload,
        _load_policy(),
        root=REPO_ROOT,
        manifest_path=MANIFEST_PATH,
        policy_path=POLICY_PATH,
    )


def test_chromium_patch_manifest_passes_check() -> None:
    assert _check(_load_manifest()) == []


def test_chromium_patch_manifest_rejects_duplicate_patch_ids() -> None:
    payload = _load_manifest()
    payload["patches"][1]["patchId"] = payload["patches"][0]["patchId"]

    assert {
        "code": "duplicate_patch_id",
        "path": "patches[1].patchId",
        "message": "duplicate patchId chromium_app_doe_wrapper",
    } in _check(payload)


def test_chromium_patch_manifest_rejects_forbidden_patch_root() -> None:
    payload = _load_manifest()
    payload["patches"][0]["path"] = "browser/chromium/vendor/downstream.patch"
    payload["patches"][0]["allowedRoot"] = "browser/chromium/"

    failures = _check(payload)

    assert any(item["code"] == "patch_path_forbidden" for item in failures)


def test_chromium_patch_manifest_rejects_missing_evidence_path() -> None:
    payload = _load_manifest()
    payload["patches"][0]["evidencePaths"] = ["bench/out/missing-patch-evidence.json"]

    assert {
        "code": "missing_evidence_path",
        "path": "patches[0].evidencePaths[0]",
        "message": "missing referenced path: bench/out/missing-patch-evidence.json",
    } in _check(payload)


def test_chromium_patch_manifest_rejects_policy_path_mismatch() -> None:
    payload = _load_manifest()
    payload["policyPath"] = "config/other-chromium-policy.json"

    failures = _check(payload)

    assert any(item["code"] == "policy_path_mismatch" for item in failures)
