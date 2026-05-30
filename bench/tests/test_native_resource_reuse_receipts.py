#!/usr/bin/env python3
"""Tests for native resource reuse receipt checks."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_native_resource_reuse_receipts as reuse_check


REPO_ROOT = Path(__file__).resolve().parents[2]
RECEIPTS_PATH = REPO_ROOT / "examples" / "native-resource-reuse-receipts.sample.json"


def _load() -> dict:
    return json.loads(RECEIPTS_PATH.read_text(encoding="utf-8"))


def test_native_resource_reuse_receipts_pass_check() -> None:
    assert reuse_check.check_receipts(_load()) == []


def test_native_resource_reuse_receipts_reject_reuse_without_semantics() -> None:
    payload = _load()
    payload["rows"][1]["reuseApplied"] = True

    assert {
        "code": "reuse_without_semantics",
        "path": "rows[1].reuseApplied",
        "message": "reuse cannot be applied unless semanticsAllowReuse=true",
    } in reuse_check.check_receipts(payload)


def test_native_resource_reuse_receipts_require_resource_identity_for_claims() -> None:
    payload = _load()
    payload["rows"][0]["resourceIdentityPreserved"] = False

    assert {
        "code": "resource_identity_not_preserved",
        "path": "rows[0].resourceIdentityPreserved",
        "message": "claimable reuse rows must preserve resource identity",
    } in reuse_check.check_receipts(payload)


def test_native_resource_reuse_receipts_require_command_order_for_claims() -> None:
    payload = _load()
    payload["rows"][0]["commandOrderPreserved"] = False

    assert {
        "code": "command_order_not_preserved",
        "path": "rows[0].commandOrderPreserved",
        "message": "claimable reuse rows must preserve command order",
    } in reuse_check.check_receipts(payload)
