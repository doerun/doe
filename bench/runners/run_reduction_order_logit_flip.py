#!/usr/bin/env python3
"""Run a receipted small-matmul logits counterexample across alternate accumulation policies."""

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
    / "apple-metal-reduction-order-logit-flip.json"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "apple-metal-reduction-order-logit-flip"


def parse_args():
    return build_shared_parser(
        description=__doc__,
        default_fixture=DEFAULT_FIXTURE,
        default_output_root=DEFAULT_OUTPUT_ROOT,
        fixture_help="Reduction-order logit-flip fixture JSON.",
    ).parse_args()


def validate_fixture(fixture: dict[str, Any]) -> None:
    ensure_fixture_shape(
        fixture,
        extra_required_fields=("exactReferenceLogits", "exactReferenceTopToken"),
    )


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


def summarize_lane(
    lane_id: str,
    variant_reports: dict[str, dict[str, Any]],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    logits_op_id = logits_op_id_for_fixture(fixture)
    selected_token_op_id = selected_token_op_id_for_fixture(fixture)
    exact_reference_logits = list(fixture["exactReferenceLogits"])
    exact_reference_top_token = int(fixture["exactReferenceTopToken"])

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
        for right in per_variant[index + 1:]:
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


def build_claim(
    fixture: dict[str, Any],
    lane_variant_summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "exactReferenceLogits": fixture["exactReferenceLogits"],
        "exactReferenceTopToken": fixture["exactReferenceTopToken"],
        "tokenFlipObserved": any(
            summary["tokenFlipObserved"] for summary in lane_variant_summaries.values()
        ),
        "sampleFlipObserved": any(
            summary["sampleFlipObserved"] for summary in lane_variant_summaries.values()
        ),
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
    report_path = run_probe(
        args,
        report_filename_suffix="reduction-order-logit-flip",
        validate_fixture=validate_fixture,
        summarize_lane=summarize_lane,
        build_claim=build_claim,
    )
    print(report_path)


if __name__ == "__main__":
    main()
