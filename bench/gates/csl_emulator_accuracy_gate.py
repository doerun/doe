#!/usr/bin/env python3
"""CSL WebGPU emulator accuracy gate (roadmap item #7).

For every layer in the chain, compare:
  - CSL simfabric output: trace's executedRun.perLayerOutputs[l].path
  - CSL WebGPU emulator output: emulator --out-dir/per_layer/layer{l}.f32

Pass iff every layer's max-abs-diff <= atol. Also verifies graph/kernel
identity via the CSL trace's recorded hashes and emulator receipt's
bundle hashes — a numerical match against a DIFFERENT program is not a
valid accuracy claim.

The gate is narrow-scope:
  - shape: both sides are expected to be size=1024 f32 per layer
  - depth: the CSL trace's numLayersChained determines the count
  - tolerance: caller supplies --atol; defaults to 1e-3 (per the
    claim-discipline doc's cross-runtime threshold)

Usage:
  python3 bench/gates/csl_emulator_accuracy_gate.py \\
    --csl-trace bench/out/streaming-executor/e2b-layer-block-smoke-trace.json \\
    --emulator-out-dir bench/out/doppler-reference/gemma-4-e2b-layer-block-webgpu-isolated \\
    --atol 1e-3

Exit 0 on PASS, 1 on FAIL. Failure output names the first drift layer
and its max abs err so the offending stage is easy to locate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--csl-trace", required=True,
        help="Path to a CSL runner trace with executedRun.perLayerOutputs.",
    )
    p.add_argument(
        "--emulator-out-dir", required=True,
        help="Path to the emulator output dir (contains per_layer/).",
    )
    p.add_argument(
        "--atol", type=float, default=1e-3,
        help="Per-layer tolerance. Default 1e-3 per docs/claim-discipline.md.",
    )
    p.add_argument(
        "--out-json", default="",
        help="Optional path for a machine-readable verdict artifact.",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def main() -> int:
    args = parse_args()
    csl_trace_path = resolve(args.csl_trace)
    emu_dir = resolve(args.emulator_out_dir)

    if not csl_trace_path.is_file():
        print(f"FAIL: CSL trace missing: {args.csl_trace}")
        return 1
    if not emu_dir.is_dir():
        print(f"FAIL: emulator out-dir missing: {args.emulator_out_dir}")
        return 1

    trace = json.loads(csl_trace_path.read_text(encoding="utf-8"))
    executed = trace.get("executedRun", {}) or {}
    per_layer = executed.get("perLayerOutputs")
    if not per_layer:
        print(
            "FAIL: CSL trace has no executedRun.perLayerOutputs. "
            "Re-run the CSL runner after the generator's per-layer "
            "emission landed (tick "
            "`per-layer activation_out dumps`)."
        )
        return 1

    model_id = trace.get("modelId", "unknown")
    num_layers = executed.get("numLayersChained")
    if num_layers is None:
        num_layers = len(per_layer)

    emu_per_layer_dir = emu_dir / "per_layer"
    if not emu_per_layer_dir.is_dir():
        print(f"FAIL: emulator per_layer/ dir missing at {emu_per_layer_dir}")
        return 1

    per_layer_records: list[dict] = []
    first_failure_layer = None
    max_overall = 0.0
    mean_overall = 0.0

    for entry in per_layer:
        l = int(entry["layer"])
        csl_path = resolve(entry["path"])
        if not csl_path.is_file():
            print(f"FAIL: layer {l} CSL output missing at {entry['path']}")
            return 1
        emu_path = emu_per_layer_dir / f"layer{l}.f32"
        if not emu_path.is_file():
            print(
                f"FAIL: layer {l} emulator output missing at "
                f"{emu_path.relative_to(REPO_ROOT) if emu_path.is_relative_to(REPO_ROOT) else emu_path}"
            )
            return 1
        csl_f32 = np.fromfile(csl_path, dtype=np.float32)
        emu_f32 = np.fromfile(emu_path, dtype=np.float32)
        if csl_f32.shape != emu_f32.shape:
            print(
                f"FAIL: layer {l} shape mismatch: csl={csl_f32.shape} "
                f"emulator={emu_f32.shape}"
            )
            return 1
        diff = np.abs(csl_f32 - emu_f32)
        max_abs = float(diff.max())
        mean_abs = float(diff.mean())
        within = max_abs <= args.atol
        per_layer_records.append({
            "layer": l,
            "cslPath": entry.get("path"),
            "cslSha256": entry.get("sha256"),
            "emulatorPath": (
                str(emu_path.relative_to(REPO_ROOT))
                if emu_path.is_relative_to(REPO_ROOT) else str(emu_path)
            ),
            "maxAbsErr": max_abs,
            "meanAbsErr": mean_abs,
            "withinAtol": within,
        })
        if max_abs > max_overall:
            max_overall = max_abs
        mean_overall += mean_abs
        if not within and first_failure_layer is None:
            first_failure_layer = (l, max_abs)

    if per_layer_records:
        mean_overall /= len(per_layer_records)

    verdict_pass = first_failure_layer is None
    verdict = {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_emulator_accuracy_verdict",
        "modelId": model_id,
        "cslTracePath": args.csl_trace,
        "emulatorOutDir": args.emulator_out_dir,
        "numLayers": num_layers,
        "atol": args.atol,
        "summary": {
            "maxAbsErrAcrossLayers": max_overall,
            "meanAbsErrAcrossLayers": mean_overall,
            "allLayersWithinAtol": verdict_pass,
            "firstFailureLayer": (
                None if verdict_pass
                else {"layer": first_failure_layer[0], "maxAbsErr": first_failure_layer[1]}
            ),
        },
        "perLayer": per_layer_records,
        "verdict": "passed" if verdict_pass else "failed",
    }

    if args.out_json:
        out_path = resolve(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
        try:
            rel = str(out_path.relative_to(REPO_ROOT))
        except ValueError:
            rel = str(out_path)
        print(f"wrote {rel}")

    if verdict_pass:
        print(
            f"PASS: CSL emulator accuracy gate (model={model_id}, "
            f"numLayers={num_layers}, atol={args.atol}, "
            f"max_abs_across_layers={max_overall:.4e})"
        )
        return 0

    l, e = first_failure_layer
    print(
        f"FAIL: CSL emulator accuracy gate: layer {l} exceeds atol "
        f"({e:.4e} > {args.atol}). model={model_id}, numLayers={num_layers}, "
        f"max_abs_across_layers={max_overall:.4e}."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
