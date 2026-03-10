#!/usr/bin/env python3
"""Validate browser benchmark superset projection and optional layered report coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

VALID_PROJECTION_CLASSES = {"high", "medium", "non_projectable"}
VALID_LAYER_TARGETS = {"l1_browser_api", "l0_only"}
VALID_COMPARABILITY = {"strict", "component", "none"}
VALID_REQUIRED_STATUS = {"ok", "not_applicable"}
VALID_OPTIONAL_REQUIRED_STATUS = {"ok", "optional"}
VALID_L1_CLAIM_SCOPE = {"l1_strict_candidate", "l1_component_only", "l0_only_no_claim"}
VALID_L2_CLAIM_SCOPE = {"l2_component_only", "l2_diagnostic_only"}
VALID_RUNTIME_STATUS = {"ok", "fail", "unsupported", "l0_only"}
VALID_RUNTIME_STATUS_CODES = {
    "ok": {"ok"},
    "fail": {"browser_launch_failed", "mode_setup_failed", "mode_execution_failed", "scenario_runtime_error"},
    "unsupported": {
        "adapter_null",
        "api_unsupported",
        "launch_surface_unavailable",
        "mode_execution_unavailable",
        "runtime_mode_unavailable",
        "sandbox_constraint",
        "scenario_template_unknown",
        "webgpu_unavailable",
    },
    "l0_only": {"l0_only"},
}
PROMOTION_APPROVER_ROLES = {
    "browser_runtime_integration_owner",
    "browser_quality_owner",
    "browser_benchmark_methodology_owner",
    "module_contracts_owner",
    "coordinator",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workloads",
        default=str(REPO_ROOT / "bench/workloads.amd.vulkan.superset.json"),
        help="Path to core workload JSON.",
    )
    parser.add_argument(
        "--manifest",
        default=str(
            REPO_ROOT
            / "nursery/fawn-browser/bench/generated/browser_projection_manifest.json"
        ),
        help="Path to generated browser projection manifest JSON.",
    )
    parser.add_argument(
        "--workflows",
        default=str(
            REPO_ROOT / "nursery/fawn-browser/bench/workflows/browser-workflow-manifest.json"
        ),
        help="Path to browser workflow manifest JSON.",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Optional layered browser report JSON for coverage checks.",
    )
    parser.add_argument(
        "--require-modes",
        default="",
        help="Comma-separated runtime modes required in report coverage checks (e.g. dawn,doe).",
    )
    parser.add_argument(
        "--promotion-approvals",
        default=str(
            REPO_ROOT
            / "nursery/fawn-browser/bench/workflows/browser-promotion-approvals.json"
        ),
        help="Path to promotion approval JSON used when --require-promotion-approvals is set.",
    )
    parser.add_argument(
        "--require-promotion-approvals",
        action="store_true",
        help="Require Track B contracts owner and coordinator approvals for promotion candidates.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Emit result JSON instead of text summary.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing non-empty string: {label}")
    return value


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"missing bool: {label}")
    return value


def require_hash_hex(value: Any, label: str) -> str:
    text = require_string(value, label)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"invalid sha256 hex: {label}")
    return text


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_sha256(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def resolve_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


def parse_workloads(workloads_payload: dict[str, Any]) -> list[dict[str, str]]:
    workloads_raw = workloads_payload.get("workloads")
    if not isinstance(workloads_raw, list) or not workloads_raw:
        raise ValueError("invalid workloads payload: missing non-empty workloads[]")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, workload_raw in enumerate(workloads_raw):
        if not isinstance(workload_raw, dict):
            raise ValueError(f"invalid workloads[{index}] object")
        workload_id = require_string(workload_raw.get("id"), f"workloads[{index}].id")
        name = require_string(workload_raw.get("name"), f"workloads[{index}].name")
        domain = require_string(workload_raw.get("domain"), f"workloads[{index}].domain")
        if workload_id in seen:
            raise ValueError(f"duplicate workload id: {workload_id}")
        seen.add(workload_id)
        rows.append({"id": workload_id, "name": name, "domain": domain})
    return rows


def parse_projection_manifest(manifest_payload: dict[str, Any]) -> dict[str, Any]:
    schema_version = manifest_payload.get("schemaVersion")
    if schema_version != 2:
        raise ValueError(f"invalid manifest schemaVersion: expected 2, got {schema_version}")

    manifest = {
        "generatedAt": require_string(manifest_payload.get("generatedAt"), "manifest.generatedAt"),
        "sourceWorkloadsPath": require_string(
            manifest_payload.get("sourceWorkloadsPath"), "manifest.sourceWorkloadsPath"
        ),
        "sourceWorkloadsSha256": require_hash_hex(
            manifest_payload.get("sourceWorkloadsSha256"), "manifest.sourceWorkloadsSha256"
        ),
        "rulesPath": require_string(manifest_payload.get("rulesPath"), "manifest.rulesPath"),
        "rulesSha256": require_hash_hex(manifest_payload.get("rulesSha256"), "manifest.rulesSha256"),
        "projectionContractHash": require_hash_hex(
            manifest_payload.get("projectionContractHash"), "manifest.projectionContractHash"
        ),
    }

    source_count = manifest_payload.get("sourceWorkloadCount")
    if not isinstance(source_count, int) or source_count <= 0:
        raise ValueError("manifest.sourceWorkloadCount must be a positive integer")
    manifest["sourceWorkloadCount"] = source_count

    rows_raw = manifest_payload.get("rows")
    if not isinstance(rows_raw, list) or not rows_raw:
        raise ValueError("invalid manifest payload: missing non-empty rows[]")

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, row_raw in enumerate(rows_raw):
        if not isinstance(row_raw, dict):
            raise ValueError(f"invalid manifest rows[{index}] object")

        source_workload_id = require_string(
            row_raw.get("sourceWorkloadId"), f"rows[{index}].sourceWorkloadId"
        )
        row = {
            "sourceWorkloadId": source_workload_id,
            "sourceWorkloadName": require_string(
                row_raw.get("sourceWorkloadName"), f"rows[{index}].sourceWorkloadName"
            ),
            "domain": require_string(row_raw.get("domain"), f"rows[{index}].domain"),
            "projectionClass": require_string(
                row_raw.get("projectionClass"), f"rows[{index}].projectionClass"
            ),
            "layerTarget": require_string(
                row_raw.get("layerTarget"), f"rows[{index}].layerTarget"
            ),
            "scenarioTemplate": require_string(
                row_raw.get("scenarioTemplate"), f"rows[{index}].scenarioTemplate"
            ),
            "comparabilityExpectation": require_string(
                row_raw.get("comparabilityExpectation"),
                f"rows[{index}].comparabilityExpectation",
            ),
            "requiredStatus": require_string(
                row_raw.get("requiredStatus"), f"rows[{index}].requiredStatus"
            ),
            "claimScope": require_string(row_raw.get("claimScope"), f"rows[{index}].claimScope"),
            "claimLanguage": require_string(
                row_raw.get("claimLanguage"), f"rows[{index}].claimLanguage"
            ),
            "projectionNote": require_string(
                row_raw.get("projectionNote"), f"rows[{index}].projectionNote"
            ),
        }

        if source_workload_id in seen_ids:
            raise ValueError(f"duplicate sourceWorkloadId in manifest: {source_workload_id}")
        seen_ids.add(source_workload_id)

        if row["projectionClass"] not in VALID_PROJECTION_CLASSES:
            raise ValueError(
                f"invalid projectionClass for {source_workload_id}: {row['projectionClass']}"
            )
        if row["layerTarget"] not in VALID_LAYER_TARGETS:
            raise ValueError(f"invalid layerTarget for {source_workload_id}: {row['layerTarget']}")
        if row["comparabilityExpectation"] not in VALID_COMPARABILITY:
            raise ValueError(
                "invalid comparabilityExpectation "
                f"for {source_workload_id}: {row['comparabilityExpectation']}"
            )
        if row["requiredStatus"] not in VALID_REQUIRED_STATUS:
            raise ValueError(
                f"invalid requiredStatus for {source_workload_id}: {row['requiredStatus']}"
            )
        if row["claimScope"] not in VALID_L1_CLAIM_SCOPE:
            raise ValueError(f"invalid claimScope for {source_workload_id}: {row['claimScope']}")

        if row["projectionClass"] in {"high", "medium"}:
            if row["layerTarget"] != "l1_browser_api":
                raise ValueError(
                    f"{source_workload_id} must target l1_browser_api for {row['projectionClass']}"
                )
            if row["scenarioTemplate"] == "none":
                raise ValueError(
                    f"{source_workload_id} must have non-none scenarioTemplate for {row['projectionClass']}"
                )
            if row["requiredStatus"] != "ok":
                raise ValueError(f"{source_workload_id} must use requiredStatus=ok")
        if row["projectionClass"] == "non_projectable":
            if row["layerTarget"] != "l0_only":
                raise ValueError(f"{source_workload_id} must be l0_only for non_projectable")
            if row["requiredStatus"] != "not_applicable":
                raise ValueError(
                    f"{source_workload_id} non_projectable must use requiredStatus=not_applicable"
                )
            if row["comparabilityExpectation"] != "none":
                raise ValueError(
                    f"{source_workload_id} non_projectable must use comparabilityExpectation=none"
                )
            if row["claimScope"] != "l0_only_no_claim":
                raise ValueError(f"{source_workload_id} non_projectable must use l0_only_no_claim")

        if row["comparabilityExpectation"] == "strict" and row["claimScope"] != "l1_strict_candidate":
            raise ValueError(f"{source_workload_id} strict comparability requires l1_strict_candidate")
        if row["comparabilityExpectation"] == "component" and row["claimScope"] != "l1_component_only":
            raise ValueError(f"{source_workload_id} component comparability requires l1_component_only")
        if row["comparabilityExpectation"] == "none" and row["claimScope"] != "l0_only_no_claim":
            raise ValueError(f"{source_workload_id} none comparability requires l0_only_no_claim")

        rows.append(row)

    manifest["rows"] = rows
    return manifest


def parse_workflow_manifest(workflows_payload: dict[str, Any]) -> dict[str, Any]:
    schema_version = workflows_payload.get("schemaVersion")
    if schema_version != 3:
        raise ValueError(f"invalid workflow schemaVersion: expected 3, got {schema_version}")

    required_approvals_raw = workflows_payload.get("promotionGateRequiredApprovals")
    if not isinstance(required_approvals_raw, list) or not required_approvals_raw:
        raise ValueError("workflow manifest missing promotionGateRequiredApprovals[]")
    required_approvals: list[str] = []
    for index, role in enumerate(required_approvals_raw):
        role_value = require_string(role, f"promotionGateRequiredApprovals[{index}]")
        if role_value not in PROMOTION_APPROVER_ROLES:
            raise ValueError(f"invalid promotion approver role: {role_value}")
        if role_value in required_approvals:
            raise ValueError(f"duplicate promotion approver role: {role_value}")
        required_approvals.append(role_value)

    rows_raw = workflows_payload.get("rows")
    if not isinstance(rows_raw, list) or not rows_raw:
        raise ValueError("invalid workflow payload: missing non-empty rows[]")

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, row_raw in enumerate(rows_raw):
        if not isinstance(row_raw, dict):
            raise ValueError(f"invalid workflow rows[{index}] object")

        workflow_id = require_string(row_raw.get("id"), f"workflow.rows[{index}].id")
        if workflow_id in seen_ids:
            raise ValueError(f"duplicate workflow id: {workflow_id}")
        seen_ids.add(workflow_id)

        scenario_template = require_string(
            row_raw.get("scenarioTemplate"), f"workflow.rows[{index}].scenarioTemplate"
        )
        description = require_string(
            row_raw.get("description"), f"workflow.rows[{index}].description"
        )
        comparability = require_string(
            row_raw.get("comparabilityExpectation"),
            f"workflow.rows[{index}].comparabilityExpectation",
        )
        if comparability not in {"component", "none"}:
            raise ValueError(
                f"invalid workflow comparabilityExpectation for {workflow_id}: {comparability}"
            )

        metrics = row_raw.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            raise ValueError(f"workflow metrics must be non-empty array for {workflow_id}")
        for metric_index, metric_name in enumerate(metrics):
            require_string(metric_name, f"workflow.rows[{index}].metrics[{metric_index}]")

        required = require_bool(row_raw.get("required"), f"workflow.rows[{index}].required")
        required_status = require_string(
            row_raw.get("requiredStatus"), f"workflow.rows[{index}].requiredStatus"
        )
        if required_status not in VALID_OPTIONAL_REQUIRED_STATUS:
            raise ValueError(
                f"invalid workflow requiredStatus for {workflow_id}: {required_status}"
            )
        if required and required_status != "ok":
            raise ValueError(f"workflow {workflow_id} required=true must use requiredStatus=ok")
        if not required and required_status != "optional":
            raise ValueError(
                f"workflow {workflow_id} required=false must use requiredStatus=optional"
            )

        claim_scope = require_string(
            row_raw.get("claimScope"), f"workflow.rows[{index}].claimScope"
        )
        if claim_scope not in VALID_L2_CLAIM_SCOPE:
            raise ValueError(f"invalid workflow claimScope for {workflow_id}: {claim_scope}")
        claim_language = require_string(
            row_raw.get("claimLanguage"), f"workflow.rows[{index}].claimLanguage"
        )

        if comparability == "component" and claim_scope != "l2_component_only":
            raise ValueError(f"workflow {workflow_id} component comparability requires l2_component_only")
        if comparability == "none" and claim_scope != "l2_diagnostic_only":
            raise ValueError(f"workflow {workflow_id} none comparability requires l2_diagnostic_only")

        rows.append(
            {
                "id": workflow_id,
                "scenarioTemplate": scenario_template,
                "description": description,
                "comparabilityExpectation": comparability,
                "metrics": metrics,
                "required": required,
                "requiredStatus": required_status,
                "claimScope": claim_scope,
                "claimLanguage": claim_language,
            }
        )

    return {
        "requiredApprovals": required_approvals,
        "rows": rows,
    }


def parse_promotion_approvals(approvals_payload: dict[str, Any]) -> dict[str, Any]:
    schema_version = approvals_payload.get("schemaVersion")
    if schema_version != 2:
        raise ValueError(f"invalid promotion approvals schemaVersion: {schema_version}")

    required_roles_raw = approvals_payload.get("requiredApprovals")
    if not isinstance(required_roles_raw, list) or not required_roles_raw:
        raise ValueError("promotion approvals missing requiredApprovals[]")
    required_roles: list[str] = []
    for index, role in enumerate(required_roles_raw):
        role_value = require_string(role, f"requiredApprovals[{index}]")
        if role_value not in PROMOTION_APPROVER_ROLES:
            raise ValueError(f"invalid required approval role: {role_value}")
        if role_value in required_roles:
            raise ValueError(f"duplicate required approval role: {role_value}")
        required_roles.append(role_value)

    approvals_raw = approvals_payload.get("approvals")
    if not isinstance(approvals_raw, dict):
        raise ValueError("promotion approvals missing approvals object")

    approvals: dict[str, dict[str, Any]] = {}
    for role in PROMOTION_APPROVER_ROLES:
        role_raw = approvals_raw.get(role)
        if not isinstance(role_raw, dict):
            raise ValueError(f"promotion approvals missing role object: {role}")
        approvals[role] = {
            "approved": require_bool(role_raw.get("approved"), f"approvals.{role}.approved"),
            "by": require_string(role_raw.get("by"), f"approvals.{role}.by")
            if role_raw.get("approved")
            else str(role_raw.get("by", "")),
            "at": require_string(role_raw.get("at"), f"approvals.{role}.at")
            if role_raw.get("approved")
            else str(role_raw.get("at", "")),
        }

    return {
        "requiredApprovals": required_roles,
        "approvals": approvals,
    }


def check_projection_completeness(
    workload_rows: list[dict[str, str]], manifest_rows: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []

    workloads_by_id = {row["id"]: row for row in workload_rows}
    manifest_by_id = {row["sourceWorkloadId"]: row for row in manifest_rows}

    if len(workload_rows) != len(manifest_rows):
        errors.append(
            "projection row count mismatch: "
            f"workloads={len(workload_rows)} manifest={len(manifest_rows)}"
        )

    workload_ids = set(workloads_by_id.keys())
    manifest_ids = set(manifest_by_id.keys())
    missing = sorted(workload_ids - manifest_ids)
    extras = sorted(manifest_ids - workload_ids)
    if missing:
        errors.append(f"manifest missing workload ids: {', '.join(missing)}")
    if extras:
        errors.append(f"manifest has unknown workload ids: {', '.join(extras)}")

    for workload_id in sorted(workload_ids & manifest_ids):
        workload = workloads_by_id[workload_id]
        manifest = manifest_by_id[workload_id]

        if workload["domain"] != manifest["domain"]:
            errors.append(
                f"domain mismatch for {workload_id}: workloads={workload['domain']} manifest={manifest['domain']}"
            )

        if manifest["projectionClass"] in {"high", "medium"}:
            if manifest["layerTarget"] != "l1_browser_api":
                errors.append(
                    f"{workload_id}: high/medium row must target l1_browser_api "
                    f"(found {manifest['layerTarget']})"
                )
            if manifest["scenarioTemplate"] == "none":
                errors.append(f"{workload_id}: high/medium row has scenarioTemplate=none")

        if manifest["projectionClass"] == "non_projectable":
            if manifest["layerTarget"] != "l0_only":
                errors.append(f"{workload_id}: non_projectable row must target l0_only")

    return errors


def check_projection_hash_sync(
    manifest: dict[str, Any],
    workloads_path: Path,
) -> list[str]:
    errors: list[str] = []

    manifest_workload_path = resolve_path(manifest["sourceWorkloadsPath"])
    if manifest_workload_path != workloads_path:
        errors.append(
            "manifest sourceWorkloadsPath drift: "
            f"manifest={manifest_workload_path} requested={workloads_path}"
        )

    if not workloads_path.exists():
        errors.append(f"workloads path not found: {workloads_path}")
        return errors

    current_workloads_hash = file_sha256(workloads_path)
    if current_workloads_hash != manifest["sourceWorkloadsSha256"]:
        errors.append(
            "source workload hash mismatch: "
            f"manifest={manifest['sourceWorkloadsSha256']} current={current_workloads_hash}"
        )

    rules_path = resolve_path(manifest["rulesPath"])
    if not rules_path.exists():
        errors.append(f"rules path not found: {rules_path}")
        return errors

    current_rules_hash = file_sha256(rules_path)
    if current_rules_hash != manifest["rulesSha256"]:
        errors.append(
            "rules hash mismatch: "
            f"manifest={manifest['rulesSha256']} current={current_rules_hash}"
        )

    expected_projection_hash = payload_sha256(
        {
            "sourceWorkloadsSha256": manifest["sourceWorkloadsSha256"],
            "rulesSha256": manifest["rulesSha256"],
            "rows": manifest["rows"],
        }
    )
    if expected_projection_hash != manifest["projectionContractHash"]:
        errors.append(
            "projectionContractHash mismatch: "
            f"manifest={manifest['projectionContractHash']} computed={expected_projection_hash}"
        )

    if manifest["sourceWorkloadCount"] != len(manifest["rows"]):
        errors.append(
            "manifest sourceWorkloadCount mismatch: "
            f"sourceWorkloadCount={manifest['sourceWorkloadCount']} rows={len(manifest['rows'])}"
        )

    return errors


def parse_required_modes(value: str) -> list[str]:
    if not value.strip():
        return []
    modes = [segment.strip() for segment in value.split(",") if segment.strip()]
    for mode in modes:
        if mode not in {"dawn", "doe"}:
            raise ValueError(f"invalid mode in --require-modes: {mode}")
    return modes


def check_mode_result(
    mode_result: dict[str, Any],
    row_label: str,
    mode: str,
) -> list[str]:
    errors: list[str] = []

    status = mode_result.get("status")
    status_code = mode_result.get("statusCode")
    if status not in VALID_RUNTIME_STATUS:
        errors.append(f"{row_label}: invalid status for mode '{mode}': {status}")
        return errors
    if not isinstance(status_code, str) or not status_code.strip():
        errors.append(f"{row_label}: missing statusCode for mode '{mode}'")
        return errors
    if status_code not in VALID_RUNTIME_STATUS_CODES[status]:
        errors.append(
            f"{row_label}: invalid statusCode '{status_code}' for mode '{mode}' and status '{status}'"
        )
    return errors


def check_report_coverage(
    report_payload: dict[str, Any],
    manifest: dict[str, Any],
    workflow_manifest: dict[str, Any],
    required_modes: list[str],
) -> list[str]:
    errors: list[str] = []

    report_kind = report_payload.get("reportKind")
    if report_kind != "browser-layered-diagnostic":
        errors.append(f"reportKind must be browser-layered-diagnostic (found {report_kind})")

    report_projection_hash = report_payload.get("projectionContractHash")
    if report_projection_hash != manifest["projectionContractHash"]:
        errors.append(
            "report projectionContractHash mismatch: "
            f"report={report_projection_hash} manifest={manifest['projectionContractHash']}"
        )

    env_evidence = report_payload.get("browserEnvironmentEvidence")
    if not isinstance(env_evidence, dict):
        errors.append("report missing browserEnvironmentEvidence object")

    mode_order = report_payload.get("modeOrder")
    if not isinstance(mode_order, list):
        errors.append("report missing modeOrder[]")
        mode_order = []
    else:
        for index, mode in enumerate(mode_order):
            if mode not in {"dawn", "doe"}:
                errors.append(f"modeOrder[{index}] invalid mode: {mode}")

    for mode in required_modes:
        if mode not in mode_order:
            errors.append(f"required mode missing from modeOrder: {mode}")

    mode_run_details_raw = report_payload.get("modeRunDetails")
    mode_run_details: dict[str, dict[str, Any]] = {}
    if not isinstance(mode_run_details_raw, list):
        errors.append("report missing modeRunDetails[]")
    else:
        for index, detail in enumerate(mode_run_details_raw):
            if not isinstance(detail, dict):
                errors.append(f"modeRunDetails[{index}] is not an object")
                continue
            detail_mode = detail.get("mode")
            if detail_mode not in {"dawn", "doe"}:
                errors.append(f"modeRunDetails[{index}] has invalid mode: {detail_mode}")
                continue
            mode_run_details[str(detail_mode)] = detail

    for mode in required_modes:
        detail = mode_run_details.get(mode)
        if detail is None:
            errors.append(f"modeRunDetails missing required mode: {mode}")
            continue
        runtime_evidence = detail.get("runtimeEvidence")
        if not isinstance(runtime_evidence, dict):
            errors.append(f"modeRunDetails[{mode}] missing runtimeEvidence object")
            continue
        if runtime_evidence.get("modeRequested") != mode:
            errors.append(f"modeRunDetails[{mode}] runtimeEvidence.modeRequested mismatch")
        if not isinstance(runtime_evidence.get("pageTargetKind"), str):
            errors.append(f"modeRunDetails[{mode}] missing runtimeEvidence.pageTargetKind")
        if not isinstance(runtime_evidence.get("browserVersion"), str):
            errors.append(f"modeRunDetails[{mode}] missing runtimeEvidence.browserVersion")
        if not isinstance(runtime_evidence.get("userAgent"), str):
            errors.append(f"modeRunDetails[{mode}] missing runtimeEvidence.userAgent")

    report_l1 = report_payload.get("l1")
    report_l2 = report_payload.get("l2")
    if not isinstance(report_l1, dict):
        return errors + ["report missing object field l1"]
    if not isinstance(report_l2, dict):
        return errors + ["report missing object field l2"]

    report_l1_rows_raw = report_l1.get("rows")
    report_l2_rows_raw = report_l2.get("rows")
    if not isinstance(report_l1_rows_raw, list):
        return errors + ["report.l1 missing array field rows"]
    if not isinstance(report_l2_rows_raw, list):
        return errors + ["report.l2 missing array field rows"]

    report_l1_rows: dict[str, dict[str, Any]] = {}
    for index, row_raw in enumerate(report_l1_rows_raw):
        if not isinstance(row_raw, dict):
            errors.append(f"report.l1.rows[{index}] is not an object")
            continue
        workload_id = row_raw.get("sourceWorkloadId")
        if not isinstance(workload_id, str) or not workload_id.strip():
            errors.append(f"report.l1.rows[{index}] missing sourceWorkloadId")
            continue
        report_l1_rows[workload_id] = row_raw

    report_l2_rows: dict[str, dict[str, Any]] = {}
    for index, row_raw in enumerate(report_l2_rows_raw):
        if not isinstance(row_raw, dict):
            errors.append(f"report.l2.rows[{index}] is not an object")
            continue
        workflow_id = row_raw.get("id")
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            errors.append(f"report.l2.rows[{index}] missing id")
            continue
        report_l2_rows[workflow_id] = row_raw

    manifest_rows = manifest["rows"]
    required_l1_ids = [
        row["sourceWorkloadId"]
        for row in manifest_rows
        if row["projectionClass"] in {"high", "medium"}
    ]

    for manifest_row in manifest_rows:
        workload_id = manifest_row["sourceWorkloadId"]
        report_row = report_l1_rows.get(workload_id)
        if report_row is None:
            if workload_id in required_l1_ids:
                errors.append(f"report missing required L1 row: {workload_id}")
            continue
        if report_row.get("claimScope") != manifest_row["claimScope"]:
            errors.append(f"L1 row claimScope drift for {workload_id}")
        if report_row.get("requiredStatus") != manifest_row["requiredStatus"]:
            errors.append(f"L1 row requiredStatus drift for {workload_id}")

        if required_modes:
            runtimes = report_row.get("runtimes")
            if not isinstance(runtimes, dict):
                errors.append(f"report row missing runtimes object: {workload_id}")
                continue
            for mode in required_modes:
                mode_result = runtimes.get(mode)
                if not isinstance(mode_result, dict):
                    errors.append(
                        f"report row missing required mode '{mode}' result: {workload_id}"
                    )
                    continue
                errors.extend(check_mode_result(mode_result, f"L1:{workload_id}", mode))

    workflow_rows = workflow_manifest["rows"]
    required_workflow_ids = [row["id"] for row in workflow_rows if row["required"]]
    for workflow_row in workflow_rows:
        workflow_id = workflow_row["id"]
        report_row = report_l2_rows.get(workflow_id)
        if report_row is None:
            if workflow_id in required_workflow_ids:
                errors.append(f"report missing required workflow row: {workflow_id}")
            continue

        if report_row.get("claimScope") != workflow_row["claimScope"]:
            errors.append(f"L2 row claimScope drift for {workflow_id}")
        if report_row.get("requiredStatus") != workflow_row["requiredStatus"]:
            errors.append(f"L2 row requiredStatus drift for {workflow_id}")

        if required_modes:
            runtimes = report_row.get("runtimes")
            if not isinstance(runtimes, dict):
                errors.append(f"workflow row missing runtimes object: {workflow_id}")
                continue
            for mode in required_modes:
                mode_result = runtimes.get(mode)
                if not isinstance(mode_result, dict):
                    errors.append(
                        f"workflow row missing required mode '{mode}' result: {workflow_id}"
                    )
                    continue
                errors.extend(check_mode_result(mode_result, f"L2:{workflow_id}", mode))

    return errors


def check_promotion_approvals(
    approvals: dict[str, Any],
    workflow_manifest: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    workflow_required = workflow_manifest["requiredApprovals"]
    approval_required = approvals["requiredApprovals"]
    for role in workflow_required:
        if role not in approval_required:
            errors.append(f"promotion approvals missing required role declaration: {role}")

        role_approval = approvals["approvals"].get(role)
        if not isinstance(role_approval, dict):
            errors.append(f"promotion approvals missing role object: {role}")
            continue
        if not role_approval.get("approved"):
            errors.append(f"promotion approval not granted: {role}")
            continue
        if not isinstance(role_approval.get("by"), str) or not role_approval["by"].strip():
            errors.append(f"promotion approval missing 'by' for {role}")
        if not isinstance(role_approval.get("at"), str) or not role_approval["at"].strip():
            errors.append(f"promotion approval missing 'at' for {role}")
    return errors


def summarize(manifest_rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "rowCount": len(manifest_rows),
        "high": 0,
        "medium": 0,
        "non_projectable": 0,
        "l1_browser_api": 0,
        "l0_only": 0,
    }
    for row in manifest_rows:
        summary[row["projectionClass"]] = summary.get(row["projectionClass"], 0) + 1
        summary[row["layerTarget"]] = summary.get(row["layerTarget"], 0) + 1
    return summary


def main() -> int:
    args = parse_args()

    workloads_path = Path(args.workloads).resolve()
    manifest_path = Path(args.manifest).resolve()
    workflows_path = Path(args.workflows).resolve()

    workloads_payload = load_json(workloads_path)
    manifest_payload = load_json(manifest_path)
    workflows_payload = load_json(workflows_path)

    workload_rows = parse_workloads(workloads_payload)
    manifest = parse_projection_manifest(manifest_payload)
    workflow_manifest = parse_workflow_manifest(workflows_payload)

    errors: list[str] = []
    errors.extend(check_projection_completeness(workload_rows, manifest["rows"]))
    errors.extend(check_projection_hash_sync(manifest, workloads_path))

    required_modes = parse_required_modes(args.require_modes)
    if args.report:
        report_payload = load_json(Path(args.report).resolve())
        errors.extend(
            check_report_coverage(
                report_payload,
                manifest,
                workflow_manifest,
                required_modes,
            )
        )

    promotion_checked = False
    if args.require_promotion_approvals:
        promotion_checked = True
        approvals_payload = load_json(Path(args.promotion_approvals).resolve())
        approvals = parse_promotion_approvals(approvals_payload)
        errors.extend(check_promotion_approvals(approvals, workflow_manifest))

    status = {
        "ok": len(errors) == 0,
        "errorCount": len(errors),
        "errors": errors,
        "summary": summarize(manifest["rows"]),
        "requiredModes": required_modes,
        "reportChecked": bool(args.report),
        "promotionChecked": promotion_checked,
        "projectionContractHash": manifest["projectionContractHash"],
        "sourceWorkloadsSha256": manifest["sourceWorkloadsSha256"],
    }

    if args.emit_json:
        print(json.dumps(status, indent=2))
    else:
        print(
            "browser-benchmark-superset-check "
            f"ok={status['ok']} errors={status['errorCount']} "
            f"rows={status['summary']['rowCount']}"
        )
        print(
            "  classes: "
            f"high={status['summary']['high']} "
            f"medium={status['summary']['medium']} "
            f"non_projectable={status['summary']['non_projectable']}"
        )
        print(
            "  targets: "
            f"l1_browser_api={status['summary']['l1_browser_api']} "
            f"l0_only={status['summary']['l0_only']}"
        )
        for error in errors:
            print(f"  - {error}")

    return 0 if status["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
