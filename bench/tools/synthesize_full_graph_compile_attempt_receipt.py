#!/usr/bin/env python3
"""Synthesize the 31B full-graph compile attempt receipt.

Mitigates "Full inference graph compile" from
docs/cerebras-north-star.md (Remaining no-hardware evidence gaps).

The existing manifest-shape compile-attempt receipt
(`bench/out/r3-1-31b-manifest-compile-attempt/`) and the threshold
sweep (`bench/out/r3-1-31b-manifest-compile-sweep/`) test only the
transformer_layer_shape kernel. The 31B host-plan
(`bench/out/31b-full-graph/host-plan.json`) names 17 distinct
compile targets — embed, ple_embed, ple_proj, ple_rmsnorm,
ple_residual, rmsnorm, tiled, rope, attn_small, residual, gelu, gemv,
kv_write, attn_decode_sliding, kv_write_shared, attn_decode, sample.
A "full inference graph compile attempt" means: attempt cslc on each
of those 17 targets at manifest shape and aggregate.

This synthesizer reads the host-plan, enumerates compileTargets, and
emits a typed-blocker receipt that:
  - lists every compile target by name with its layout + pe_program
    paths (relative to the bundle compile root),
  - binds to the layer-block sweep's known threshold so reviewers can
    see which targets *probably* fail at manifest shape (those whose
    per-PE residency mirrors the layer-block kernel),
  - names the operational blocker — the bundle compile root with the
    materialized layout sources for all 17 kernels does not yet exist
    in repo state, and producing it requires
    `runtime/zig/zig-out/bin/doe-csl-host-plan-tool` to emit fresh
    layouts at manifest shape. That is doable but is a multi-minute
    operation per kernel; doing all 17 sequentially is ~10-30 minutes
    of cslc work.

The receipt does not invent compile verdicts. It records the structural
attempt-readiness state + the named runner extension that closes the
gap. When the host-plan-tool materializes the 17 layouts and a follow-up
script iterates cslc per target, this receipt's `compileTargets[].verdict`
fields can be filled in.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOSTPLAN = REPO_ROOT / "bench/out/31b-full-graph/host-plan.json"
DEFAULT_SWEEP_SUMMARY = (
    REPO_ROOT / "bench/out/r3-1-31b-manifest-compile-sweep/sweep-summary.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host-plan", type=Path, default=DEFAULT_HOSTPLAN)
    p.add_argument(
        "--sweep-summary", type=Path, default=DEFAULT_SWEEP_SUMMARY
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--manifest-size",
        type=int,
        default=4096,
        help=(
            "Compile size to record as the manifest target. The receipt "
            "doesn't actually invoke cslc; this is the size that the "
            "follow-up cslc loop would attempt."
        ),
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.host_plan.is_file():
        sys.stderr.write(
            f"synthesize_full_graph_compile_attempt_receipt: host-plan "
            f"{args.host_plan} not found\n"
        )
        return 2
    host_plan = json.loads(args.host_plan.read_text(encoding="utf-8"))
    compile_targets = host_plan.get("compileTargets") or []
    if not compile_targets:
        sys.stderr.write(
            "synthesize_full_graph_compile_attempt_receipt: host-plan "
            "has no compileTargets\n"
        )
        return 2

    sweep_summary = None
    if args.sweep_summary.is_file():
        sweep_summary = json.loads(
            args.sweep_summary.read_text(encoding="utf-8")
        )

    target_records = []
    for target in compile_targets:
        if not isinstance(target, dict):
            continue
        target_records.append(
            {
                "name": target.get("name", "unknown"),
                "layout": target.get("layout", ""),
                "peProgram": target.get("peProgram", ""),
                "compileVerdict": "not_attempted",
                "compileSize": args.manifest_size,
                "blocker": (
                    "layout_pe_program_sources_not_materialized_in_repo"
                ),
            }
        )

    threshold_note = None
    if sweep_summary is not None:
        threshold = sweep_summary.get("threshold") or {}
        last_passing = threshold.get("lastPassing")
        first_failing = threshold.get("firstFailing")
        threshold_note = {
            "sourceSweepPath": str(
                args.sweep_summary.relative_to(REPO_ROOT)
                if args.sweep_summary.is_absolute()
                and str(args.sweep_summary).startswith(str(REPO_ROOT))
                else args.sweep_summary
            ),
            "lastPassingLayerBlockSize": last_passing,
            "firstFailingLayerBlockSize": first_failing,
            "implication": (
                f"transformer_layer_shape compiles up to size={last_passing} "
                f"and fails at size>={first_failing}. Compile targets that "
                f"share its per-PE residency profile (rmsnorm, tiled, rope, "
                f"residual, gelu, gemv) are likely to inherit the same "
                f"failure pattern at manifest shape; small-state targets "
                f"(embed, sample, kv_write) probably compile cleanly. The "
                f"receipt records this as a hypothesis pinned to the sweep, "
                f"not a measured outcome."
            ),
        }

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_full_graph_compile_attempt_receipt",
        "modelId": host_plan.get("modelId")
        or (host_plan.get("contract") if isinstance(host_plan.get("contract"), str) else "unknown"),
        "target": host_plan.get("target", "wse3"),
        "manifestSize": args.manifest_size,
        "sourceHostPlan": str(
            args.host_plan.relative_to(REPO_ROOT)
            if args.host_plan.is_absolute()
            and str(args.host_plan).startswith(str(REPO_ROOT))
            else args.host_plan
        ),
        "compileTargetCount": len(target_records),
        "compileTargets": target_records,
        "thresholdNote": threshold_note,
        "blocker": {
            "class": "full_graph_compile_loop_absent",
            "detail": (
                "host-plan.json names 17 compile targets but the bundle "
                "compile root with materialized layout.csl + pe_program.csl "
                "for each does not exist in repo state. Producing it "
                "requires runtime/zig/zig-out/bin/doe-csl-host-plan-tool to "
                "emit fresh per-target layouts at manifest shape, then a "
                "loop that invokes cslc on each. Total work: ~10-30 minutes "
                "of cslc time plus the orchestrator code."
            ),
            "namedRunnerExtensions": [
                "runtime/zig/zig-out/bin/doe-csl-host-plan-tool: re-run "
                "with --bundle-root <fresh-dir> --manifest-shape so the "
                "17 compile-target layouts materialize on disk.",
                "bench/runners/csl-runners/(new)full_graph_compile_loop.py: "
                "iterate compile targets, run cslc per target with "
                "DOE_CSL_SCRATCH_CWD set to a per-target scratch dir, "
                "capture compileVerdict {pass, failed_typed, error}, and "
                "emit a doe_full_graph_compile_attempt_receipt with real "
                "verdicts.",
                "(optional) bench/gates/full_graph_compile_attempt_gate.py: "
                "block release until the receipt's compileTargets[].verdict "
                "fields are non-not_attempted for every entry.",
            ],
        },
        "claim": {
            "scope": (
                "31B host-plan compile-target inventory is pinned. The "
                "receipt records the 17 named targets, the manifest-shape "
                "compile size that would be attempted, and the layer-block "
                "threshold that lets reviewers predict which targets "
                "probably fail."
            ),
            "notWhat": (
                "Not a compile attempt. Every compileTargets[].verdict is "
                "not_attempted; this receipt is structural, not numerical. "
                "Not a hardware receipt. Not a manifest-shape success. "
                "When the follow-up loop lands, this receipt is replaced "
                "by one with real verdicts."
            ),
            "summary": (
                "31B host-plan names 17 compile targets at manifest shape; "
                "compile loop blocked on layout materialization."
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.out} (typed blocker, "
        f"compileTargetCount={len(target_records)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
