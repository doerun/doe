#!/usr/bin/env python3
"""Generate browser projection manifest from core Dawn-vs-Fawn workloads."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VALID_PROJECTION_CLASSES = {"high", "medium", "non_projectable"}
VALID_LAYER_TARGETS = {"l1_browser_api", "l0_only"}
VALID_COMPARABILITY = {"strict", "component", "none"}
VALID_REQUIRED_STATUS = {"ok", "not_applicable"}
VALID_CLAIM_SCOPE = {"l1_strict_candidate", "l1_component_only", "l0_only_no_claim"}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workloads",
        default="bench/workloads.amd.vulkan.extended.json",
        help="Path to core workload JSON.",
    )
    parser.add_argument(
        "--rules",
        default="nursery/chromium_webgpu_lane/bench/projection-rules.json",
        help="Path to projection-rules.json.",
    )
    parser.add_argument(
        "--out",
        default="nursery/chromium_webgpu_lane/bench/generated/browser_projection_manifest.json",
        help="Output manifest path.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate inputs and print summary without writing output.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def resolve_path(value: str, repo_root: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_sha256(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing non-empty string: {label}")
    return value


def require_rule_shape(rule: dict[str, Any], label: str) -> dict[str, str]:
    projection_class = require_string(rule.get("projectionClass"), f"{label}.projectionClass")
    layer_target = require_string(rule.get("layerTarget"), f"{label}.layerTarget")
    scenario_template = require_string(rule.get("scenarioTemplate"), f"{label}.scenarioTemplate")
    comparability = require_string(
        rule.get("comparabilityExpectation"), f"{label}.comparabilityExpectation"
    )
    required_status = require_string(rule.get("requiredStatus"), f"{label}.requiredStatus")
    claim_scope = require_string(rule.get("claimScope"), f"{label}.claimScope")
    claim_language = require_string(rule.get("claimLanguage"), f"{label}.claimLanguage")
    projection_note = require_string(rule.get("projectionNote"), f"{label}.projectionNote")

    if projection_class not in VALID_PROJECTION_CLASSES:
        raise ValueError(f"invalid {label}.projectionClass: {projection_class}")
    if layer_target not in VALID_LAYER_TARGETS:
        raise ValueError(f"invalid {label}.layerTarget: {layer_target}")
    if comparability not in VALID_COMPARABILITY:
        raise ValueError(f"invalid {label}.comparabilityExpectation: {comparability}")
    if required_status not in VALID_REQUIRED_STATUS:
        raise ValueError(f"invalid {label}.requiredStatus: {required_status}")
    if claim_scope not in VALID_CLAIM_SCOPE:
        raise ValueError(f"invalid {label}.claimScope: {claim_scope}")

    if projection_class in {"high", "medium"}:
        if layer_target != "l1_browser_api":
            raise ValueError(
                f"{label} must target l1_browser_api for projectionClass={projection_class}"
            )
        if scenario_template == "none":
            raise ValueError(
                f"{label} must provide non-none scenarioTemplate for projectionClass={projection_class}"
            )
        if required_status != "ok":
            raise ValueError(
                f"{label} requiredStatus must be ok for projectionClass={projection_class}"
            )
    if projection_class == "non_projectable":
        if layer_target != "l0_only":
            raise ValueError(f"{label} must target l0_only for non_projectable")
        if required_status != "not_applicable":
            raise ValueError(f"{label} requiredStatus must be not_applicable for non_projectable")
        if claim_scope != "l0_only_no_claim":
            raise ValueError(f"{label} claimScope must be l0_only_no_claim for non_projectable")
        if comparability != "none":
            raise ValueError(
                f"{label} comparabilityExpectation must be none for non_projectable"
            )
    if comparability == "strict" and claim_scope != "l1_strict_candidate":
        raise ValueError(f"{label} strict comparability requires claimScope=l1_strict_candidate")
    if comparability == "component" and claim_scope != "l1_component_only":
        raise ValueError(f"{label} component comparability requires claimScope=l1_component_only")
    if comparability == "none" and claim_scope != "l0_only_no_claim":
        raise ValueError(f"{label} none comparability requires claimScope=l0_only_no_claim")

    return {
        "projectionClass": projection_class,
        "layerTarget": layer_target,
        "scenarioTemplate": scenario_template,
        "comparabilityExpectation": comparability,
        "requiredStatus": required_status,
        "claimScope": claim_scope,
        "claimLanguage": claim_language,
        "projectionNote": projection_note,
    }


def build_manifest(
    workloads_payload: dict[str, Any],
    rules_payload: dict[str, Any],
    workloads_path: str,
    rules_path: str,
    workloads_sha256: str,
    rules_sha256: str,
) -> dict[str, Any]:
    workloads_raw = workloads_payload.get("workloads")
    if not isinstance(workloads_raw, list) or not workloads_raw:
        raise ValueError("invalid workloads payload: missing non-empty workloads[]")

    default_rule_raw = rules_payload.get("defaultRule")
    if not isinstance(default_rule_raw, dict):
        raise ValueError("invalid rules payload: missing defaultRule object")
    default_rule = require_rule_shape(default_rule_raw, "defaultRule")

    domain_rules_raw = rules_payload.get("domainRules")
    if not isinstance(domain_rules_raw, dict):
        raise ValueError("invalid rules payload: missing domainRules object")

    domain_rules: dict[str, dict[str, str]] = {}
    for domain, value in domain_rules_raw.items():
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError(f"invalid domain rule key: {domain}")
        if not isinstance(value, dict):
            raise ValueError(f"invalid domain rule object: {domain}")
        domain_rules[domain] = require_rule_shape(value, f"domainRules.{domain}")

    seen_ids: set[str] = set()
    rows: list[dict[str, Any]] = []

    for index, workload_raw in enumerate(workloads_raw):
        if not isinstance(workload_raw, dict):
            raise ValueError(f"invalid workload object at index {index}")
        workload_id = require_string(workload_raw.get("id"), f"workloads[{index}].id")
        workload_name = require_string(workload_raw.get("name"), f"workloads[{index}].name")
        domain = require_string(workload_raw.get("domain"), f"workloads[{index}].domain")

        if workload_id in seen_ids:
            raise ValueError(f"duplicate workload id: {workload_id}")
        seen_ids.add(workload_id)

        rule = domain_rules.get(domain, default_rule)

        row = {
            "sourceWorkloadId": workload_id,
            "sourceWorkloadName": workload_name,
            "domain": domain,
            "projectionClass": rule["projectionClass"],
            "layerTarget": rule["layerTarget"],
            "scenarioTemplate": rule["scenarioTemplate"],
            "comparabilityExpectation": rule["comparabilityExpectation"],
            "requiredStatus": rule["requiredStatus"],
            "claimScope": rule["claimScope"],
            "claimLanguage": rule["claimLanguage"],
            "projectionNote": rule["projectionNote"],
        }
        rows.append(row)

    projection_contract_hash = payload_sha256(
        {
            "sourceWorkloadsSha256": workloads_sha256,
            "rulesSha256": rules_sha256,
            "rows": rows,
        }
    )

    return {
        "schemaVersion": 2,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "sourceWorkloadsPath": workloads_path,
        "sourceWorkloadsSha256": workloads_sha256,
        "rulesPath": rules_path,
        "rulesSha256": rules_sha256,
        "projectionContractHash": projection_contract_hash,
        "sourceWorkloadCount": len(rows),
        "rows": rows,
    }


def summarize(manifest: dict[str, Any]) -> str:
    rows = manifest["rows"]
    by_class: dict[str, int] = {"high": 0, "medium": 0, "non_projectable": 0}
    by_target: dict[str, int] = {"l1_browser_api": 0, "l0_only": 0}
    for row in rows:
        by_class[row["projectionClass"]] = by_class.get(row["projectionClass"], 0) + 1
        by_target[row["layerTarget"]] = by_target.get(row["layerTarget"], 0) + 1
    return (
        f"rows={len(rows)} "
        f"high={by_class['high']} medium={by_class['medium']} "
        f"non_projectable={by_class['non_projectable']} "
        f"l1={by_target['l1_browser_api']} l0_only={by_target['l0_only']}"
    )


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[3]
    workloads_path = resolve_path(args.workloads, repo_root)
    rules_path = resolve_path(args.rules, repo_root)
    out_path = resolve_path(args.out, repo_root)

    workloads_payload = load_json(workloads_path)
    rules_payload = load_json(rules_path)
    workloads_sha256 = file_sha256(workloads_path)
    rules_sha256 = file_sha256(rules_path)

    manifest = build_manifest(
        workloads_payload,
        rules_payload,
        display_path(workloads_path, repo_root),
        display_path(rules_path, repo_root),
        workloads_sha256,
        rules_sha256,
    )
    summary = summarize(manifest)

    if args.check_only:
        print(f"[projection-manifest] check-only ok: {summary}")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")
    print(f"[projection-manifest] wrote {out_path}")
    print(f"[projection-manifest] {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
