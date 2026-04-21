#!/usr/bin/env python3
"""Combined 5-lane summary for doe_run.py targets (roadmap #9).

Reads every per-target receipt under
  bench/out/doe-run/{target}/L{num_layers}-receipt.json
and emits one `doe_all_lanes_summary` JSON:

  - per-lane: target, status, backendId, outputSha256, elapsedMs,
    manifestSha256, graphSha256, interpretation
  - bundleIdentity: manifest/graph sha consistency across lanes
  - outputParityMatrix: output-sha agreement across runtime-producing
    lanes (webgpu-wgsl, csl-webgpu-emulator, csl-sdklayout), now
    annotated with tolerance verdicts (maxAbsDiff, toleranceVerdict
    ∈ {within_tolerance, exceeds_tolerance, shape_mismatch,
    non_finite, not_comparable}) when float32 outputs are readable
  - runtimeParityTolerance: rollup of the tolerance column with the
    declared atol (sourced from config/gemma-4-e2b-real-weight-fixture
    parityPolicy.atol when present, else 1e-3)
  - laneTaxonomy: which lanes produce output vs probe backend identity

Scope: identity + parity matrix. Not a performance claim. See
`docs/claim-discipline.md` for allowed/rejected claim boundaries.
Tolerance is the accuracy gate — digest mismatch is not the same as
"exceeds tolerance"; float-order differences across backends can
produce different digests while staying well within atol.

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

# Canonical E2B layer-block parity tolerance lives in the real-weight
# fixture's parityPolicy.atol. Kept as a constant path so the tool does
# not silently drift from the fixture. Fallback atol is the same 1e-3
# documented in docs/claim-discipline.md.
PARITY_FIXTURE_PATH = "config/gemma-4-e2b-real-weight-fixture.json"
DEFAULT_ATOL = 1e-3
SYNTHETIC_CLAIMABLE_DEPTH = 1


def evidence_eligibility(num_layers: int) -> dict:
    """Return the claim boundary for this all-lanes rollup.

    The unified entrypoint can be used diagnostically at deeper chain
    depths, but the current evidence bundle only promotes the L1
    synthetic layer-block path. Real weights, full-depth E2B, and
    hardware all require separate receipts before this function should
    return claimable=true for those modes.
    """
    if num_layers == SYNTHETIC_CLAIMABLE_DEPTH:
        return {
            "claimable": True,
            "evidenceTier": "synthetic_l1_layer_block",
            "claimableLabel": "L1 synthetic layer-block",
            "weightSource": "synthetic_seeded_rng",
            "scope": (
                "One Gemma-4 E2B-shaped layer-block with synthetic "
                "seeded tensors. This is not real weights, not full "
                "model inference, and not hardware execution."
            ),
            "blockers": [
                "real_weight_extractor",
                "l2_l4_l8_l35_claimable_receipts",
                "full_e2b_end_to_end",
                "cerebras_hardware_receipt",
            ],
        }
    return {
        "claimable": False,
        "evidenceTier": "diagnostic_synthetic_chain",
        "claimableLabel": f"L{num_layers} diagnostic only",
        "weightSource": "synthetic_seeded_rng",
        "scope": (
            "Diagnostic synthetic chain artifacts may exist at this "
            "depth, but they are not counted as claimable E2B evidence "
            "until the depth is promoted by an explicit receipt policy."
        ),
        "blockers": [
            "l1_synthetic_is_only_claimable_depth_today",
            "real_weight_extractor",
            "full_e2b_end_to_end",
            "cerebras_hardware_receipt",
        ],
    }


def load_declared_atol() -> tuple[float, str]:
    """Return (atol, source) from the canonical fixture, else default."""
    fixture = REPO_ROOT / PARITY_FIXTURE_PATH
    if fixture.is_file():
        try:
            data = json.loads(fixture.read_text(encoding="utf-8"))
            policy = data.get("parityPolicy") or {}
            atol = policy.get("atol")
            if isinstance(atol, (int, float)):
                return float(atol), PARITY_FIXTURE_PATH
        except (OSError, ValueError):
            pass
    return DEFAULT_ATOL, "default_1e-3"


def read_f32(path: Path):
    """Read a raw float32 binary file. Returns (array, error) tuple.

    Kept numpy-import-guarded so the summarizer still runs (without
    tolerance annotation) on environments that lack numpy.
    """
    try:
        import numpy as np  # noqa: PLC0415
    except ImportError:
        return None, "numpy_unavailable"
    if not path.is_file():
        return None, "file_absent"
    try:
        arr = np.fromfile(str(path), dtype=np.float32)
    except (OSError, ValueError) as exc:
        return None, f"read_failed: {exc}"
    return arr, None


def tolerance_verdict(
    left_path: Path, right_path: Path, atol: float,
) -> dict:
    """Compute max_abs diff between two f32 files under atol.

    Emits machine-readable verdict fields without raising. The caller
    merges these into the parity matrix entry.
    """
    import math  # noqa: PLC0415
    left_arr, left_err = read_f32(left_path)
    right_arr, right_err = read_f32(right_path)
    if left_err or right_err:
        return {
            "toleranceVerdict": "not_comparable",
            "toleranceReason": f"left={left_err or 'ok'} right={right_err or 'ok'}",
            "toleranceAtol": atol,
        }
    if left_arr.shape != right_arr.shape:
        return {
            "toleranceVerdict": "shape_mismatch",
            "toleranceReason": (
                f"left_elems={int(left_arr.size)} "
                f"right_elems={int(right_arr.size)}"
            ),
            "toleranceAtol": atol,
        }
    if left_arr.size == 0:
        return {
            "toleranceVerdict": "not_comparable",
            "toleranceReason": "empty_arrays",
            "toleranceAtol": atol,
        }
    import numpy as np  # noqa: PLC0415
    diff = np.abs(left_arr - right_arr)
    max_abs = float(diff.max())
    mean_abs = float(diff.mean())
    if math.isnan(max_abs) or math.isinf(max_abs):
        return {
            "toleranceVerdict": "non_finite",
            "toleranceReason": (
                f"max_abs={max_abs!r} — nan/inf present"
            ),
            "toleranceAtol": atol,
            "maxAbsDiff": max_abs,
            "meanAbsDiff": mean_abs,
        }
    within = max_abs <= atol
    return {
        "toleranceVerdict": (
            "within_tolerance" if within else "exceeds_tolerance"
        ),
        "toleranceAtol": atol,
        "maxAbsDiff": max_abs,
        "meanAbsDiff": mean_abs,
        "elemCount": int(left_arr.size),
    }


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
        receipt_path = run_dir / lane / f"L{args.num_layers}-receipt.json"
        receipt_rel = rel(receipt_path)
        receipt = load_receipt(run_dir, lane, args.num_layers)
        if receipt is None:
            per_lane.append({
                "lane": lane,
                "receiptPath": receipt_rel,
                "receiptPresent": False,
                "status": "missing",
            })
            continue
        bundle = receipt.get("bundle") or {}
        rt = receipt.get("runtimeMetadata") or {}
        per_lane.append({
            "lane": lane,
            "receiptPath": receipt_rel,
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
    atol, atol_source = load_declared_atol()
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
        entry = {
            "left": left["lane"],
            "right": right["lane"],
            "leftOutputSha256": left["outputSha256"],
            "rightOutputSha256": right["outputSha256"],
            "verdict": (
                "bit_exact_match"
                if left["outputSha256"] == right["outputSha256"]
                else "digest_mismatch"
            ),
        }
        left_out = left.get("outputPath")
        right_out = right.get("outputPath")
        if left_out and right_out:
            entry.update(tolerance_verdict(
                resolve(left_out), resolve(right_out), atol,
            ))
        parity_entries.append(entry)

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
    eligibility = evidence_eligibility(args.num_layers)
    if (
        args.num_layers == SYNTHETIC_CLAIMABLE_DEPTH
        and isinstance(real_weight_block, dict)
        and (real_weight_block.get("promotionCriteriaMet") or {}).get(
            "outputParityPassed"
        ) is True
    ):
        eligibility["claimableLabel"] = (
            "L1 synthetic + real-weight smoke layer-block"
        )
        eligibility["weightSource"] = (
            "synthetic_seeded_rng_and_bf16_derived_smoke_slices"
        )
        eligibility["scope"] = (
            "One Gemma-4 E2B-shaped synthetic L1 layer-block plus one "
            "BF16-derived real-weight L1 smoke layer-block. This is not "
            "full model inference and not hardware execution."
        )
        eligibility["realWeightClaimable"] = True
        eligibility["realWeightScope"] = (
            "BF16-derived Gemma-4 E2B weight slices are evidenced for "
            "the L1 smoke layer-block contract only."
        )
        eligibility["blockers"] = [
            "l2_l4_l8_l35_claimable_receipts",
            "full_e2b_end_to_end",
            "cerebras_hardware_receipt",
        ]
    else:
        eligibility["realWeightClaimable"] = False

    # Tolerance rollup across runtime-producing lane pairs. A pair is
    # "tolerance-informative" if it has a toleranceVerdict in
    # {within_tolerance, exceeds_tolerance, shape_mismatch, non_finite}.
    # Pairs with toleranceVerdict=not_comparable (numpy unavailable or
    # file absent) are excluded from the informative count so the
    # rollup does not conflate tooling gaps with real parity findings.
    informative = [
        p for p in parity_entries
        if p.get("toleranceVerdict") in (
            "within_tolerance", "exceeds_tolerance",
            "shape_mismatch", "non_finite",
        )
    ]
    within_count = sum(
        1 for p in informative
        if p.get("toleranceVerdict") == "within_tolerance"
    )
    exceeds_count = sum(
        1 for p in informative
        if p.get("toleranceVerdict") == "exceeds_tolerance"
    )
    hard_fail_count = sum(
        1 for p in informative
        if p.get("toleranceVerdict") in ("shape_mismatch", "non_finite")
    )
    if not informative:
        tolerance_rollup_verdict = "not_evaluated"
    elif hard_fail_count > 0:
        tolerance_rollup_verdict = "shape_or_non_finite_failure"
    elif exceeds_count > 0:
        tolerance_rollup_verdict = "exceeds_tolerance"
    else:
        tolerance_rollup_verdict = "all_within_tolerance"

    summary = {
        "schemaVersion": 1,
        "artifactKind": "doe_all_lanes_summary",
        "numLayers": args.num_layers,
        "evidenceEligibility": eligibility,
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
        "runtimeParityTolerance": {
            "atol": atol,
            "atolSource": atol_source,
            "informativePairCount": len(informative),
            "withinToleranceCount": within_count,
            "exceedsToleranceCount": exceeds_count,
            "hardFailCount": hard_fail_count,
            "rollupVerdict": tolerance_rollup_verdict,
        },
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
        f"tolerance(atol={atol:g}): within={within_count} exceeds={exceeds_count} "
        f"hard_fail={hard_fail_count} rollup={tolerance_rollup_verdict}. "
        f"verdict={overall}"
    )
    return 0 if overall == "all_lanes_identity_and_parity_matched" else 0


if __name__ == "__main__":
    sys.exit(main())
