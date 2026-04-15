#!/usr/bin/env python3
"""Run a receipted micro counterexample across alternate reduction policies."""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.runners._reduction_order_probe_support import (
    build_shared_parser,
    ensure_fixture_shape,
    resolve_repo_path,
    run_probe,
)


DEFAULT_FIXTURE = (
    REPO_ROOT
    / "bench"
    / "fixtures"
    / "determinism"
    / "apple-metal-reduction-order-dot-product.json"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "apple-metal-reduction-order-counterexample"


def parse_args():
    return build_shared_parser(
        description=__doc__,
        default_fixture=DEFAULT_FIXTURE,
        default_output_root=DEFAULT_OUTPUT_ROOT,
        fixture_help="Reduction-order counterexample fixture JSON.",
    ).parse_args()


def validate_fixture(fixture: dict[str, Any]) -> None:
    ensure_fixture_shape(fixture, validate_variants=True)


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


def summarize_lane(
    lane_id: str,
    variant_reports: dict[str, dict[str, Any]],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    capture_op_id = fixture["captures"][0]["semanticOpId"]
    exact_reference_value = fixture.get("exactReferenceValue")

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
        for right in per_variant[index + 1:]:
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


def build_claim(
    fixture: dict[str, Any],
    lane_variant_summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "exactReferenceValue": fixture.get("exactReferenceValue"),
        "counterexampleObserved": any(
            summary["counterexampleObserved"] for summary in lane_variant_summaries.values()
        ),
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
    report_path = run_probe(
        args,
        report_filename_suffix="reduction-order-counterexample",
        validate_fixture=validate_fixture,
        summarize_lane=summarize_lane,
        build_claim=build_claim,
    )
    print(report_path)


if __name__ == "__main__":
    main()
