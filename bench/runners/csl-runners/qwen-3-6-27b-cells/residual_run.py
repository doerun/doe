#!/usr/bin/env cs_python
"""Qwen 3.6 27B residual kernel — simfabric end-to-end run.

Compiles small-shape (width=4, chunk_size=128) version of the
manifest-shape Qwen residual CSL, runs it under simfabric, and
verifies numerical parity vs the canonical residual-add formula:

    output[i] = input[i] + residual[i]

Parity tolerance: 1e-3 absolute / 1e-3 relative (matches the SUMMA
wedge cell's tolerance — float32 simfabric vs float32 numpy).
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
height = 1
chunk_size = 128

rng = np.random.default_rng(seed=27)
input_host = rng.standard_normal(size=(width, chunk_size)).astype(np.float32)
residual_host = rng.standard_normal(size=(width, chunk_size)).astype(np.float32)
ref_output = (input_host + residual_host).astype(np.float32)

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
input_sym = runner.get_id("input")
residual_sym = runner.get_id("residual")
output_sym = runner.get_id("output")

runner.load()
runner.run()

runner.memcpy_h2d(
    input_sym, input_host.ravel(),
    0, 0, width, 1, chunk_size,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.memcpy_h2d(
    residual_sym, residual_host.ravel(),
    0, 0, width, 1, chunk_size,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.launch("compute", nonblock=False)

actual_flat = np.zeros(width * chunk_size, dtype=np.float32)
runner.memcpy_d2h(
    actual_flat, output_sym,
    0, 0, width, 1, chunk_size,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.stop()

actual = actual_flat.reshape(width, chunk_size)
print(f"DBG actual[0, :5] = {actual[0, :5]}")
print(f"DBG ref[0, :5]    = {ref_output[0, :5]}")
max_abs = float(np.max(np.abs(actual - ref_output)))
max_rel = float(
    np.max(np.abs(actual - ref_output) / (np.abs(ref_output) + 1e-9))
)
ok = bool(np.allclose(actual, ref_output, rtol=1e-3, atol=1e-3))

print(f"shape: width={width} chunk_size={chunk_size}")
print(f"max_abs_diff={max_abs:.6e} max_rel_diff={max_rel:.6e} parity={'OK' if ok else 'FAIL'}")

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_residual_simfabric_cell",
    "kernel": "residual",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {"width": width, "height": height, "chunk_size": chunk_size},
    "parityMaxAbsDiff": max_abs,
    "parityMaxRelDiff": max_rel,
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B residual kernel CSL (sourced from the "
            "manifest-shape host plan) compiles via cslc 2.10.0 at "
            f"width={width}, chunk_size={chunk_size} and runs end-to-"
            "end on simfabric. Output matches host-computed input + "
            "residual within float32 precision."
        ),
        "notWhat": (
            "Not a hardware run. Not a manifest-shape run (manifest "
            "is width=251, chunk_size=5120; small canary shape "
            "exercises the kernel mechanism, not production scale). "
            "Not a multi-kernel chain — single residual kernel only. "
            "Layout.csl was hand-patched to forward chunk_size to "
            "pe_program — same per-PE-residency rationale documented "
            "in the rmsnorm cell receipt: at manifest hidden=5120 the "
            "[chunk_size]f32 × 3 buffers (60 KB) overflow the WSE-3 "
            "per-PE 38 KB working budget, so emit_csl_layout.zig "
            "deliberately omits this forwarding."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
