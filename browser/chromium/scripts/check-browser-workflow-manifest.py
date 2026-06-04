#!/usr/bin/env python3
"""Validate browser workflow manifest semantics."""

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
VALID_COMPARABILITY = {"component", "none"}
VALID_REQUIRED_STATUS = {"ok", "optional"}
VALID_CLAIM_SCOPES = {"l2_component_only", "l2_diagnostic_only"}
VISUAL_RESOURCE_TEMPLATE = "fawn_visual_resource"
VISUAL_RESOURCE_PREFIX = "browser/chromium/resources/"
VISUAL_RESOURCE_REQUIRED_METRICS = {"avgFrameMs", "p95FrameMs", "avgFps", "frameCount"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default=str(REPO_ROOT / "browser/chromium/bench/workflows/browser-workflow-manifest.json"),
        help="Path to browser workflow manifest JSON.",
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


def check_workflow_manifest(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("schemaVersion") != 3:
        failures.append(
            failure("invalid_schema_version", "schemaVersion", "schemaVersion must be 3")
        )

    approvals_raw = payload.get("promotionGateRequiredApprovals")
    if not isinstance(approvals_raw, list) or not approvals_raw:
        failures.append(
            failure(
                "missing_required_approvals",
                "promotionGateRequiredApprovals",
                "promotionGateRequiredApprovals must be non-empty",
            )
        )
        approvals: set[str] = set()
    else:
        approvals = set()
        for index, role in enumerate(approvals_raw):
            if not isinstance(role, str) or not role.strip():
                failures.append(
                    failure(
                        "invalid_required_role",
                        f"promotionGateRequiredApprovals[{index}]",
                        "required approval role must be non-empty",
                    )
                )
                continue
            if role not in VALID_APPROVER_ROLES:
                failures.append(
                    failure(
                        "unknown_required_role",
                        f"promotionGateRequiredApprovals[{index}]",
                        f"unknown workflow approval role {role}",
                    )
                )
            if role in approvals:
                failures.append(
                    failure(
                        "duplicate_required_role",
                        f"promotionGateRequiredApprovals[{index}]",
                        f"duplicate workflow approval role {role}",
                    )
                )
            approvals.add(role)

    for role in sorted(REQUIRED_APPROVER_ROLES - approvals):
        failures.append(
            failure(
                "missing_required_role",
                "promotionGateRequiredApprovals",
                f"missing workflow approval role {role}",
            )
        )

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return failures + [
            failure("missing_rows", "rows", "rows must be a non-empty array")
        ]

    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        row_path = f"rows[{index}]"
        if not isinstance(row, dict):
            failures.append(failure("invalid_row", row_path, "workflow row must be an object"))
            continue
        workflow_id = _text(row.get("id"))
        if not workflow_id:
            failures.append(failure("missing_row_id", f"{row_path}.id", "row id must be non-empty"))
        elif workflow_id in seen_ids:
            failures.append(
                failure("duplicate_row_id", f"{row_path}.id", f"duplicate workflow row {workflow_id}")
            )
        else:
            seen_ids.add(workflow_id)

        scenario_template = _text(row.get("scenarioTemplate"))
        for field in ("scenarioTemplate", "description", "claimLanguage"):
            if not _text(row.get(field)):
                failures.append(
                    failure(
                        "missing_row_text",
                        f"{row_path}.{field}",
                        f"workflow row requires non-empty {field}",
                    )
                )

        metrics = row.get("metrics")
        metric_names: set[str] = set()
        if not isinstance(metrics, list) or not metrics:
            failures.append(
                failure("missing_metrics", f"{row_path}.metrics", "metrics must be non-empty")
            )
        else:
            for metric_index, metric in enumerate(metrics):
                metric_name = _text(metric)
                if not metric_name:
                    failures.append(
                        failure(
                            "invalid_metric",
                            f"{row_path}.metrics[{metric_index}]",
                            "metric must be non-empty",
                        )
                    )
                elif metric_name in metric_names:
                    failures.append(
                        failure(
                            "duplicate_metric",
                            f"{row_path}.metrics[{metric_index}]",
                            f"duplicate metric {metric_name}",
                        )
                    )
                metric_names.add(metric_name)

        comparability = row.get("comparabilityExpectation")
        claim_scope = row.get("claimScope")
        required = row.get("required")
        required_status = row.get("requiredStatus")
        claim_language = _text(row.get("claimLanguage")).lower()

        if comparability not in VALID_COMPARABILITY:
            failures.append(
                failure(
                    "invalid_comparability",
                    f"{row_path}.comparabilityExpectation",
                    "comparabilityExpectation must be component or none",
                )
            )
        if required_status not in VALID_REQUIRED_STATUS:
            failures.append(
                failure(
                    "invalid_required_status",
                    f"{row_path}.requiredStatus",
                    "requiredStatus must be ok or optional",
                )
            )
        if claim_scope not in VALID_CLAIM_SCOPES:
            failures.append(
                failure(
                    "invalid_claim_scope",
                    f"{row_path}.claimScope",
                    "claimScope must be l2_component_only or l2_diagnostic_only",
                )
            )
        if not isinstance(required, bool):
            failures.append(
                failure("invalid_required", f"{row_path}.required", "required must be boolean")
            )
        elif required and required_status != "ok":
            failures.append(
                failure(
                    "required_status_mismatch",
                    f"{row_path}.requiredStatus",
                    "required workflow rows must use requiredStatus=ok",
                )
            )
        elif required is False and required_status != "optional":
            failures.append(
                failure(
                    "optional_status_mismatch",
                    f"{row_path}.requiredStatus",
                    "optional workflow rows must use requiredStatus=optional",
                )
            )

        if comparability == "component" and claim_scope != "l2_component_only":
            failures.append(
                failure(
                    "component_scope_mismatch",
                    f"{row_path}.claimScope",
                    "component workflow rows must use l2_component_only",
                )
            )
        if comparability == "none" and claim_scope != "l2_diagnostic_only":
            failures.append(
                failure(
                    "diagnostic_scope_mismatch",
                    f"{row_path}.claimScope",
                    "non-comparable workflow rows must use l2_diagnostic_only",
                )
            )
        if "never a substitute" not in claim_language:
            failures.append(
                failure(
                    "unsafe_claim_language",
                    f"{row_path}.claimLanguage",
                    "claimLanguage must state it is never a substitute for L0 parity claims",
                )
            )

        resource_path = _text(row.get("resourcePath"))
        if scenario_template == VISUAL_RESOURCE_TEMPLATE:
            if not resource_path:
                failures.append(
                    failure(
                        "missing_visual_resource_path",
                        f"{row_path}.resourcePath",
                        "fawn visual workflow rows require resourcePath",
                    )
                )
            elif (
                not resource_path.startswith(VISUAL_RESOURCE_PREFIX)
                or not resource_path.endswith(".html")
                or ".." in resource_path
            ):
                failures.append(
                    failure(
                        "invalid_visual_resource_path",
                        f"{row_path}.resourcePath",
                        "resourcePath must be a browser/chromium/resources/*.html path",
                    )
                )
            elif not (REPO_ROOT / resource_path).is_file():
                failures.append(
                    failure(
                        "missing_visual_resource",
                        f"{row_path}.resourcePath",
                        f"resourcePath does not exist: {resource_path}",
                    )
                )
            missing_metrics = sorted(VISUAL_RESOURCE_REQUIRED_METRICS - metric_names)
            if missing_metrics:
                failures.append(
                    failure(
                        "missing_visual_metrics",
                        f"{row_path}.metrics",
                        "fawn visual workflow rows require "
                        + ", ".join(sorted(VISUAL_RESOURCE_REQUIRED_METRICS)),
                    )
                )
            for selector_field in (
                "statusSelector",
                "frameSelector",
                "workloadSelector",
                "adapterSelector",
            ):
                if selector_field in row and not _text(row.get(selector_field)):
                    failures.append(
                        failure(
                            "invalid_visual_selector",
                            f"{row_path}.{selector_field}",
                            "optional visual selectors must be non-empty strings",
                        )
                    )
        elif resource_path:
            failures.append(
                failure(
                    "unexpected_resource_path",
                    f"{row_path}.resourcePath",
                    "resourcePath is only valid for fawn_visual_resource rows",
                )
            )

    return failures


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    failures = check_workflow_manifest(load_json(manifest_path))
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_workflow_manifest_check",
        "manifestPath": str(manifest_path),
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser workflow manifest")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser workflow manifest")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
