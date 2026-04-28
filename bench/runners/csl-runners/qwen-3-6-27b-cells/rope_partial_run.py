#!/usr/bin/env cs_python
"""Qwen 3.6 27B rope_partial kernel — simfabric end-to-end run.

Compiles small-shape (width=4, head_dim=8, num_pairs=2) version of
the manifest-shape Qwen rope_partial CSL, runs it under simfabric,
and verifies numerical parity vs the canonical RoPE rotation:

    out[2k]   = x[2k]   * cos[k] - x[2k+1] * sin[k]
    out[2k+1] = x[2k]   * sin[k] + x[2k+1] * cos[k]

This kernel exercises the partialRotaryFactor wiring delta —
manifest-shape Qwen 3.6 27B has head_dim=256, partialRotaryFactor=0.25,
num_pairs=32. The small canary uses head_dim=8, num_pairs=2 (i.e.
partial_rotary_factor=0.5) so 2 pairs are rotated; the remaining 4
dims stay untouched (in the kernel they are simply not rotated since
the loop only iterates num_pairs times).

Note that rope_partial's layout DOES forward both head_dim and
num_pairs to pe_program (unlike rmsnorm which had to be hand-patched
for hidden_size); this run validates the manifest-shape forwarding
chain end-to-end.

Parity tolerance: 1e-3 absolute / 1e-3 relative (matches SUMMA cell).
"""

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
head_dim = 8
num_pairs = 2

rng = np.random.default_rng(seed=27)
input_host = rng.standard_normal(size=(width, head_dim)).astype(np.float32)
# RoPE cos/sin tables: each PE gets the same per-position table here
# (the kernel doesn't broadcast — caller streams in the per-PE table).
freqs = rng.uniform(0.0, 2.0 * np.pi, size=(width, num_pairs)).astype(np.float32)
cos_host = np.cos(freqs).astype(np.float32)
sin_host = np.sin(freqs).astype(np.float32)

# Host reference: interleaved-pair RoPE on the first 2*num_pairs dims.
ref_output = input_host.copy()
for w in range(width):
    for p in range(num_pairs):
        d0, d1 = 2 * p, 2 * p + 1
        x0 = input_host[w, d0]
        x1 = input_host[w, d1]
        c = cos_host[w, p]
        s = sin_host[w, p]
        ref_output[w, d0] = x0 * c - x1 * s
        ref_output[w, d1] = x0 * s + x1 * c

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
input_sym = runner.get_id("input")
cos_sym = runner.get_id("cos_table")
sin_sym = runner.get_id("sin_table")

runner.load()
runner.run()

runner.memcpy_h2d(
    input_sym, input_host.ravel(),
    0, 0, width, 1, head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.memcpy_h2d(
    cos_sym, cos_host.ravel(),
    0, 0, width, 1, num_pairs,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.memcpy_h2d(
    sin_sym, sin_host.ravel(),
    0, 0, width, 1, num_pairs,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.launch("compute", nonblock=False)

actual_flat = np.zeros(width * head_dim, dtype=np.float32)
runner.memcpy_d2h(
    actual_flat, input_sym,
    0, 0, width, 1, head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.stop()

actual = actual_flat.reshape(width, head_dim)
print(f"DBG actual[0] = {actual[0]}")
print(f"DBG ref[0]    = {ref_output[0]}")
max_abs = float(np.max(np.abs(actual - ref_output)))
max_rel = float(
    np.max(np.abs(actual - ref_output) / (np.abs(ref_output) + 1e-9))
)
ok = bool(np.allclose(actual, ref_output, rtol=1e-3, atol=1e-3))

print(f"shape: width={width} head_dim={head_dim} num_pairs={num_pairs}")
print(f"max_abs_diff={max_abs:.6e} max_rel_diff={max_rel:.6e} parity={'OK' if ok else 'FAIL'}")

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_rope_partial_simfabric_cell",
    "kernel": "rope_partial",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {
        "width": width,
        "head_dim": head_dim,
        "num_pairs": num_pairs,
        "partial_rotary_factor_effective": (2.0 * num_pairs) / head_dim,
    },
    "parityMaxAbsDiff": max_abs,
    "parityMaxRelDiff": max_rel,
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B rope_partial kernel CSL (sourced from the "
            "manifest-shape host plan) compiles via cslc 2.10.0 at "
            f"width={width}, head_dim={head_dim}, num_pairs={num_pairs} "
            "and runs end-to-end on simfabric. Output matches host-"
            "computed interleaved-pair RoPE rotation within float32 "
            "precision. Validates the partialRotaryFactor wiring delta "
            "from the host-plan tool — manifest carries head_dim=256 / "
            "partialRotaryFactor=0.25 / num_pairs=32; this small canary "
            "uses head_dim=8, num_pairs=2 (effective factor 0.5) and "
            "exercises the same forwarding chain (layout.csl → "
            "@set_tile_code → pe_program.csl) the manifest-shape "
            "compile relies on."
        ),
        "notWhat": (
            "Not a hardware run. Not a manifest-shape run (manifest is "
            "head_dim=256, num_pairs=32; small canary exercises the "
            "kernel mechanism, not production scale). Not a multi-"
            "kernel chain — single rope_partial kernel only. Cos/sin "
            "tables are random per-PE, not produced by a real position-"
            "indexing scheme — kernel arithmetic is the claim, not "
            "rope-table generation."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
