#!/usr/bin/env python3
"""Tests for browser capture policy checks."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_browser_capture_policy as capture_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "config" / "browser-capture-policy.json"


def _load() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_browser_capture_policy_passes_check() -> None:
    assert capture_policy.check_policy(_load()) == []


def test_browser_capture_policy_requires_all_surfaces() -> None:
    payload = _load()
    payload["surfaces"] = [
        row for row in payload["surfaces"] if row["surfaceId"] != "flight_replay"
    ]

    assert {
        "code": "missing_surface",
        "path": "surfaces",
        "message": "missing capture policy surface flight_replay",
    } in capture_policy.check_policy(payload)


def test_browser_capture_policy_requires_origin_scope() -> None:
    payload = _load()
    payload["surfaces"][0]["originScoped"] = False

    assert {
        "code": "not_origin_scoped",
        "path": "surfaces[0].originScoped",
        "message": "capture surfaces must be origin-scoped",
    } in capture_policy.check_policy(payload)


def test_browser_capture_policy_requires_secure_gate_for_replay() -> None:
    payload = _load()
    payload["surfaces"][0]["permissionGate"] = "devtools_opt_in"

    assert {
        "code": "replay_without_secure_gate",
        "path": "surfaces[0].permissionGate",
        "message": "replay surfaces require secure-context devtools opt-in",
    } in capture_policy.check_policy(payload)


def test_browser_capture_policy_rejects_unknown_permission_gate() -> None:
    payload = _load()
    payload["surfaces"][0]["permissionGate"] = "popup_prompt"

    assert {
        "code": "invalid_permission_gate",
        "path": "surfaces[0].permissionGate",
        "message": "permissionGate must use the browser capture policy taxonomy",
    } in capture_policy.check_policy(payload)


def test_browser_capture_policy_rejects_unknown_artifact_data_policy() -> None:
    payload = _load()
    payload["surfaces"][0]["artifactDataPolicy"] = "raw_snapshots"

    assert {
        "code": "invalid_artifact_data_policy",
        "path": "surfaces[0].artifactDataPolicy",
        "message": "artifact data must be metadata-only or hashed/redacted metadata",
    } in capture_policy.check_policy(payload)


def test_browser_capture_policy_requires_replay_visible_to_developer() -> None:
    payload = _load()
    payload["surfaces"][0]["developerVisible"] = False

    assert {
        "code": "replay_not_developer_visible",
        "path": "surfaces[0].developerVisible",
        "message": "replay surfaces must be developer-visible",
    } in capture_policy.check_policy(payload)
