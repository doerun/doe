#!/usr/bin/env python3
"""Synthesize the Doe-WebGPU vs Doppler token-sequence parity preflight.

Mitigates "Doe-WebGPU vs Doppler parity" from
docs/cerebras-north-star.md (Remaining no-hardware evidence gaps).

The existing parity-receipt at
`bench/out/r3-1-31b-doe-webgpu-parity/parity-receipt.json` records
identity-chain agreement (modelIdMatch=true) but the actual token-
sequence/logits/KV comparison fields are `not_attempted` because Doe
does not yet have a WebGPU end-to-end inference runner that consumes
the closed Doppler Program Bundle and emits a token transcript.

This synthesizer reads the existing parity-receipt and emits a typed
preflight that:
  - re-states the in-hand identity-chain match,
  - records the contract a Doe-side end-to-end runner would emit
    (per-token IDs, per-step logits digests, KV digests),
  - names the operational blocker — Doe-WebGPU's capture path proves
    structural emission, but a runtime that actually produces a token
    transcript by walking the Program Bundle's WGSL modules + host
    entrypoint does not exist.

The preflight receipt is not parity. It is the reviewer-facing
"what would be required to close the per-token compare" artifact,
ready for the bundle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARITY_RECEIPT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-doe-webgpu-parity/parity-receipt.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-doe-webgpu-token-parity-preflight/receipt.json"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--parity-receipt",
        type=Path,
        default=DEFAULT_PARITY_RECEIPT,
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.parity_receipt.is_file():
        sys.stderr.write(
            f"synthesize_doe_webgpu_token_parity_preflight: "
            f"existing parity receipt {args.parity_receipt} not found\n"
        )
        return 2
    parity = json.loads(args.parity_receipt.read_text(encoding="utf-8"))
    lanes = parity.get("lanes") or {}
    doppler = lanes.get("doppler") or {}
    doe = lanes.get("doe") or {}
    agreement = parity.get("agreement") or {}

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_webgpu_token_parity_preflight",
        "modelId": parity.get("modelId", "unknown"),
        "purpose": (
            "Preflight for Doe-WebGPU vs Doppler token-sequence "
            "parity. Records the existing identity-chain match and the "
            "contract a Doe-side end-to-end runner would emit. The "
            "blocker is the absence of that runner; identity-chain "
            "evidence is unchanged from the source parity receipt."
        ),
        "sourceParityReceipt": {
            "path": str(
                args.parity_receipt.relative_to(REPO_ROOT)
                if args.parity_receipt.is_absolute()
                and str(args.parity_receipt).startswith(str(REPO_ROOT))
                else args.parity_receipt
            ),
            "modelIdMatch": agreement.get("modelIdMatch"),
            "doppler": {
                "artifact": doppler.get("artifact"),
                "decodeTokens": doppler.get("decodeTokens"),
                "stopReason": doppler.get("stopReason"),
            },
            "doe": {
                "artifact": doe.get("artifact"),
                "graphSha256": doe.get("graphSha256"),
                "shaderCount": doe.get("shaderCount"),
                "submissionCount": doe.get("submissionCount"),
            },
        },
        "tokenParityContract": {
            "comparisonFields": [
                "tokenIdsSha256: doe vs doppler tokenSequence",
                "perStepLogitsSha256: doe vs doppler per-step logits digest",
                "kvStateSha256: doe vs doppler final KV digest",
                "stopReason: must match exactly across lanes",
            ],
            "promotionCriteria": {
                "tokenIdsMatch": "boolean",
                "perStepLogitsParityPassed": "boolean",
                "kvStateMatch": "boolean",
            },
            "currentValuesInSourceReceipt": {
                "tokenSequenceCompare": agreement.get(
                    "tokenSequenceCompare", "not_attempted"
                ),
                "logitsCompare": agreement.get(
                    "logitsCompare", "not_attempted"
                ),
                "kvStateCompare": agreement.get(
                    "kvStateCompare", "not_attempted"
                ),
            },
        },
        "blocker": {
            "class": "doe_webgpu_end_to_end_inference_runner_absent",
            "detail": (
                "Doe's existing WebGPU lane "
                "(bench/tools/capture_doppler_gemma4_webgpu_graph.mjs) "
                "captures a structural graph digest from a Program "
                "Bundle but does not run the program end-to-end. A "
                "runner that walks the bundle's WGSL modules, drives "
                "host_entrypoint, and emits a token transcript "
                "matching Doppler's reference contract is absent. The "
                "runtime support exists in packages/doe-gpu (Doe's "
                "Dawn-replacement WebGPU runtime); the missing piece "
                "is the Program Bundle-driver glue."
            ),
            "namedRunnerExtensions": [
                "bench/tools/(new)run_doe_webgpu_program_bundle_inference.mjs: "
                "load the Program Bundle JSON, instantiate the Doe-WebGPU "
                "runtime against its WGSL modules, run host_entrypoint to "
                "completion, emit a Doppler-shape transcript "
                "(tokenSequence, perStepLogitsDigest, kvDigest, "
                "stopReason).",
                "bench/tools/bind_doe_webgpu_token_parity.py: ingest the "
                "Doe-side transcript and the Doppler reference, emit a "
                "doe_webgpu_token_parity_receipt with hash-matched fields.",
                "config/(new)doe-webgpu-token-parity-receipt.schema.json: "
                "schema for the bound receipt so the gate path is typed.",
            ],
        },
        "claim": {
            "scope": (
                "Existing identity-chain match (modelIdMatch=true) is "
                "preserved. The token-sequence parity contract is named, "
                "the named blocker is the absent Doe-WebGPU end-to-end "
                "inference runner."
            ),
            "notWhat": (
                "Not numerical parity. tokenIdsMatch / "
                "perStepLogitsParityPassed / kvStateMatch are all "
                "absent because no Doe-side transcript exists yet. The "
                "preflight does not assert agreement — only that "
                "agreement would be measurable once the runner lands."
            ),
            "summary": (
                "Identity-chain parity in-hand; numerical token parity "
                "blocked on Doe-WebGPU end-to-end inference runner."
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out} (typed preflight, source parity in-hand)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
