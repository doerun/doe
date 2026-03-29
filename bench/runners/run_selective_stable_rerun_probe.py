#!/usr/bin/env python3
"""Evaluate a selective stable-rerun decision from a reduction-order source report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.lib.config_validation import load_validated_config
from bench.runners.run_determinism_probe import load_json
from bench.runners.run_determinism_probe import resolve_repo_path
from bench.runners.run_determinism_probe import sha256_path
from bench.runners.run_determinism_probe import timestamp_label

DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "determinism" / "apple-metal-selective-stable-rerun-logit-flip.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "apple-metal-selective-stable-rerun"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Selective stable-rerun fixture JSON.")
    parser.add_argument("--source-report", required=True, help="Source reduction-order logit-flip report JSON.")
    parser.add_argument("--timestamp", default=None, help="UTC timestamp label (default: current UTC time).")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for artifacts.")
    return parser.parse_args()


def ensure_fixture_shape(fixture: dict[str, Any]) -> None:
    required = [
        "scenarioId",
        "policyRegistryPath",
        "triggerPolicyId",
        "routingPolicyId",
        "operatorFamily",
        "fastVariantId",
        "stableVariantId",
        "selectedTokenOpId",
        "sensitiveOperators",
    ]
    missing = [field for field in required if field not in fixture]
    if missing:
        raise ValueError(f"fixture missing required fields: {', '.join(missing)}")


def ensure_source_shape(source_report: dict[str, Any], *, fast_variant_id: str, stable_variant_id: str) -> None:
    required = ["scenarioId", "captures", "variants", "laneVariantSummary", "claim"]
    missing = [field for field in required if field not in source_report]
    if missing:
        raise ValueError(f"source report missing required fields: {', '.join(missing)}")
    variants = source_report["variants"]
    if fast_variant_id not in variants or stable_variant_id not in variants:
        raise ValueError(
            f"source report must contain fast/stable variants {fast_variant_id!r} and {stable_variant_id!r}"
        )


def build_variant_output_map(source_report: dict[str, Any], lane_id: str) -> dict[str, dict[str, Any]]:
    outputs = source_report["laneVariantSummary"][lane_id]["variantOutputs"]
    return {entry["variantId"]: entry for entry in outputs}


def find_first_divergence(
    source_report: dict[str, Any],
    *,
    lane_id: str,
    fast_variant_id: str,
    stable_variant_id: str,
) -> dict[str, Any] | None:
    fast_lane = source_report["variants"][fast_variant_id]["lanes"][lane_id]["operators"]
    stable_lane = source_report["variants"][stable_variant_id]["lanes"][lane_id]["operators"]
    for capture in source_report["captures"]:
        op_id = capture["semanticOpId"]
        fast_op = fast_lane[op_id]
        stable_op = stable_lane[op_id]
        if fast_op["dominantDigest"] == stable_op["dominantDigest"]:
            continue
        return {
            "semanticOpId": op_id,
            "semanticStage": capture.get("semanticStage"),
            "semanticPhase": capture.get("semanticPhase"),
            "fastDigest": fast_op["dominantDigest"],
            "stableDigest": stable_op["dominantDigest"],
        }
    return None


def resolve_registry_entries(
    registry: dict[str, Any],
    *,
    trigger_policy_id: str,
    routing_policy_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    trigger_policy = next(
        (entry for entry in registry["triggerPolicies"] if entry["triggerPolicyId"] == trigger_policy_id),
        None,
    )
    if trigger_policy is None:
        raise ValueError(f"unknown trigger policy: {trigger_policy_id}")
    routing_policy = next(
        (entry for entry in registry["routingPolicies"] if entry["policyId"] == routing_policy_id),
        None,
    )
    if routing_policy is None:
        raise ValueError(f"unknown routing policy: {routing_policy_id}")
    if routing_policy["triggerPolicyId"] != trigger_policy_id:
        raise ValueError(
            f"routing policy {routing_policy_id} does not reference trigger policy {trigger_policy_id}"
        )
    route_metadata = next(
        (entry for entry in registry["routeDecisionMetadata"] if entry["decision"] == routing_policy["triggeredDecision"]),
        None,
    )
    if route_metadata is None:
        raise ValueError(
            f"missing route decision metadata for triggered decision {routing_policy['triggeredDecision']}"
        )
    return trigger_policy, routing_policy, route_metadata


def evaluate_lane(
    source_report: dict[str, Any],
    registry: dict[str, Any],
    fixture: dict[str, Any],
    *,
    lane_id: str,
) -> dict[str, Any]:
    fast_variant_id = fixture["fastVariantId"]
    stable_variant_id = fixture["stableVariantId"]
    trigger_policy_id = fixture["triggerPolicyId"]
    routing_policy_id = fixture["routingPolicyId"]
    selected_token_op_id = fixture["selectedTokenOpId"]
    exact_reference_top_token = source_report["claim"].get("exactReferenceTopToken")

    trigger_policy, routing_policy, _ = resolve_registry_entries(
        registry,
        trigger_policy_id=trigger_policy_id,
        routing_policy_id=routing_policy_id,
    )
    variant_outputs = build_variant_output_map(source_report, lane_id)
    fast_variant = variant_outputs[fast_variant_id]
    stable_variant = variant_outputs[stable_variant_id]
    fast_lane = source_report["variants"][fast_variant_id]["lanes"][lane_id]["operators"]
    stable_lane = source_report["variants"][stable_variant_id]["lanes"][lane_id]["operators"]
    first_divergence = find_first_divergence(
        source_report,
        lane_id=lane_id,
        fast_variant_id=fast_variant_id,
        stable_variant_id=stable_variant_id,
    )

    fast_token = fast_lane[selected_token_op_id]["dominantDecodedValue"]
    stable_token = stable_lane[selected_token_op_id]["dominantDecodedValue"]
    selected_token_disagreement = fast_token != stable_token
    stable_matches_exact_reference = stable_variant["matchesExactReferenceTopToken"]
    fast_misses_exact_reference = not fast_variant["matchesExactReferenceTopToken"]
    sensitive_operator_matched = (
        first_divergence is not None
        and first_divergence["semanticOpId"] in trigger_policy["allowedSensitiveOperators"]
        and first_divergence["semanticOpId"] in fixture["sensitiveOperators"]
    )

    checks = {
        "firstDivergencePresent": first_divergence is not None,
        "sensitiveOperatorMatched": sensitive_operator_matched,
        "selectedTokenDisagreement": selected_token_disagreement,
        "stableMatchesExactReference": stable_matches_exact_reference,
        "fastMissesExactReference": fast_misses_exact_reference,
    }
    trigger_fired = all(
        [
            checks["firstDivergencePresent"] if trigger_policy["requireFirstDivergence"] else True,
            checks["selectedTokenDisagreement"] if trigger_policy["requireSelectedTokenDisagreement"] else True,
            checks["stableMatchesExactReference"] if trigger_policy["requireStableMatchesExactReference"] else True,
            checks["fastMissesExactReference"] if trigger_policy["requireFastMissesExactReference"] else True,
            checks["sensitiveOperatorMatched"],
        ]
    )

    route_decision = routing_policy["triggeredDecision"] if trigger_fired else routing_policy["fallbackDecision"]
    route_metadata = next(
        (entry for entry in registry["routeDecisionMetadata"] if entry["decision"] == route_decision),
        None,
    )
    if route_metadata is None:
        raise ValueError(f"missing route decision metadata for route decision {route_decision}")
    selection_mode = route_metadata["selectionMode"]
    selected_variant_id = (
        stable_variant_id if selection_mode == "stable"
        else fast_variant_id if selection_mode == "fast"
        else None
    )
    selected_token = (
        stable_token if selection_mode == "stable"
        else fast_token if selection_mode == "fast"
        else None
    )

    return {
        "laneId": lane_id,
        "operatorFamily": fixture["operatorFamily"],
        "selectedTokenOpId": selected_token_op_id,
        "fastVariantId": fast_variant_id,
        "stableVariantId": stable_variant_id,
        "fastPolicyId": fast_variant["policyId"],
        "stablePolicyId": stable_variant["policyId"],
        "exactReferenceTopToken": exact_reference_top_token,
        "firstDivergence": first_divergence,
        "selectedToken": {
            "fast": fast_token,
            "stable": stable_token,
            "changed": selected_token_disagreement,
            "fastMatchesExactReference": fast_variant["matchesExactReferenceTopToken"],
            "stableMatchesExactReference": stable_variant["matchesExactReferenceTopToken"],
        },
        "trigger": {
            "triggerPolicyId": trigger_policy_id,
            "fired": trigger_fired,
            "checks": checks,
            "allowedSensitiveOperators": trigger_policy["allowedSensitiveOperators"],
            "proofLinks": trigger_policy["proofLinks"],
        },
        "route": {
            "policyId": routing_policy_id,
            "decision": route_decision,
            "selectionMode": selection_mode,
            "selectedVariantId": selected_variant_id,
            "selectedToken": selected_token,
            "triggeredDecision": routing_policy["triggeredDecision"],
            "fallbackDecision": routing_policy["fallbackDecision"],
            "proofLinks": routing_policy["proofLinks"],
            "selectionProofLinks": route_metadata["proofLinks"],
        },
    }


def claim_summary(lane_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "anyTriggerFired": any(result["trigger"]["fired"] for result in lane_results.values()),
        "anyPreferStable": any(result["route"]["decision"] == "prefer-stable" for result in lane_results.values()),
        "allLanesSameRoute": len({result["route"]["decision"] for result in lane_results.values()}) == 1,
        "lanes": {
            lane_id: {
                "triggerFired": result["trigger"]["fired"],
                "routeDecision": result["route"]["decision"],
                "selectedTokenChanged": result["selectedToken"]["changed"],
                "stableMatchesExactReference": result["selectedToken"]["stableMatchesExactReference"],
                "fastMatchesExactReference": result["selectedToken"]["fastMatchesExactReference"],
            }
            for lane_id, result in lane_results.items()
        },
    }


def main() -> None:
    args = parse_args()
    fixture_path = resolve_repo_path(args.fixture)
    fixture = load_json(fixture_path)
    ensure_fixture_shape(fixture)

    source_report_path = resolve_repo_path(args.source_report)
    source_report = load_json(source_report_path)
    ensure_source_shape(
        source_report,
        fast_variant_id=fixture["fastVariantId"],
        stable_variant_id=fixture["stableVariantId"],
    )

    registry_path = resolve_repo_path(fixture["policyRegistryPath"])
    registry = load_validated_config(registry_path)
    stamp = timestamp_label(args.timestamp)
    output_dir = resolve_repo_path(args.output_root) / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    lane_results = {
        lane_id: evaluate_lane(source_report, registry, fixture, lane_id=lane_id)
        for lane_id in sorted(source_report["laneVariantSummary"].keys())
    }

    report = {
        "schemaVersion": 1,
        "scenarioId": fixture["scenarioId"],
        "description": fixture.get("description"),
        "timestamp": stamp,
        "fixturePath": str(fixture_path),
        "sourceReportPath": str(source_report_path),
        "sourceReportSha256": sha256_path(source_report_path),
        "sourceScenarioId": source_report["scenarioId"],
        "policyRegistryPath": str(registry_path),
        "proofArtifactPath": registry["proofArtifactPath"],
        "policyRegistryVersion": registry["registryVersion"],
        "routeTaxonomyVersion": registry["routeTaxonomyVersion"],
        "routeDecisions": registry["routeDecisions"],
        "laneResults": lane_results,
        "claim": claim_summary(lane_results),
    }

    report_path = output_dir / f"{fixture['scenarioId']}.selective-stable-rerun.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
