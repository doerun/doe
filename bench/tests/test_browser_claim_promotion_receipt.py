#!/usr/bin/env python3
"""Tests for browser claim promotion receipt checks."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_browser_claim_promotion_receipt as promotion
from bench.tools import build_browser_claim_promotion_receipt as builder


REPO_ROOT = Path(__file__).resolve().parents[2]
RECEIPT_PATH = REPO_ROOT / "examples" / "browser-claim-promotion-receipt.sample.json"


def _load() -> dict:
    return json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))


def _runtime_selection(*, fallback_applied: bool = False) -> dict:
    return {
        "selectionMode": "doe",
        "selectedRuntime": "doe",
        "forcedMode": "doe",
        "fallbackApplied": fallback_applied,
        "fallbackReasonCode": "fallback_applied" if fallback_applied else "",
        "hiddenFallbackAllowed": False,
        "selectorVersion": "browser-runtime-selector-v1",
        "launchArgsHash": "a" * 64,
        "artifactIdentity": {
            "browserExecutablePath": "/tmp/chrome",
            "browserExecutableSha256": "b" * 64,
            "doeLibPath": "/tmp/libwebgpu_doe.dylib",
            "doeLibSha256": "c" * 64,
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _claim_report_fixture(tmp_path: Path, *, fallback_applied: bool = False) -> tuple[Path, Path]:
    policy_path = tmp_path / "browser-claim-policy.json"
    policy_path.write_text("{}\n", encoding="utf-8")
    selection = _runtime_selection(fallback_applied=fallback_applied)
    smoke_path = tmp_path / "window-01.smoke.json"
    layered_path = tmp_path / "window-01.layered.json"
    _write_json(
        smoke_path,
        {
            "runtimeSelections": [selection],
            "modeResults": [{"mode": "doe", "runtimeSelection": selection}],
        },
    )
    _write_json(
        layered_path,
        {
            "runtimeSelections": [selection],
            "modeRunDetails": [{"mode": "doe", "runtimeSelection": selection}],
        },
    )
    claim_report_path = tmp_path / "browser-claim-report.json"
    _write_json(
        claim_report_path,
        {
            "reportKind": "browser-claim-report",
            "comparisonStatus": "comparable",
            "claimStatus": "claimable",
            "policyPath": str(policy_path.resolve()),
            "windows": [
                {
                    "smokeReport": str(smoke_path),
                    "layeredReport": str(layered_path),
                }
            ],
            "failures": [],
        },
    )
    return claim_report_path, policy_path


def test_browser_claim_promotion_receipt_passes_check() -> None:
    assert promotion.check_receipt(_load()) == []


def test_browser_claim_promotion_receipt_sample_verifies_file_hash() -> None:
    assert promotion.check_receipt(_load(), verify_files_root=REPO_ROOT) == []


def test_browser_claim_promotion_receipt_requires_forced_doe() -> None:
    payload = _load()
    payload["artifacts"][0]["mode"] = "auto"

    assert {
        "code": "artifact_not_forced_doe",
        "path": "artifacts[0]",
        "message": "promotion artifacts must be forced-Doe runs",
    } in promotion.check_receipt(payload)


def test_browser_claim_promotion_receipt_rejects_hidden_fallback() -> None:
    payload = _load()
    payload["artifacts"][0]["hiddenFallbackUsed"] = True

    assert {
        "code": "hidden_fallback_used",
        "path": "artifacts[0].hiddenFallbackUsed",
        "message": "promotion artifacts cannot use hidden fallback",
    } in promotion.check_receipt(payload)


def test_browser_claim_promotion_receipt_requires_claim_policy_pass() -> None:
    payload = _load()
    payload["artifacts"][0]["claimPolicyPassed"] = False

    assert {
        "code": "claim_policy_not_passed",
        "path": "artifacts[0].claimPolicyPassed",
        "message": "promotion artifacts must pass browser claim policy",
    } in promotion.check_receipt(payload)


def test_browser_claim_promotion_receipt_builder_promotes_forced_doe_report(tmp_path: Path) -> None:
    claim_report_path, policy_path = _claim_report_fixture(tmp_path)

    receipt = builder.build_receipt(
        [claim_report_path],
        claim_policy_path=policy_path,
        receipt_id="test-receipt",
    )

    assert receipt["promotionStatus"] == "promotable"
    assert receipt["hiddenFallbackCheck"]["passed"] is True
    assert receipt["artifacts"][0]["forcedDoe"] is True
    assert receipt["artifacts"][0]["hiddenFallbackUsed"] is False
    assert promotion.check_receipt(receipt) == []
    assert promotion.check_receipt(receipt, verify_files_root=tmp_path) == []


def test_browser_claim_promotion_receipt_builder_rejects_hidden_fallback(tmp_path: Path) -> None:
    claim_report_path, policy_path = _claim_report_fixture(tmp_path, fallback_applied=True)

    receipt = builder.build_receipt(
        [claim_report_path],
        claim_policy_path=policy_path,
        receipt_id="test-receipt",
    )

    assert receipt["promotionStatus"] == "diagnostic"
    assert receipt["artifacts"][0]["hiddenFallbackUsed"] is True
    assert {
        "code": "hidden_fallback_used",
        "path": "artifacts[0].hiddenFallbackUsed",
        "message": "promotion artifacts cannot use hidden fallback",
    } in promotion.check_receipt(receipt)


def test_browser_claim_promotion_receipt_verifies_artifact_hash(tmp_path: Path) -> None:
    claim_report_path, policy_path = _claim_report_fixture(tmp_path)
    receipt = builder.build_receipt(
        [claim_report_path],
        claim_policy_path=policy_path,
        receipt_id="test-receipt",
    )
    receipt["artifacts"][0]["sha256"] = "0" * 64

    assert any(
        failure["code"] == "artifact_hash_mismatch"
        for failure in promotion.check_receipt(receipt, verify_files_root=tmp_path)
    )


def test_browser_claim_promotion_receipt_rejects_artifact_path_escape(tmp_path: Path) -> None:
    payload = _load()
    payload["artifacts"][0]["path"] = "../claim-report.json"

    failures = promotion.check_receipt(payload, verify_files_root=tmp_path)

    assert {
        "code": "unsafe_artifact_path",
        "path": "artifacts[0].path",
        "message": "artifact path must resolve under verify-files-root: ../claim-report.json",
    } in failures
