#!/usr/bin/env python3
"""Combined 5-lane summary for doe_run.py targets (roadmap #9).

Reads every per-target receipt under
  bench/out/doe-run/{target}/L{num_layers}-receipt.json
and emits one `doe_all_lanes_summary` JSON:

  - per-lane: target, status, backendId, outputSha256, elapsedMs,
    manifestSha256, graphSha256, interpretation
  - bundleIdentity: manifest/graph sha consistency across lanes
  - outputParityMatrix: output-sha agreement across runtime-producing
    lanes (webgpu-wgsl, csl-webgpu-emulator, csl-sdklayout)
  - laneTaxonomy: which lanes produce output vs probe backend identity

Scope: identity + parity matrix. Not a performance claim. See
`docs/claim-discipline.md` for allowed/rejected claim boundaries.

Usage:
  python3 bench/tools/summarize_doe_run_lanes.py --num-layers 1 \\
    --out-json bench/out/doe-run/all-lanes-summary-L1.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

LANES = [
    "webgpu-wgsl",
    "doe-metal",
    "doe-vulkan",
    "csl-sdklayout",
    "csl-webgpu-emulator",
]

# Runtime-producing lanes emit an output tensor we can parity-check.
# Identity-probe lanes only emit a backend-identity trace; they have
# no outputSha256 to compare.
RUNTIME_OUTPUT_LANES = {"webgpu-wgsl", "csl-sdklayout", "csl-webgpu-emulator"}
IDENTITY_PROBE_LANES = {"doe-metal", "doe-vulkan"}


MODEL_RECEIPT_E2B = "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--num-layers", type=int, default=1)
    p.add_argument("--run-dir", default="bench/out/doe-run")
    p.add_argument(
        "--model-receipt",
        default=MODEL_RECEIPT_E2B,
        help="Model runtime receipt to extract realWeightEvidence from.",
    )
    p.add_argument("--out-json", default="")
    return p.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_receipt(run_dir: Path, lane: str, num_layers: int) -> dict | None:
    path = run_dir / lane / f"L{num_layers}-receipt.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main() -> int:
    args = parse_args()
    run_dir = resolve(args.run_dir)

    per_lane = []
    for lane in LANES:
        receipt = load_receipt(run_dir, lane, args.num_layers)
        if receipt is None:
            per_lane.append({
                "lane": lane,
                "receiptPresent": False,
                "status": "missing",
            })
            continue
        bundle = receipt.get("bundle") or {}
        rt = receipt.get("runtimeMetadata") or {}
        per_lane.append({
            "lane": lane,
            "receiptPresent": True,
            "status": receipt.get("status"),
            "elapsedMs": receipt.get("elapsedMs"),
            "outputSha256": receipt.get("outputSha256"),
            "outputPath": receipt.get("outputPath"),
            "tracePath": receipt.get("tracePath"),
            "manifestSha256": bundle.get("manifestSha256"),
            "graphSha256": bundle.get("graphSha256"),
            "backendId": rt.get("backendId"),
            "backendLane": rt.get("backendLane"),
            "profile": rt.get("profile"),
            "interpretation": rt.get("interpretation"),
            "laneRole": (
                "runtime_output"
                if lane in RUNTIME_OUTPUT_LANES
                else "backend_identity_probe"
            ),
        })

    # Bundle identity: manifest/graph sha must match across all lanes
    # that reported a receipt. Mismatched bundle shas mean the targets
    # ran different programs — the whole comparison is invalid.
    manifest_values = {
        e["manifestSha256"] for e in per_lane
        if e.get("receiptPresent") and e.get("manifestSha256")
    }
    graph_values = {
        e["graphSha256"] for e in per_lane
        if e.get("receiptPresent") and e.get("graphSha256")
    }
    manifest_consistent = len(manifest_values) <= 1
    graph_consistent = len(graph_values) <= 1

    # Output parity matrix across runtime-producing lanes only. Only
    # compare lanes that report status=succeeded and a non-null
    # outputSha256; otherwise mark the pair 'not_comparable'.
    parity_entries = []
    runtime_lane_entries = [
        e for e in per_lane
        if e.get("receiptPresent")
        and e.get("laneRole") == "runtime_output"
    ]
    for left, right in itertools.combinations(runtime_lane_entries, 2):
        left_ok = left.get("status") == "succeeded" and left.get("outputSha256")
        right_ok = right.get("status") == "succeeded" and right.get("outputSha256")
        if not (left_ok and right_ok):
            parity_entries.append({
                "left": left["lane"],
                "right": right["lane"],
                "verdict": "not_comparable",
                "reason": (
                    "missing status=succeeded or outputSha256 on one side"
                ),
            })
            continue
        parity_entries.append({
            "left": left["lane"],
            "right": right["lane"],
            "leftOutputSha256": left["outputSha256"],
            "rightOutputSha256": right["outputSha256"],
            "verdict": (
                "bit_exact_match"
                if left["outputSha256"] == right["outputSha256"]
                else "digest_mismatch"
            ),
        })

    # Overall verdict: all lanes with receipts succeeded or probed
    # successfully, bundle identity held, and runtime lanes all agree
    # on outputSha256. Anything short of that downgrades.
    all_receipts_ok = all(
        e.get("status") in ("succeeded",) for e in per_lane if e.get("receiptPresent")
    )
    missing_lanes = [e["lane"] for e in per_lane if not e.get("receiptPresent")]
    runtime_output_mismatches = [
        p for p in parity_entries if p.get("verdict") == "digest_mismatch"
    ]
    runtime_lanes_bit_exact = (
        len(runtime_output_mismatches) == 0
        and any(p.get("verdict") == "bit_exact_match" for p in parity_entries)
    )

    if (
        not missing_lanes
        and all_receipts_ok
        and manifest_consistent
        and graph_consistent
        and runtime_lanes_bit_exact
    ):
        overall = "all_lanes_identity_and_parity_matched"
    elif not missing_lanes and all_receipts_ok and manifest_consistent and graph_consistent:
        overall = "all_lanes_identity_matched_parity_partial"
    else:
        overall = "partial_or_inconsistent"

    # Real-weight evidence is a property of the MODEL runtime receipt,
    # not any one target receipt. Pull it through so the rollup carries
    # the 5 promotion criteria + pointers to the fixture/audit/parity
    # verdict. Absent receipt → leave field null; the cockpit surfaces
    # this as "absent" state rather than pretending it's promoted.
    real_weight_block = None
    executionStatus = None
    model_receipt_path = resolve(args.model_receipt)
    if model_receipt_path.is_file():
        try:
            _r = json.loads(model_receipt_path.read_text(encoding="utf-8"))
            executionStatus = _r.get("executionStatus")
            real_weight_block = _r.get("realWeightEvidence")
        except (OSError, ValueError):
            pass

    summary = {
        "schemaVersion": 1,
        "artifactKind": "doe_all_lanes_summary",
        "numLayers": args.num_layers,
        "modelReceiptPath": rel(model_receipt_path) if model_receipt_path.is_file() else None,
        "executionStatus": executionStatus,
        "realWeightEvidence": real_weight_block,
        "lanes": per_lane,
        "bundleIdentity": {
            "manifestSha256Values": sorted(manifest_values),
            "graphSha256Values": sorted(graph_values),
            "manifestConsistent": manifest_consistent,
            "graphConsistent": graph_consistent,
        },
        "outputParityMatrix": parity_entries,
        "laneTaxonomy": {
            "runtimeOutputLanes": sorted(RUNTIME_OUTPUT_LANES),
            "backendIdentityProbeLanes": sorted(IDENTITY_PROBE_LANES),
        },
        "missingLanes": missing_lanes,
        "verdict": overall,
        "claimScope": (
            "Identity + runtime-lane output parity only. This summary "
            "does NOT make performance claims. See "
            "docs/claim-discipline.md for the allowed/rejected claim "
            "boundary; hardware performance specifically requires a "
            "hardware_success receipt not present in this bundle."
        ),
    }

    if args.out_json:
        out_path = resolve(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {rel(out_path)}")

    runtime_matches = sum(
        1 for p in parity_entries if p.get("verdict") == "bit_exact_match"
    )
    runtime_mismatches = len(runtime_output_mismatches)
    print(
        f"lanes: {sum(1 for e in per_lane if e.get('receiptPresent'))}/{len(LANES)} present, "
        f"bundleIdentity manifest={manifest_consistent} graph={graph_consistent}, "
        f"runtime-output parity {runtime_matches} match / {runtime_mismatches} mismatch. "
        f"verdict={overall}"
    )
    return 0 if overall == "all_lanes_identity_and_parity_matched" else 0


if __name__ == "__main__":
    sys.exit(main())
