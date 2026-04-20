#!/usr/bin/env python3
"""Doppler-side reference export contract (stub).

This file is the executable specification for the Doppler command
that emits the cross-runtime reference the CSL parity gate consumes.
It produces every artifact the gate and the
`emit_csl_reference_parity_sample.py --external-reference-output`
path need, in exactly the file layout the gate expects:

  <out-dir>/
    activation_out.f32          -- the f32 output vector (1024 floats)
    export_receipt.json         -- { manifestSha256, graphSha256,
                                    inputTensorSha256, weightSha256,
                                    outputSha256, runtime, shape,
                                    perLayerOutputSha256 }

The CURRENT implementation computes the same compute_layer_block
semantic as the CSL runner (scalar-f32 in-order ops, shared
`_e2b_layer_block_compute` module) using the same seeded-RNG inputs.
When Doppler re-implements this via WebGPU/Node, they should KEEP
this CLI signature and REPLACE the compute block with their real
runtime path. The receipt's `runtime` field documents which
implementation produced the output:

  * numpy_reference_stub        -- this file (trivial cross-proof,
                                   byte-matches CSL since both sides
                                   use the same compute module)
  * doppler_browser_webgpu      -- real Doppler WebGPU in the browser
  * doppler_node_webgpu         -- real Doppler Node+WebGPU harness
  * doppler_exported_fixture    -- pre-computed fixture file

Parity mode the gate should be invoked with:

  * numpy_reference_stub        -> --require-output-parity (bit-exact)
  * doppler_browser_webgpu      -> --require-tolerance-parity --atol 1e-3
  * doppler_node_webgpu         -> --require-tolerance-parity --atol 1e-3
  * doppler_exported_fixture    -> depends on how fixture was produced

Usage:

  python3 bench/tools/doppler_reference_export_stub.py \\
    --manifest runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json \\
    --graph   bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json \\
    --size 1024 \\
    --num-layers 35 \\
    --initial-rows-seed 1000 \\
    --per-layer-base 2000 \\
    --runtime numpy_reference_stub \\
    --out-dir bench/out/doppler-reference/gemma-4-e2b-layer-block

Then bind into the parity receipt and gate:

  python3 bench/tools/emit_csl_reference_parity_sample.py \\
    --external-reference-output bench/out/doppler-reference/gemma-4-e2b-layer-block/activation_out.f32 \\
    --external-reference-producer doppler_browser_webgpu \\
    --atol 1e-3

  python3 bench/gates/csl_reference_parity_gate.py \\
    --receipt examples/doe-csl-reference-parity.gemma-4-e2b-layer-block.sample.json \\
    --require-tolerance-parity

## Input contract (seeded RNG, matches CSL runner's load_layer_data)

For each layer l_idx in [0, num_layers):

    seed_l          = per_layer_base + l_idx
    rows_layer_0    = default_rng(initial_rows_seed).standard_normal(size, f32)
    rows_layer_N>0  = output of layer N-1
    proj_layer_l    = default_rng(seed_l).standard_normal(size, f32)
    wts_layer_l     = default_rng(seed_l).standard_normal(size, f32)

Note: proj_l and wts_l use SEPARATE default_rng(seed_l) instances
(fresh rng per call), so proj_l == wts_l bit-exactly. This mirrors
the runner's load_layer_data() semantics and is the symmetry the
synthetic trace also uses.

## Output contract

  activation_out.f32        -- `size` f32 values (4 * size bytes),
                               little-endian, from the FINAL layer's
                               compute (layer num_layers - 1).
  export_receipt.json       -- schemaVersion 1, artifactKind
                               'doppler_reference_export', all
                               sha256 hex strings, runtime tag,
                               per-layer output shas for debugging.

The gate at csl_reference_parity_gate.py reads only
activation_out.f32 in tolerance-parity mode. The export_receipt
is for humans debugging + the receipt builder's future binding of
comparison.referenceRun.output.runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "runners" / "csl-runners"))
from _e2b_layer_block_compute import compute_layer_block  # noqa: E402


VALID_RUNTIMES = (
    "numpy_reference_stub",
    "doppler_browser_webgpu",
    "doppler_node_webgpu",
    "doppler_exported_fixture",
)


def sha256_f32(arr: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(arr.astype(np.float32).tobytes(order="C"))
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--graph", required=True)
    p.add_argument("--size", type=int, default=1024)
    p.add_argument("--num-layers", type=int, default=35)
    p.add_argument("--initial-rows-seed", type=int, default=1000)
    p.add_argument("--per-layer-base", type=int, default=2000)
    p.add_argument(
        "--runtime",
        choices=VALID_RUNTIMES,
        default="numpy_reference_stub",
        help="Tag recorded in export_receipt.runtime.",
    )
    p.add_argument(
        "--out-dir",
        required=True,
        help="Directory to write activation_out.f32 + export_receipt.json.",
    )
    return p.parse_args()


def compute_numpy_reference(
    size: int,
    num_layers: int,
    initial_rows_seed: int,
    per_layer_base: int,
) -> tuple[np.ndarray, list[str]]:
    """Chain compute_layer_block num_layers times with seeded inputs.

    Returns (final_output_f32, per_layer_output_sha256_list).
    """
    rows = np.random.default_rng(
        seed=initial_rows_seed
    ).standard_normal(size=size, dtype=np.float32)
    per_layer_shas: list[str] = []
    for l_idx in range(num_layers):
        seed_l = per_layer_base + l_idx
        proj_l = np.random.default_rng(
            seed=seed_l
        ).standard_normal(size=size, dtype=np.float32)
        wts_l = np.random.default_rng(
            seed=seed_l
        ).standard_normal(size=size, dtype=np.float32)
        rows = compute_layer_block(rows, proj_l, wts_l, size)
        per_layer_shas.append(sha256_f32(rows))
    return rows, per_layer_shas


def main() -> int:
    args = parse_args()
    manifest_path = resolve(args.manifest)
    graph_path = resolve(args.graph)
    for label, p in (("manifest", manifest_path), ("graph", graph_path)):
        if not p.is_file():
            print(f"ERROR: --{label} missing: {p}", file=sys.stderr)
            return 2
    out_dir = resolve(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng_init = np.random.default_rng(seed=args.initial_rows_seed)
    initial_rows = rng_init.standard_normal(
        size=args.size, dtype=np.float32
    )
    input_tensor_sha = sha256_f32(initial_rows)

    # For synthetic seeded inputs with proj==wts per layer, weight
    # hash equals the aggregate over all per-layer wts arrays.
    weight_sha = hashlib.sha256()
    for l_idx in range(args.num_layers):
        seed_l = args.per_layer_base + l_idx
        wts_l = np.random.default_rng(
            seed=seed_l
        ).standard_normal(size=args.size, dtype=np.float32)
        weight_sha.update(wts_l.astype(np.float32).tobytes(order="C"))
    weight_sha_hex = weight_sha.hexdigest()

    # Compute the reference via the numpy path. When a Doppler team
    # replaces this function with a real WebGPU runtime call, they
    # keep the (size, num_layers, seeds) -> (output, per_layer_shas)
    # signature and update --runtime to doppler_browser_webgpu or
    # doppler_node_webgpu.
    if args.runtime == "numpy_reference_stub":
        activation_out, per_layer_shas = compute_numpy_reference(
            args.size, args.num_layers,
            args.initial_rows_seed, args.per_layer_base,
        )
    else:
        print(
            f"ERROR: runtime={args.runtime!r} selected but this stub "
            "only implements numpy_reference_stub. A real Doppler "
            "integration must replace compute_numpy_reference() with "
            "the chosen runtime's execution of the same layer-block "
            "chain on the same seeded inputs."
        )
        return 2

    out_path = out_dir / "activation_out.f32"
    activation_out.astype(np.float32).tofile(out_path)
    output_sha = sha256_file(out_path)

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doppler_reference_export",
        "manifestPath": args.manifest,
        "manifestSha256": sha256_file(manifest_path),
        "graphPath": args.graph,
        "graphSha256": sha256_file(graph_path),
        "inputTensorSha256": input_tensor_sha,
        "weightSha256": weight_sha_hex,
        "size": args.size,
        "numLayers": args.num_layers,
        "initialRowsSeed": args.initial_rows_seed,
        "perLayerBase": args.per_layer_base,
        "runtime": args.runtime,
        "outputPath": str(out_path.relative_to(REPO_ROOT))
        if out_path.is_relative_to(REPO_ROOT)
        else str(out_path),
        "outputSha256": output_sha,
        "outputShape": [args.size],
        "outputDtype": "float32",
        "perLayerOutputSha256": per_layer_shas,
        "runtimeContractNote": (
            "A real Doppler runtime replaces "
            "compute_numpy_reference() with a WebGPU execution of the "
            "same layer-block chain on the same seeded inputs, "
            "preserving (size, num_layers, seeds) -> (output, "
            "per_layer_shas). --runtime tag records which variant "
            "produced the output. Bit-exact to scalar f32 numpy is "
            "only expected for numpy_reference_stub; WebGPU runtimes "
            "drift under driver FMA / vectorized reductions / "
            "platform sqrt and must be gated via tolerance parity "
            "(csl_reference_parity_gate.py --require-tolerance-"
            "parity --atol <N>)."
        ),
    }

    receipt_path = out_dir / "export_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )

    print(
        "Doppler reference export complete:"
        + f"\n  out-dir: {out_dir}"
        + f"\n  activation_out.f32: {output_sha[:16]}... "
        + f"({args.size} floats, {args.size * 4} bytes)"
        + f"\n  runtime: {args.runtime}"
        + f"\n  manifestSha256: {receipt['manifestSha256'][:16]}..."
        + f"\n  graphSha256: {receipt['graphSha256'][:16]}..."
        + f"\n  inputTensorSha256: {input_tensor_sha[:16]}..."
        + f"\n  weightSha256: {weight_sha_hex[:16]}..."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
