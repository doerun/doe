#!/usr/bin/env python3
"""Run a receipted micro counterexample across alternate reduction policies."""

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

DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "determinism" / "apple-metal-reduction-order-dot-product.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "apple-metal-reduction-order-counterexample"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Reduction-order counterexample fixture JSON.")
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
    ]
    missing = [field for field in required if field not in fixture]
    if missing:
        raise ValueError(f"fixture missing required fields: {', '.join(missing)}")
    if not fixture["backendLanes"]:
        raise ValueError("fixture must define at least one backend lane")
    if not fixture["captures"]:
        raise ValueError("fixture must define at least one capture")
    if not fixture["variants"]:
        raise ValueError("fixture must define at least one variant")
    for index, variant in enumerate(fixture["variants"]):
        for field in ("id", "policyId", "commandsPath"):
            if not isinstance(variant.get(field), str) or not variant[field]:
                raise ValueError(f"variants[{index}].{field} must be a non-empty string")


def decode_scalar_f32(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    if len(payload) != 4:
        raise ValueError(f"expected 4-byte f32 payload at {path}, got {len(payload)} bytes")
    word = struct.unpack("<I", payload)[0]
    value = struct.unpack("<f", payload)[0]
    return {"value": value, "word": word}


def ulp_distance(left_word: int, right_word: int) -> int:
    def ordered(word: int) -> int:
        return 0x80000000 - word if (word & 0x80000000) else word + 0x80000000
    return abs(ordered(left_word) - ordered(right_word))


def summarize_lane_variants(
    lane_id: str,
    variant_reports: dict[str, dict[str, Any]],
    *,
    capture_op_id: str,
    exact_reference_value: float | None,
) -> dict[str, Any]:
    per_variant: list[dict[str, Any]] = []
    for variant_id, variant_report in variant_reports.items():
        op_summary = variant_report["lanes"][lane_id]["operators"][capture_op_id]
        artifact_path = resolve_repo_path(op_summary["artifacts"][0]["capturePath"])
        decoded = decode_scalar_f32(artifact_path)
        entry = {
            "variantId": variant_id,
            "policyId": variant_report["policyId"],
            "stableAcrossRuns": op_summary["stableAcrossRuns"],
            "dominantDigest": op_summary["dominantDigest"],
            "outputValueF32": decoded["value"],
            "outputWordHex": f"0x{decoded['word']:08x}",
            "capturePath": str(artifact_path),
        }
        if exact_reference_value is not None:
            entry["deltaFromExactReference"] = decoded["value"] - exact_reference_value
        per_variant.append(entry)
    per_variant.sort(key=lambda item: item["variantId"])

    comparisons: list[dict[str, Any]] = []
    for index, left in enumerate(per_variant):
        for right in per_variant[index + 1 :]:
            left_word = int(left["outputWordHex"], 16)
            right_word = int(right["outputWordHex"], 16)
            comparisons.append(
                {
                    "leftVariantId": left["variantId"],
                    "rightVariantId": right["variantId"],
                    "sameBytes": left["dominantDigest"] == right["dominantDigest"],
                    "sameValue": left["outputValueF32"] == right["outputValueF32"],
                    "valueDelta": left["outputValueF32"] - right["outputValueF32"],
                    "ulpDistance": ulp_distance(left_word, right_word),
                }
            )
    return {
        "laneId": lane_id,
        "variantCount": len(per_variant),
        "variantOutputs": per_variant,
        "uniqueOutputValueCount": len({entry["outputValueF32"] for entry in per_variant}),
        "uniqueDigestCount": len({entry["dominantDigest"] for entry in per_variant}),
        "counterexampleObserved": len({entry["outputValueF32"] for entry in per_variant}) > 1,
        "comparisons": comparisons,
    }


def claim_summary(
    fixture: dict[str, Any],
    *,
    lane_variant_summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    exact_reference_value = fixture.get("exactReferenceValue")
    return {
        "exactReferenceValue": exact_reference_value,
        "counterexampleObserved": any(summary["counterexampleObserved"] for summary in lane_variant_summaries.values()),
        "lanes": {
            lane_id: {
                "counterexampleObserved": summary["counterexampleObserved"],
                "uniqueOutputValueCount": summary["uniqueOutputValueCount"],
                "uniqueDigestCount": summary["uniqueDigestCount"],
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
        if not isinstance(base_commands, list):
            raise SystemExit(f"commands file must contain a list: {base_commands_path}")
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

    capture_op_id = captures[0]["semanticOpId"]
    lane_variant_summaries = {
        lane["id"]: summarize_lane_variants(
            lane["id"],
            variant_reports,
            capture_op_id=capture_op_id,
            exact_reference_value=fixture.get("exactReferenceValue"),
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

    report_path = output_dir / f"{fixture['scenarioId']}.reduction-order-counterexample.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
