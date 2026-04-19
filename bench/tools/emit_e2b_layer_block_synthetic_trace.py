#!/usr/bin/env python3
"""Emit a numpy-only "synthetic-trace" companion to the generated E2B
layer-block runner.

The generated runner at bench/runners/csl-runners/e2b_layer_block_smoke.py
imports the Cerebras SDK at module top, so it cannot run without
cs_python on PATH. This tool imports the SAME canonical
compute_layer_block helper that the runner uses
(bench/runners/csl-runners/_e2b_layer_block_compute.py — single
source of truth) and runs the num_layers chain entirely in numpy. The output is a JSON file shaped
like a doe_streaming_executor_trace: same field names, same per-layer
arrays, with dataSource.kind="numpy_only_no_simulator" and
executedRun.status="synthetic_numpy_only".

The parity-contract gate (parallel-safe support track) can consume this
synthetic trace immediately to exercise its logic against the right
trace shape, without waiting for cs_python. When cs_python lands and
the real runner produces a "synthetic_seeded_rng" / "manifest_slice"
trace, the gate's filter on dataSource.kind picks up the upgrade
automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]

# Canonical compute_layer_block lives next to the SDK runner. Both
# the runner and this tool import the same source so the parity-
# contract gate has one source of truth (no exec/source-extraction).
sys.path.insert(0, str(REPO_ROOT / "bench" / "runners" / "csl-runners"))
from _e2b_layer_block_compute import compute_layer_block  # noqa: E402

# Re-use the generator's per-kernel-shape derivation so the synthetic
# trace satisfies perKernelShapes (minItems: 14) without duplicating
# the 14-pattern table.
sys.path.insert(0, str(REPO_ROOT / "bench" / "tools"))
from generate_e2b_layer_block_runner import (  # noqa: E402
    derive_per_kernel_shapes,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--runner",
        default="bench/runners/csl-runners/e2b_layer_block_smoke.py",
    )
    p.add_argument(
        "--kernel-source",
        default=(
            "bench/out/streaming-executor/e2b-layer-block-source/"
            "transformer_layer_shape.csl"
        ),
    )
    p.add_argument(
        "--execution-plan",
        default="bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json",
    )
    p.add_argument("--size", type=int, default=1024,
                   help="Per-stream f32 count (matches runner default).")
    p.add_argument(
        "--num-layers", type=int, default=35,
        help="Chain depth (E2B manifest.modelConfig.numLayers).",
    )
    p.add_argument("--initial-rows-seed", type=int, default=1000)
    p.add_argument("--per-layer-base", type=int, default=2000)
    p.add_argument(
        "--out",
        default="bench/out/streaming-executor/e2b-layer-block-synthetic-trace.json",
    )
    return p.parse_args()


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def main() -> int:
    args = parse_args()
    runner_path = resolve(args.runner)  # kept for back-compat / inspection
    kernel_path = resolve(args.kernel_source)
    plan_path = resolve(args.execution_plan)
    out_path = resolve(args.out)
    # compute_layer_block is imported at module top from
    # _e2b_layer_block_compute (the canonical source); the runner-path
    # arg is no longer used to lift the function via exec.
    _ = runner_path  # silence "unused" lint without changing the CLI

    rng_init = np.random.default_rng(seed=args.initial_rows_seed)
    initial_rows = rng_init.standard_normal(
        size=args.size, dtype=np.float32
    )

    per_layer_proj: list = []
    per_layer_wts: list = []
    per_layer_seeds: list = []
    for l_idx in range(args.num_layers):
        seed_l = args.per_layer_base + l_idx
        rng_l = np.random.default_rng(seed=seed_l)
        per_layer_proj.append(
            rng_l.standard_normal(size=args.size, dtype=np.float32)
        )
        per_layer_wts.append(
            rng_l.standard_normal(size=args.size, dtype=np.float32)
        )
        per_layer_seeds.append(seed_l)

    per_layer_max_abs: list = []
    per_layer_finite: list = []
    per_layer_elapsed_ms: list = []

    rows_curr = initial_rows.copy()
    chain_start = time.time()
    for l_idx in range(args.num_layers):
        layer_start = time.time()
        out = compute_layer_block(
            rows_curr,
            per_layer_proj[l_idx],
            per_layer_wts[l_idx],
            args.size,
        )
        per_layer_elapsed_ms.append((time.time() - layer_start) * 1000.0)
        per_layer_max_abs.append(float(np.max(np.abs(out))))
        per_layer_finite.append(bool(np.all(np.isfinite(out))))
        rows_curr = out
    chain_elapsed_ms = (time.time() - chain_start) * 1000.0

    finite_all = all(per_layer_finite)
    final_max_abs = per_layer_max_abs[-1] if per_layer_max_abs else -1.0

    # Output tensor digest: write the final-layer activation_out as f32
    # bytes next to the trace, then capture {dtype, shape, path, sha256,
    # preview}. doe_csl_reference_parity gate's cslRun.output field
    # consumes this — once a Doppler/browser reference output is bound,
    # --require-output-parity flips the gate to passed.
    output_path = out_path.with_suffix(".output.f32")
    rows_curr.astype(np.float32).tofile(output_path)
    output_sha = hashlib.sha256()
    with output_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            output_sha.update(chunk)
    output_digest = {
        "dtype": "float32",
        "shape": [int(args.size)],
        "path": str(output_path.relative_to(REPO_ROOT)),
        "sha256": output_sha.hexdigest(),
        "preview": [float(rows_curr[i]) for i in range(min(8, args.size))],
    }

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    # Per-kernel shapes from the same derivation the generator uses.
    manifest_path = (
        REPO_ROOT / "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    per_kernel_shapes = derive_per_kernel_shapes(plan, manifest, args.size)
    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": plan.get("modelId", ""),
        "executorIteration": 8,
        "sourcePlan": {
            "streamGraphPath": "",
            "executionPlanPath": str(plan_path.relative_to(REPO_ROOT)),
            "kernelSourcePath": str(kernel_path.relative_to(REPO_ROOT)),
        },
        "region": {
            "regionId": "transformer_layer_shape_synthetic",
            "width": 1,
            "height": 1,
            "peCount": 1,
        },
        "executedCompile": {
            "compilePrefix": "synthetic_numpy_only_no_compile",
            "elapsedMs": 0.0,
            "status": "succeeded",
            "syntheticOverrideNote": (
                "executedCompile.status is 'succeeded' to satisfy the "
                "trace schema enum {succeeded, failed}, but no CSL "
                "compile actually ran. The authoritative synthetic "
                "marker is executedRun.dataSource.kind = "
                "'numpy_only_no_simulator'."
            ),
        },
        "executedRun": {
            "status": "synthetic_numpy_only",
            "elapsedMs": chain_elapsed_ms,
            "numLayersChained": args.num_layers,
            "perLayerElapsedMs": per_layer_elapsed_ms,
            "observedBytesTransferredPerPe":
                args.size * 4 * 4 * args.num_layers,
            "observedBytesTransferredTotal":
                args.size * 4 * 4 * args.num_layers,
            "dataSource": {
                "kind": "numpy_only_no_simulator",
                "initialRowsSeed": args.initial_rows_seed,
                "perLayerBase": args.per_layer_base,
                "perLayerSeeds": per_layer_seeds,
                "weightsDir": None,
                "perLayerProjSource": [
                    "synthetic_seed:" + str(s) for s in per_layer_seeds
                ],
                "perLayerWtsSource": [
                    "synthetic_seed:" + str(s) for s in per_layer_seeds
                ],
                "swapBoundary": (
                    "Numpy-only synthetic trace from "
                    "bench/tools/emit_e2b_layer_block_synthetic_trace.py. "
                    "Same compute_layer_block as the SDK runner, no CSL "
                    "compile or simfabric run. The parity-contract gate "
                    "should treat this as a structural-shape probe, not "
                    "a simulator pass — promotion to simulator_success "
                    "requires a real-runner trace with dataSource.kind "
                    "in {synthetic_seeded_rng, manifest_weights_*} and "
                    "executedRun.status='succeeded'."
                ),
            },
            "numericalParity": {
                "maxAbsErr": 0.0,
                "perLayerMaxAbsErr": [0.0] * args.num_layers,
                "atol": 0,
                "passed": finite_all,
                "perLayerOutputMaxAbs": per_layer_max_abs,
                "perLayerOutputFinite": per_layer_finite,
                "finalLayerMaxAbs": final_max_abs,
                "passNote": (
                    "passed=true here just means every numpy-evaluated "
                    "layer produced a finite output; this trace cannot "
                    "claim CSL/numpy bit-exact parity because no CSL "
                    "compile/run happened. The real-runner trace (when "
                    "cs_python is available) carries the np.array_equal "
                    "comparison."
                ),
            },
            "output": output_digest,
        },
        "streams": [
            {"role": "input",  "color": "rx_ple_rows",
             "size": args.size, "dtype": "float32"},
            {"role": "input",  "color": "rx_ple_projection",
             "size": args.size, "dtype": "float32"},
            {"role": "input",  "color": "rx_layer_weights",
             "size": args.size, "dtype": "float32"},
            {"role": "output", "color": "tx_activation",
             "size": args.size, "dtype": "float32"},
        ],
        "layerBlockSmoke": {
            "planPath": str(plan_path.relative_to(REPO_ROOT)),
            "planSha256": sha256_file(plan_path),
            "layerIndex": 0,
            "regionName": "transformer_layer_shape",
            "kernelSourcePath": str(kernel_path.relative_to(REPO_ROOT)),
            "kernelSourceSha256": sha256_file(kernel_path),
            "kernelIsStub": False,
            "kernelStage": (
                "pre_attn_rmsnorm+mha_8head_hd8_kv4_multi_pair_rope_real"
                "_poly_c1_softmax+residual"
                "+post_attn_rmsnorm+gated_mlp_poly_c1_gelu"
                "+multi_layer_chain"
            ),
            "combineRule": (
                "Numpy-only synthetic trace; combineRule shape matches the "
                "real runner's bit-exact reference. See "
                "bench/runners/csl-runners/e2b_layer_block_smoke.py for "
                "the canonical formula."
            ),
            "status": "synthetic_numpy_only",
            "targetMode": "local_simfabric",
            "targetModeSyntheticOverride": (
                "no_simulator_numpy_only — targetMode is set to "
                "local_simfabric to satisfy the trace schema enum, "
                "but the actual run was numpy-only with no CSL "
                "compile or simfabric. dataSource.kind and "
                "executedRun.status are the authoritative synthetic "
                "markers."
            ),
            "compileArtifactDir":    "synthetic_numpy_only_no_compile",
            "compileArtifactPrefix": "synthetic_numpy_only_no_compile",
            "connectionGraph": {
                "region": "transformer_layer_shape",
                "grid": {"width": 1, "height": 1, "peCount": 1, "place": [4, 2]},
                "inputPorts": [
                    {"color": "rx_ple_rows",
                     "edge": "LEFT",   "size": args.size},
                    {"color": "rx_ple_projection",
                     "edge": "TOP",    "size": args.size},
                    {"color": "rx_layer_weights",
                     "edge": "BOTTOM", "size": args.size},
                ],
                "outputPorts": [
                    {"color": "tx_activation",
                     "edge": "RIGHT",  "size": args.size},
                ],
                "crossRegionConnections": [],
            },
            "hostIoLayout": [
                {"streamId": "ple_rows_stream",       "role": "input",
                 "elementsPerPe": args.size, "dtype": "float32",
                 "order": "row_major", "roi": [4, 2, 1, 1],
                 "tileBehavior": "stream", "planPayloadBytes": 2},
                {"streamId": "ple_projection_stream", "role": "input",
                 "elementsPerPe": args.size, "dtype": "float32",
                 "order": "row_major", "roi": [4, 2, 1, 1],
                 "tileBehavior": "stream", "planPayloadBytes": 23},
                {"streamId": "layer_weights_stream",  "role": "input",
                 "elementsPerPe": args.size, "dtype": "float32",
                 "order": "row_major", "roi": [4, 2, 1, 1],
                 "tileBehavior": "stream", "planPayloadBytes": 2166},
                {"streamId": "activation_out_stream", "role": "output",
                 "elementsPerPe": args.size, "dtype": "float32",
                 "order": "row_major", "roi": [4, 2, 1, 1],
                 "tileBehavior": "stream", "planPayloadBytes": 0},
            ],
            "ioBufferSizes": {
                "rows": 1024, "proj": 1024, "wts": 1024, "activation": 1024,
            },
            "sendReceiveCounts": {
                "sends": 3 * args.num_layers,
                "receives": args.num_layers,
            },
            "simulatorArtifactPaths": {
                "compileDir": None,
                "runLogs": [],
                "coreFile": None,
            },
            "sourceModelReceiptPath":
                "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
            "perKernelShapes": per_kernel_shapes,
        },
        "notes": (
            "Numpy-only synthetic trace emitted by "
            "bench/tools/emit_e2b_layer_block_synthetic_trace.py to give "
            "the parity-contract gate a real-shaped artifact to consume "
            "before cs_python is available. dataSource.kind = "
            "'numpy_only_no_simulator' lets the gate filter this out of "
            "any simulator_success promotion logic."
        ),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(
        "wrote " + str(out_path.relative_to(REPO_ROOT)) +
        " (" + str(args.num_layers) + " layers, " +
        f"{chain_elapsed_ms:.1f}ms, finite_all={finite_all}, " +
        f"finalMaxAbs={final_max_abs:.4f})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
