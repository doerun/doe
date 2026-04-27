#!/usr/bin/env cs_python
"""Qwen 3.6 27B silu kernel — simfabric end-to-end run.

Compiles small-shape (width=4, chunk_size=128) version of the
manifest-shape Qwen silu CSL and runs it under simfabric.

IMPORTANT — emit/spec mismatch documented in claim.notWhat:
The kernel under compile/silu/pe_program.csl currently emits as a
pure passthrough (`output[idx] = input[idx] * 1.0`) — the WGSL
`silu` op falls through the doe_wgsl element_wise pattern as a
single-input identity stand-in rather than `x * sigmoid(x)`. This
is one of the named blockers listed in the smoke config's
`scopeRestrictions.swigluFfnFusedGate`: surfacing real SiLU (and
the gate*up multiplication) requires routing the `silu_gated` op
through the doe_wgsl classifier and exec-v1 opToSpec map. The
TSIR `silu_gated` body op landed but the front-end wiring did
not on this branch.

This run therefore validates the kernel-dispatch shape (memcpy,
PE-grid layout, host-driver round-trip), NOT the SiLU arithmetic.
The host reference is the same passthrough the kernel currently
emits — parity here means "the dispatch executes faithfully", not
"SiLU is correct". When the front-end wiring lands, the host
reference here switches to `x / (1 + exp(-x))`.
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
u_host = np.zeros(1, dtype=np.uint32)
ref_output = input_host * 1.0  # matches the current passthrough emit

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
u_sym = runner.get_id("u")
input_sym = runner.get_id("input")
output_sym = runner.get_id("output")

runner.load()
runner.run()
runner.memcpy_h2d(
    u_sym, np.tile(u_host, width),
    0, 0, width, 1, 1,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.memcpy_h2d(
    input_sym, input_host.ravel(),
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
max_abs = float(np.max(np.abs(actual - ref_output)))
max_rel = float(np.max(np.abs(actual - ref_output) / (np.abs(ref_output) + 1e-9)))
ok = bool(np.allclose(actual, ref_output, rtol=1e-3, atol=1e-3))
print(f"shape: width={width} chunk_size={chunk_size}")
print(f"max_abs_diff={max_abs:.6e} max_rel_diff={max_rel:.6e} parity={'OK' if ok else 'FAIL'}")

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_silu_simfabric_cell",
    "kernel": "silu",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {"width": width, "chunk_size": chunk_size},
    "parityMaxAbsDiff": max_abs,
    "parityMaxRelDiff": max_rel,
    "kernelReferenceMode": "passthrough_matches_current_emit",
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B silu kernel CSL (sourced from the manifest-"
            "shape host plan) compiles via cslc 2.10.0 at "
            f"width={width}, chunk_size={chunk_size} and runs end-to-"
            "end on simfabric. Output matches the host reference "
            "(passthrough) within float32 precision."
        ),
        "notWhat": (
            "Not actual SiLU arithmetic. The kernel under compile/silu/"
            "pe_program.csl currently emits as a passthrough "
            "(output[idx] = input[idx] * 1.0); WGSL `silu` falls "
            "through the doe_wgsl element_wise pattern as a single-"
            "input identity stand-in. The TSIR silu_gated body op "
            "landed but the front-end wiring (doe_wgsl classifier + "
            "exec-v1 opToSpec) did not on this branch. Tracked as "
            "scopeRestrictions.swigluFfnFusedGate in the smoke config. "
            "Layout was hand-patched to forward chunk_size — same "
            "rationale as rmsnorm/residual cells."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
