#!/usr/bin/env python3
"""Run a receipted small-matmul logits counterexample across alternate accumulation policies."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import struct
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.runners.run_determinism_probe import annotate_commands
from bench.runners.run_determinism_probe import build_runtime
from bench.runners.run_determinism_probe import compare_lanes
from bench.runners.run_determinism_probe import load_json
from bench.runners.run_determinism_probe import resolve_repo_path
from bench.runners.run_determinism_probe import run_lane
from bench.runners.run_determinism_probe import sha256_bytes

DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "determinism" / "apple-metal-reduction-order-logit-flip.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "apple-metal-reduction-order-logit-flip"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Reduction-order logit-flip fixture JSON.")
    parser.add_argument("--runs", type=int, default=None, help="Override repeat count from the fixture.")
    parser.add_argument("--timestamp", default=None, help="UTC timestamp label (default: current UTC time).")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for artifacts.")
    parser.add_argument("--build", action="store_true", help="Build doe-zig-runtime before running.")
    return parser.parse_args()


def timestamp_label(raw: str | None) -> str:
    if raw:
        return raw
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_fixture_shape(fixture: dict[str, Any]) -> None:
    required = [
        "scenarioId",
        "kernelRoot",
        "profile",
        "backendLanes",
        "defaultRunCount",
        "captures",
        "variants",
        "exactReferenceLogits",
        "exactReferenceTopToken",
    ]
    missing = [field for field in required if field not in fixture]
    if missing:
        raise ValueError(f"fixture missing required fields: {', '.join(missing)}")


def logits_op_id_for_fixture(fixture: dict[str, Any]) -> str:
    return str(fixture.get("logitsSemanticOpId") or "matmul.logits")


def selected_token_op_id_for_fixture(fixture: dict[str, Any]) -> str:
    return str(fixture.get("selectedTokenSemanticOpId") or "sample.token")


def decode_logits(path: Path) -> list[float]:
    payload = path.read_bytes()
    if len(payload) % 4 != 0:
        raise ValueError(f"expected 4-byte aligned logits payload: {path}")
    if not payload:
        return []
    return list(struct.unpack("<" + "f" * (len(payload) // 4), payload))


def scalar_argmax(values: list[float]) -> int:
    best_index = 0
    best_value = values[0]
    for index, value in enumerate(values[1:], start=1):
        if value > best_value:
            best_value = value
            best_index = index
    return best_index


def summarize_lane_variants(
    lane_id: str,
    variant_reports: dict[str, dict[str, Any]],
    *,
    logits_op_id: str,
    selected_token_op_id: str,
    exact_reference_logits: list[float],
    exact_reference_top_token: int,
) -> dict[str, Any]:
    per_variant: list[dict[str, Any]] = []
    for variant_id, variant_report in variant_reports.items():
        lane = variant_report["lanes"][lane_id]
        logits_op = lane["operators"][logits_op_id]
        token_op = lane["operators"][selected_token_op_id]
        logits_artifact_path = resolve_repo_path(logits_op["artifacts"][0]["capturePath"])
        logits = decode_logits(logits_artifact_path)
        top_token = scalar_argmax(logits)
        sampled_token = token_op["dominantDecodedValue"]
        per_variant.append(
            {
                "variantId": variant_id,
                "policyId": variant_report["policyId"],
                "stableAcrossRuns": logits_op["stableAcrossRuns"] and token_op["stableAcrossRuns"],
                "logitsDigest": logits_op["dominantDigest"],
                "tokenDigest": token_op["dominantDigest"],
                "logits": logits,
                "logitsArtifactPath": str(logits_artifact_path),
                "topTokenFromLogits": top_token,
                "sampledToken": sampled_token,
                "sampleMatchesScalarArgmax": sampled_token == top_token,
                "matchesExactReferenceTopToken": top_token == exact_reference_top_token,
                "deltaFromExactReferenceLogits": [
                    logits[index] - exact_reference_logits[index] for index in range(len(logits))
                ],
            }
        )
    per_variant.sort(key=lambda item: item["variantId"])
    comparisons: list[dict[str, Any]] = []
    for index, left in enumerate(per_variant):
        for right in per_variant[index + 1 :]:
            comparisons.append(
                {
                    "leftVariantId": left["variantId"],
                    "rightVariantId": right["variantId"],
                    "sameLogitsBytes": left["logitsDigest"] == right["logitsDigest"],
                    "sameTopTokenFromLogits": left["topTokenFromLogits"] == right["topTokenFromLogits"],
                    "sameSampledToken": left["sampledToken"] == right["sampledToken"],
                }
            )
    return {
        "laneId": lane_id,
        "variantOutputs": per_variant,
        "tokenFlipObserved": len({entry["topTokenFromLogits"] for entry in per_variant}) > 1,
        "sampleFlipObserved": len({entry["sampledToken"] for entry in per_variant}) > 1,
        "comparisons": comparisons,
    }


def claim_summary(
    fixture: dict[str, Any],
    *,
    lane_variant_summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "exactReferenceLogits": fixture["exactReferenceLogits"],
        "exactReferenceTopToken": fixture["exactReferenceTopToken"],
        "tokenFlipObserved": any(summary["tokenFlipObserved"] for summary in lane_variant_summaries.values()),
        "sampleFlipObserved": any(summary["sampleFlipObserved"] for summary in lane_variant_summaries.values()),
        "lanes": {
            lane_id: {
                "tokenFlipObserved": summary["tokenFlipObserved"],
                "sampleFlipObserved": summary["sampleFlipObserved"],
            }
            for lane_id, summary in lane_variant_summaries.items()
        },
    }


def main() -> None:
    args = parse_args()
    if args.build:
        build_runtime()

    fixture_path = resolve_repo_path(args.fixture)
    fixture = load_json(fixture_path)
    ensure_fixture_shape(fixture)

    stamp = timestamp_label(args.timestamp)
    output_dir = resolve_repo_path(args.output_root) / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    kernel_root = resolve_repo_path(fixture["kernelRoot"])
    run_count = args.runs or fixture["defaultRunCount"]
    captures = fixture["captures"]

    variant_reports: dict[str, dict[str, Any]] = {}
    for variant in fixture["variants"]:
        variant_id = variant["id"]
        base_commands_path = resolve_repo_path(variant["commandsPath"])
        base_commands = load_json(base_commands_path)
        base_commands_sha256 = sha256_bytes(base_commands_path.read_bytes())
        annotated_commands = annotate_commands(
            base_commands,
            captures,
            execution_plan_hash=base_commands_sha256,
        )
        annotated_bytes = (json.dumps(annotated_commands, indent=2) + "\n").encode("utf-8")
        annotated_sha256 = sha256_bytes(annotated_bytes)
        annotated_commands_path = output_dir / f"{fixture['scenarioId']}.{variant_id}.commands.annotated.json"
        annotated_commands_path.write_bytes(annotated_bytes)

        lane_summaries: dict[str, dict[str, Any]] = {}
        for lane in fixture["backendLanes"]:
            lane_summaries[lane["id"]] = run_lane(
                lane_id=lane["id"],
                backend_lane=lane["backendLane"],
                run_count=run_count,
                commands_path=annotated_commands_path,
                output_dir=output_dir / variant_id,
                profile=fixture["profile"],
                kernel_root=kernel_root,
                queue_wait_mode=fixture.get("queueWaitMode", "process-events"),
                queue_sync_mode=fixture.get("queueSyncMode", "per-command"),
                captures=captures,
            )

        variant_reports[variant_id] = {
            "id": variant_id,
            "policyId": variant["policyId"],
            "commandsPath": str(base_commands_path),
            "baseCommandsSha256": base_commands_sha256,
            "annotatedCommandsPath": str(annotated_commands_path),
            "annotatedCommandsSha256": annotated_sha256,
            "lanes": lane_summaries,
            "crossLane": compare_lanes(lane_summaries, captures),
        }

    lane_variant_summaries = {
        lane["id"]: summarize_lane_variants(
            lane["id"],
            variant_reports,
            logits_op_id=logits_op_id_for_fixture(fixture),
            selected_token_op_id=selected_token_op_id_for_fixture(fixture),
            exact_reference_logits=list(fixture["exactReferenceLogits"]),
            exact_reference_top_token=int(fixture["exactReferenceTopToken"]),
        )
        for lane in fixture["backendLanes"]
    }

    report = {
        "schemaVersion": 1,
        "scenarioId": fixture["scenarioId"],
        "description": fixture.get("description"),
        "fixturePath": str(fixture_path),
        "timestamp": stamp,
        "runCount": run_count,
        "profile": fixture["profile"],
        "captures": captures,
        "variants": variant_reports,
        "laneVariantSummary": lane_variant_summaries,
        "claim": claim_summary(fixture, lane_variant_summaries=lane_variant_summaries),
    }

    report_path = output_dir / f"{fixture['scenarioId']}.reduction-order-logit-flip.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
