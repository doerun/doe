#!/usr/bin/env python3
"""Tests for browser workflow governance checkers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
APPROVALS_PATH = REPO_ROOT / "browser" / "chromium" / "bench" / "workflows" / "browser-promotion-approvals.json"
WORKFLOWS_PATH = REPO_ROOT / "browser" / "chromium" / "bench" / "workflows" / "browser-workflow-manifest.json"
APPROVALS_CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-promotion-approvals.py"
WORKFLOWS_CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-workflow-manifest.py"
MILESTONES_PATH = REPO_ROOT / "browser" / "chromium" / "bench" / "workflows" / "browser-milestones.json"
MILESTONES_CHECKER_PATH = REPO_ROOT / "browser" / "chromium" / "scripts" / "check-browser-milestones.py"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_browser_promotion_approvals_pass_check() -> None:
    checker = _load_module(APPROVALS_CHECKER_PATH, "browser_promotion_approvals")

    assert checker.check_approvals(
        _load_json(APPROVALS_PATH),
        workflow_payload=_load_json(WORKFLOWS_PATH),
    ) == []


def test_browser_promotion_approvals_require_all_roles() -> None:
    checker = _load_module(APPROVALS_CHECKER_PATH, "browser_promotion_approvals")
    payload = _load_json(APPROVALS_PATH)
    payload["requiredApprovals"].remove("coordinator")

    failures = checker.check_approvals(payload)

    assert {
        "code": "missing_required_role",
        "path": "requiredApprovals",
        "message": "missing required approval role coordinator",
    } in failures


def test_browser_promotion_approvals_require_workflow_roles_declared_required() -> None:
    checker = _load_module(APPROVALS_CHECKER_PATH, "browser_promotion_approvals")
    payload = _load_json(APPROVALS_PATH)
    payload["requiredApprovals"].remove("browser_quality_owner")

    failures = checker.check_approvals(
        payload,
        workflow_payload=_load_json(WORKFLOWS_PATH),
    )

    assert {
        "code": "workflow_role_not_required",
        "path": "requiredApprovals",
        "message": "workflow-required role browser_quality_owner is not declared required",
    } in failures


def test_browser_promotion_approvals_require_required_roles_in_workflow() -> None:
    checker = _load_module(APPROVALS_CHECKER_PATH, "browser_promotion_approvals")
    workflow_payload = _load_json(WORKFLOWS_PATH)
    workflow_payload["promotionGateRequiredApprovals"].remove("module_contracts_owner")

    failures = checker.check_approvals(
        _load_json(APPROVALS_PATH),
        workflow_payload=workflow_payload,
    )

    assert {
        "code": "required_role_not_in_workflow",
        "path": "workflows.promotionGateRequiredApprovals",
        "message": "required approval role module_contracts_owner is not workflow-required",
    } in failures


def test_browser_promotion_approvals_require_approved_workflow_roles() -> None:
    checker = _load_module(APPROVALS_CHECKER_PATH, "browser_promotion_approvals")
    payload = _load_json(APPROVALS_PATH)
    payload["approvals"]["browser_quality_owner"]["approved"] = False

    failures = checker.check_approvals(
        payload,
        workflow_payload=_load_json(WORKFLOWS_PATH),
    )

    assert {
        "code": "workflow_role_not_approved",
        "path": "approvals.browser_quality_owner",
        "message": "workflow-required role browser_quality_owner is not approved",
    } in failures


def test_browser_workflow_manifest_passes_check() -> None:
    checker = _load_module(WORKFLOWS_CHECKER_PATH, "browser_workflow_manifest")

    assert checker.check_workflow_manifest(_load_json(WORKFLOWS_PATH)) == []


def test_browser_workflow_manifest_rejects_claim_language_without_boundary() -> None:
    checker = _load_module(WORKFLOWS_CHECKER_PATH, "browser_workflow_manifest")
    payload = _load_json(WORKFLOWS_PATH)
    payload["rows"][0]["claimLanguage"] = "Component claim."

    failures = checker.check_workflow_manifest(payload)

    assert {
        "code": "unsafe_claim_language",
        "path": "rows[0].claimLanguage",
        "message": "claimLanguage must state it is never a substitute for L0 parity claims",
    } in failures


def test_browser_workflow_manifest_rejects_required_optional_mismatch() -> None:
    checker = _load_module(WORKFLOWS_CHECKER_PATH, "browser_workflow_manifest")
    payload = _load_json(WORKFLOWS_PATH)
    payload["rows"][0]["requiredStatus"] = "optional"

    failures = checker.check_workflow_manifest(payload)

    assert {
        "code": "required_status_mismatch",
        "path": "rows[0].requiredStatus",
        "message": "required workflow rows must use requiredStatus=ok",
    } in failures


def test_browser_workflow_manifest_requires_module_contracts_owner() -> None:
    checker = _load_module(WORKFLOWS_CHECKER_PATH, "browser_workflow_manifest")
    payload = _load_json(WORKFLOWS_PATH)
    payload["promotionGateRequiredApprovals"].remove("module_contracts_owner")

    failures = checker.check_workflow_manifest(payload)

    assert {
        "code": "missing_required_role",
        "path": "promotionGateRequiredApprovals",
        "message": "missing workflow approval role module_contracts_owner",
    } in failures


def test_browser_workflow_manifest_rejects_component_scope_mismatch() -> None:
    checker = _load_module(WORKFLOWS_CHECKER_PATH, "browser_workflow_manifest")
    payload = _load_json(WORKFLOWS_PATH)
    payload["rows"][0]["claimScope"] = "l2_diagnostic_only"

    failures = checker.check_workflow_manifest(payload)

    assert {
        "code": "component_scope_mismatch",
        "path": "rows[0].claimScope",
        "message": "component workflow rows must use l2_component_only",
    } in failures


def test_browser_workflow_manifest_rejects_duplicate_metrics() -> None:
    checker = _load_module(WORKFLOWS_CHECKER_PATH, "browser_workflow_manifest")
    payload = _load_json(WORKFLOWS_PATH)
    payload["rows"][0]["metrics"] = ["startupMs", "startupMs"]

    failures = checker.check_workflow_manifest(payload)

    assert {
        "code": "duplicate_metric",
        "path": "rows[0].metrics[1]",
        "message": "duplicate metric startupMs",
    } in failures


def test_browser_milestones_reject_evidence_path_escape() -> None:
    checker = _load_module(MILESTONES_CHECKER_PATH, "browser_milestones")
    payload = _load_json(MILESTONES_PATH)
    payload["milestones"][0]["evidence"][0]["path"] = "../AGENTS.md"

    milestones, errors = checker.validate_manifest(payload)
    summary = checker.build_summary(milestones, errors)

    assert "M0 unsafe local evidence path: ../AGENTS.md" in summary["errors"]
