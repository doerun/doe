#!/usr/bin/env cs_python
"""Gemma 4 31B AF16 lm_head_prefill kernel — simfabric canary.

Compiles a tiny manifest-shaped dense GEMV kernel (`layout.csl` +
`pe_program.csl`) for Gemma AF16, runs it under simfabric, and verifies
f16 arithmetic + collectives_2d reduction parity on f32 outputs.

This is a smoke-cell driver, not a manifest-scale run. The kernel still
uses the Gemma AF16 shape convention: f16 activation/weights, f16->f32
compute, and row-wise collectives_2d reduction across `width`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)


parser = argparse.ArgumentParser()
parser.add_argument("--name", default="compiled")
parser.add_argument("--cmaddr", default=None)
parser.add_argument("--out-receipt", default="receipt.json")
args = parser.parse_args()

width = 4
height = 1
out_dim = 4
out_dim_per_pe = 4
in_dim_per_pe = 32

rng = np.random.default_rng(seed=27)
activation_per_pe = rng.standard_normal(size=(width, in_dim_per_pe)).astype(np.float16)
weight_per_pe = rng.standard_normal(size=(width, out_dim_per_pe, in_dim_per_pe)).astype(np.float16)

activation_ref_f32 = activation_per_pe.astype(np.float32)
weight_ref_f32 = weight_per_pe.astype(np.float32)

ref_output = np.zeros(out_dim_per_pe, dtype=np.float32)
for pe in range(width):
    act = activation_ref_f32[pe]
    w = weight_ref_f32[pe]
    ref_output += w @ act

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
activation_sym = runner.get_id("activation")
weight_sym = runner.get_id("weight")
output_sym = runner.get_id("output")

runner.load()
runner.run()

activation_u16 = activation_per_pe.view(np.uint16).ravel()
if activation_u16.size % 2 != 0:
    raise ValueError("activation transfer expects an even element count for f32-worded memcpy")
activation_u32 = activation_u16.view(np.uint32)

weight_u16 = weight_per_pe.reshape(width, out_dim_per_pe * in_dim_per_pe).astype(np.float16).view(np.uint16).ravel()
if weight_u16.size % 2 != 0:
    raise ValueError("weight transfer expects an even element count for f32-worded memcpy")
weight_u32 = weight_u16.view(np.uint32)

tile_count = width * height
if tile_count <= 0:
    raise ValueError("width * height must be positive")
activation_words_per_pe = activation_u32.size // tile_count
weight_words_per_pe = weight_u32.size // tile_count
if activation_u32.size != activation_words_per_pe * tile_count:
    raise ValueError("activation transfer size is not divisible by width * height")
if weight_u32.size != weight_words_per_pe * tile_count:
    raise ValueError("weight transfer size is not divisible by width * height")

runner.memcpy_h2d(
    activation_sym,
    activation_u32,
    0,
    0,
    width,
    height,
    activation_words_per_pe,
    streaming=False,
    order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT,
    nonblock=False,
)
runner.memcpy_h2d(
    weight_sym,
    weight_u32,
    0,
    0,
    width,
    height,
    weight_words_per_pe,
    streaming=False,
    order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT,
    nonblock=False,
)
runner.launch("compute", nonblock=False)

output_buf = np.zeros(out_dim_per_pe, dtype=np.float32)
runner.memcpy_d2h(
    output_buf,
    output_sym,
    width - 1,
    0,
    1,
    1,
    out_dim_per_pe,
    streaming=False,
    order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT,
    nonblock=False,
)
runner.stop()

max_abs = float(np.max(np.abs(output_buf - ref_output)))
max_rel = float(np.max(np.abs(output_buf - ref_output) / (np.abs(ref_output) + 1e-9)))
ok = bool(np.allclose(output_buf, ref_output, rtol=1e-3, atol=1e-3))

print(
    f"shape: width={width} height={height} out_dim={out_dim} "
    f"out_dim_per_pe={out_dim_per_pe} in_dim_per_pe={in_dim_per_pe}"
)
print(f"DBG actual = {output_buf}")
print(f"DBG ref    = {ref_output}")
print(
    f"max_abs_diff={max_abs:.6e} "
    f"max_rel_diff={max_rel:.6e} parity={'OK' if ok else 'FAIL'}"
)

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_gemma4_31b_af16_lm_head_prefill_simfabric_cell",
    "kernel": "lm_head_prefill",
    "modelId": "gemma-4-31b-it-text-q4k-ehf16-af16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {
        "width": width,
        "height": height,
        "out_dim": out_dim,
        "out_dim_per_pe": out_dim_per_pe,
        "in_dim_per_pe": in_dim_per_pe,
        "dtype": "f16",
    },
    "parityMaxAbsDiff": max_abs,
    "parityMaxRelDiff": max_rel,
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Gemma 4 31B AF16 lm_head_prefill dense-GEMV "
            f"canary compiles via cslc 2.10.0 at width={width}, "
            f"height={height}, in_dim_per_pe={in_dim_per_pe}, "
            f"out_dim_per_pe={out_dim_per_pe}. "
            "collectives_2d reduce path and f16 de-staging of activation/"
            "weight are verified on simfabric."
        ),
        "notWhat": (
            "Not a manifest-scale run (Gemma LM head uses height=512 and "
            "vocab width beyond this canary). This is a dispatch-shape "
            "canary only and does not exercise full-row or full-vocab "
            "coverage."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
