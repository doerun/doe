#!/usr/bin/env cs_python
"""Qwen 3.6 27B attn_decode kernel — simfabric typed-blocker receipt.

The kernel as emitted by the manifest-shape host plan COMPILES via
cslc 2.10.0 at small canary shape (width=4, head_dim=8, kv_chunk=4)
but STALLS on simfabric: `task reduce_recv` is bound to
`reduce_task_id` but never activated. The `@fmovs(&incoming, reduce_in)`
fabric-input read is missing the `.activate = reduce_task_id`
annotation that the sample kernel's `@mov32` uses correctly. Without
the activation, the running-max reduction across the PE row never
advances; the last PE never enters the normalize task; memcpy_d2h
hangs (simfabric reports `received length (0 bytes) is not expected,
could be a kernel stall`).

This is a real WGSL→CSL emit gap that needs to be closed before
end-to-end attention parity can be validated under simfabric. The
gap is recorded here as a typed-blocker simfabric receipt so the
summary cell receipt can carry it as `verdict=kernel_emit_stall`
without aborting the rest of the lane.

When the gap is closed, this driver should:
  - run the kernel under SdkRuntime
  - read output from PE (width-1, 0)
  - compare against numpy scaled-dot-product softmax attention
"""

import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--name", default="compiled")
parser.add_argument("--cmaddr", default=None)
parser.add_argument("--out-receipt", default="receipt.json")
args = parser.parse_args()

width = 4
head_dim = 8
kv_chunk = 4
kv_total = width * kv_chunk
scale = 0.125
decode_position = kv_total - 1
sliding_window = 0

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_attn_decode_simfabric_cell",
    "kernel": "attn_decode",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "kernel_emit_stall",
    "shape": {
        "width": width, "head_dim": head_dim, "kv_chunk": kv_chunk,
        "kv_total": kv_total, "scale": scale,
        "decode_position": decode_position,
        "sliding_window": sliding_window,
    },
    "parityMaxAbsDiff": None,
    "parityMaxRelDiff": None,
    "stallSignature": (
        "received length (0 bytes) is not expected (32 bytes), "
        "could be a kernel stall"
    ),
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B attn_decode kernel CSL (sourced from the "
            "manifest-shape host plan) compiles via cslc 2.10.0 at "
            f"width={width}, head_dim={head_dim}, kv_chunk={kv_chunk} "
            f"(kv_total={kv_total}). When the reduce-chain task-"
            "activation gap (see notWhat) is closed, this cell will "
            "validate the local-max + fabric-reduce + normalize "
            "sequence end-to-end vs host softmax attention."
        ),
        "notWhat": (
            "Not a hardware run. KERNEL-EMIT GAP — STALLS ON "
            "SIMFABRIC: the attn_decode kernel as emitted today "
            "binds `task reduce_recv` to `reduce_task_id` but never "
            "activates it. `@fmovs(&incoming, reduce_in)` is missing "
            "the `.activate = reduce_task_id` annotation that the "
            "sample kernel's `@mov32(scratch_in_dsd, reduce_in, "
            ".{ .async = true, .activate = reduce_task_id })` uses "
            "correctly. Without the activation, the running-max "
            "reduction across the PE row never advances, the last "
            "PE never enters the normalize task, and memcpy_d2h "
            "hangs (simfabric reports the stall signature recorded "
            "in the receipt). This is a typed WGSL→CSL emit gap "
            "parallel to the sample kernel's missing index-"
            "reduction. Decode-loop correctness depends on it being "
            "closed. Manifest-shape head_dim=256 / GQA head "
            "broadcast / prefill (causal-mask, separate attn_prefill "
            "linker_pe_memory_overflow blocker) all out of scope."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt} verdict={receipt['verdict']}")
sys.exit(0)
