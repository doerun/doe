#!/usr/bin/env python3
"""Validate browser promotion approvals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
VALID_APPROVER_ROLES = {
    "browser_runtime_integration_owner",
    "browser_quality_owner",
    "browser_benchmark_methodology_owner",
    "module_contracts_owner",
    "coordinator",
}
REQUIRED_APPROVER_ROLES = set(VALID_APPROVER_ROLES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approvals",
        default=str(REPO_ROOT / "browser/chromium/bench/workflows/browser-promotion-approvals.json"),
        help="Path to browser promotion approvals JSON.",
    )
    parser.add_argument(
        "--workflows",
        default=str(REPO_ROOT / "browser/chromium/bench/workflows/browser-workflow-manifest.json"),
        help="Path to browser workflow manifest JSON for approval coverage checks.",
    )
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def check_approvals(
    payload: dict[str, Any],
    *,
    workflow_payload: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("schemaVersion") != 2:
        failures.append(
            failure("invalid_schema_version", "schemaVersion", "schemaVersion must be 2")
        )

    required_roles_raw = payload.get("requiredApprovals")
    if not isinstance(required_roles_raw, list) or not required_roles_raw:
        failures.append(
            failure("missing_required_approvals", "requiredApprovals", "requiredApprovals must be non-empty")
        )
        required_roles: set[str] = set()
    else:
        required_roles = set()
        for index, role in enumerate(required_roles_raw):
            if not isinstance(role, str) or not role.strip():
                failures.append(
                    failure(
                        "invalid_required_role",
                        f"requiredApprovals[{index}]",
                        "required approval role must be non-empty",
                    )
                )
                continue
            if role not in VALID_APPROVER_ROLES:
                failures.append(
                    failure(
                        "unknown_required_role",
                        f"requiredApprovals[{index}]",
                        f"unknown required approval role {role}",
                    )
                )
            if role in required_roles:
                failures.append(
                    failure(
                        "duplicate_required_role",
                        f"requiredApprovals[{index}]",
                        f"duplicate required approval role {role}",
                    )
                )
            required_roles.add(role)

    for role in sorted(REQUIRED_APPROVER_ROLES - required_roles):
        failures.append(
            failure(
                "missing_required_role",
                "requiredApprovals",
                f"missing required approval role {role}",
            )
        )

    approvals = payload.get("approvals")
    if not isinstance(approvals, dict):
        return failures + [
            failure("missing_approvals", "approvals", "approvals must be an object")
        ]

    for role in sorted(REQUIRED_APPROVER_ROLES):
        row = approvals.get(role)
        if not isinstance(row, dict):
            failures.append(
                failure("missing_approval", f"approvals.{role}", f"missing approval row {role}")
            )
            continue
        if row.get("approved") is not True:
            failures.append(
                failure(
                    "approval_not_granted",
                    f"approvals.{role}.approved",
                    f"approval not granted for {role}",
                )
            )
        if not _text(row.get("by")):
            failures.append(
                failure("missing_approval_by", f"approvals.{role}.by", f"missing approver for {role}")
            )
        if not _text(row.get("at")):
            failures.append(
                failure("missing_approval_at", f"approvals.{role}.at", f"missing approval timestamp for {role}")
            )

    if workflow_payload is not None:
        failures.extend(check_workflow_approval_coverage(payload, workflow_payload))

    return failures


def check_workflow_approval_coverage(
    approvals_payload: dict[str, Any],
    workflow_payload: dict[str, Any],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    workflow_roles_raw = workflow_payload.get("promotionGateRequiredApprovals")
    if not isinstance(workflow_roles_raw, list) or not workflow_roles_raw:
        return [
            failure(
                "workflow_missing_required_approvals",
                "workflows.promotionGateRequiredApprovals",
                "workflow manifest must declare promotionGateRequiredApprovals",
            )
        ]
    declared_required = set(approvals_payload.get("requiredApprovals", []))
    approvals = approvals_payload.get("approvals", {})
    workflow_roles = set()
    for role in workflow_roles_raw:
        workflow_roles.add(role)
        if role not in declared_required:
            failures.append(
                failure(
                    "workflow_role_not_required",
                    "requiredApprovals",
                    f"workflow-required role {role} is not declared required",
                )
            )
        approval = approvals.get(role) if isinstance(approvals, dict) else None
        if not isinstance(approval, dict) or approval.get("approved") is not True:
            failures.append(
                failure(
                    "workflow_role_not_approved",
                    f"approvals.{role}",
                    f"workflow-required role {role} is not approved",
                )
            )
    for role in sorted(declared_required - workflow_roles):
        failures.append(
            failure(
                "required_role_not_in_workflow",
                "workflows.promotionGateRequiredApprovals",
                f"required approval role {role} is not workflow-required",
            )
        )
    return failures


def main() -> int:
    args = parse_args()
    approvals_path = Path(args.approvals)
    workflow_path = Path(args.workflows)
    failures = check_approvals(
        load_json(approvals_path),
        workflow_payload=load_json(workflow_path),
    )
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_promotion_approvals_check",
        "approvalsPath": str(approvals_path),
        "workflowPath": str(workflow_path),
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser promotion approvals")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser promotion approvals")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
