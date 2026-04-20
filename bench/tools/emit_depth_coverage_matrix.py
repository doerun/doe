#!/usr/bin/env python3
"""Emit an honest depth-coverage matrix for the Doe 5-lane rollup.

Declared chain depths in the cockpit UI are L=1, 2, 4, 8, 35 (the E2B
full depth). Actual per-target receipts live at
`bench/out/doe-run/{lane}/L{N}-receipt.json`. Today only L=1 has
receipts; the other depths are aspirational accuracy-gate targets named
in the Build-order plan and the cockpit depth selector.

Without an enumerated coverage artifact, a reader of the bundle cannot
distinguish "L=1 is the only evidenced depth" from "L=8 just happens to
be selected in the UI." This tool emits one JSON artifact that states,
for every declared depth × every lane, whether a receipt is on disk —
and whether a tolerance-aware all-lanes summary has been produced for
that depth.

Scope caveat: coverage is a structural check. A receiptPresent=true row
says "this lane emitted a receipt at this depth" — it does not revalidate
parity. That remains the job of
`bench/tools/summarize_doe_run_lanes.py`.

Usage:
  python3 bench/tools/emit_depth_coverage_matrix.py \\
    --out-json bench/out/doe-run/depth-coverage-matrix.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Declared accuracy-gate depths. Keep in sync with the cockpit's
# num-layers-select options in
# demos/gemma4-e2b-csl-sim/index.html. A mismatch is a self-check
# target; see e2b_layer_block_self_check.py.
DECLARED_DEPTHS = [1, 2, 4, 8, 35]

# Same lane taxonomy as summarize_doe_run_lanes.py.
LANES = [
    "webgpu-wgsl",
    "doe-metal",
    "doe-vulkan",
    "csl-sdklayout",
    "csl-webgpu-emulator",
]
RUNTIME_OUTPUT_LANES = {"webgpu-wgsl", "csl-sdklayout", "csl-webgpu-emulator"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", default="bench/out/doe-run")
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


def per_cell(run_dir: Path, depth: int, lane: str) -> dict:
    receipt_path = run_dir / lane / f"L{depth}-receipt.json"
    cell = {
        "depth": depth,
        "lane": lane,
        "receiptPath": rel(receipt_path),
        "receiptPresent": receipt_path.is_file(),
        "status": None,
        "outputSha256": None,
        "laneRole": (
            "runtime_output"
            if lane in RUNTIME_OUTPUT_LANES
            else "backend_identity_probe"
        ),
    }
    if not cell["receiptPresent"]:
        return cell
    try:
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cell
    cell["status"] = data.get("status")
    cell["outputSha256"] = data.get("outputSha256")
    return cell


def load_summary(run_dir: Path, depth: int) -> dict | None:
    path = run_dir / f"all-lanes-summary-L{depth}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main() -> int:
    args = parse_args()
    run_dir = resolve(args.run_dir)

    coverage = []
    for depth in DECLARED_DEPTHS:
        cells = [per_cell(run_dir, depth, lane) for lane in LANES]
        present = sum(1 for c in cells if c["receiptPresent"])
        all_succeeded = bool(cells) and all(
            c["receiptPresent"] and c["status"] == "succeeded" for c in cells
        )

        summary = load_summary(run_dir, depth)
        rollup_verdict = None
        tolerance_rollup = None
        summary_path = rel(run_dir / f"all-lanes-summary-L{depth}.json")
        if summary is not None:
            rollup_verdict = summary.get("verdict")
            rpt = summary.get("runtimeParityTolerance") or {}
            tolerance_rollup = rpt.get("rollupVerdict")

        coverage.append({
            "depth": depth,
            "lanes": cells,
            "laneReceiptsPresent": present,
            "laneReceiptCount": len(LANES),
            "allLanesSucceeded": all_succeeded,
            "summaryPath": summary_path,
            "summaryPresent": summary is not None,
            "summaryVerdict": rollup_verdict,
            "toleranceRollupVerdict": tolerance_rollup,
        })

    depths_any_receipt = [c["depth"] for c in coverage if c["laneReceiptsPresent"] > 0]
    depths_full_coverage = [c["depth"] for c in coverage if c["allLanesSucceeded"]]
    depths_within_tolerance = [
        c["depth"] for c in coverage
        if c["toleranceRollupVerdict"] == "all_within_tolerance"
    ]

    artifact = {
        "schemaVersion": 1,
        "artifactKind": "doe_depth_coverage_matrix",
        "declaredDepths": DECLARED_DEPTHS,
        "lanes": LANES,
        "coverage": coverage,
        "rollup": {
            "depthsWithAnyReceipt": depths_any_receipt,
            "depthsWithFullLaneCoverage": depths_full_coverage,
            "depthsAllWithinTolerance": depths_within_tolerance,
            "declaredCount": len(DECLARED_DEPTHS),
            "anyReceiptCount": len(depths_any_receipt),
            "fullCoverageCount": len(depths_full_coverage),
            "withinToleranceCount": len(depths_within_tolerance),
        },
        "claimScope": (
            "Structural coverage only: enumerates which declared depths "
            "× lanes have on-disk receipts. Does NOT revalidate parity "
            "or tolerance — see all-lanes-summary-L{N}.json "
            "(runtimeParityTolerance) for the per-depth tolerance "
            "verdict."
        ),
    }

    if args.out_json:
        out_path = resolve(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(artifact, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {rel(out_path)}")

    print(
        f"declared depths: {len(DECLARED_DEPTHS)} ({DECLARED_DEPTHS}). "
        f"any-receipt: {depths_any_receipt}. "
        f"full-lane-coverage: {depths_full_coverage}. "
        f"all-within-tolerance: {depths_within_tolerance}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
