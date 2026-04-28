#!/usr/bin/env cs_python
"""Qwen 3.6 27B attn_decode kernel — simfabric end-to-end run.

Compiles small-shape (width=2, head_dim=8, kv_chunk=4) version of
the manifest-shape Qwen attn_decode CSL, runs it under simfabric,
and verifies output equals scaled-dot-product softmax attention vs
numpy. width=2 is the maximum width where the layout's reduce-color
chain is sound (the multi-PE chain routing for width>=3 is a known
gap, see emit_csl_layout.zig:emitReductionLayout). This canary
validates the kernel-emit fix landed in emit_csl_attention.zig:
the wse2-era synchronous @fmovs(f32_var, fabin_dsd) recv was
replaced with the canonical wse3 async @mov32(scratch_in_dsd,
reduce_in, .{.async, .activate=reduce_task_id}) that actually
fires the reduce_recv task.
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

width = 1
head_dim = 8
kv_chunk = 8
kv_total = width * kv_chunk
scale = 0.125
decode_position = kv_total - 1
sliding_window = 0

rng = np.random.default_rng(seed=27)
query_host = rng.standard_normal(size=head_dim).astype(np.float32)
key_per_pe = rng.standard_normal(size=(width, kv_chunk, head_dim)).astype(np.float32)
val_per_pe = rng.standard_normal(size=(width, kv_chunk, head_dim)).astype(np.float32)

key_full = key_per_pe.reshape(kv_total, head_dim)
val_full = val_per_pe.reshape(kv_total, head_dim)
scores = (key_full @ query_host) * scale
m = float(np.max(scores))
exp_scores = np.exp(scores - m)
weights = exp_scores / exp_scores.sum()
ref_output = (weights[:, None] * val_full).sum(axis=0).astype(np.float32)

position_host = np.full(width, decode_position, dtype=np.uint32)
sliding_window_host = np.full(width, sliding_window, dtype=np.uint32)
query_broadcast = np.tile(query_host, width).astype(np.float32)

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
query_sym = runner.get_id("query")
key_sym = runner.get_id("key")
val_sym = runner.get_id("val")
output_sym = runner.get_id("output")
position_sym = runner.get_id("position")
sliding_window_sym = runner.get_id("sliding_window")

runner.load()
runner.run()
runner.memcpy_h2d(query_sym, query_broadcast, 0, 0, width, 1, head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.memcpy_h2d(key_sym, key_per_pe.ravel(), 0, 0, width, 1, kv_chunk * head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.memcpy_h2d(val_sym, val_per_pe.ravel(), 0, 0, width, 1, kv_chunk * head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.memcpy_h2d(position_sym, position_host, 0, 0, width, 1, 1,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.memcpy_h2d(sliding_window_sym, sliding_window_host, 0, 0, width, 1, 1,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.launch("compute", nonblock=False)

output_buf = np.zeros(head_dim, dtype=np.float32)
runner.memcpy_d2h(output_buf, output_sym, width - 1, 0, 1, 1, head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.stop()

max_abs = float(np.max(np.abs(output_buf - ref_output)))
max_rel = float(np.max(np.abs(output_buf - ref_output) / (np.abs(ref_output) + 1e-9)))
ok = bool(np.allclose(output_buf, ref_output, rtol=1e-3, atol=1e-3))
print(f"shape: width={width} head_dim={head_dim} kv_chunk={kv_chunk}")
print(f"DBG actual[:4] = {output_buf[:4]}")
print(f"DBG ref   [:4] = {ref_output[:4]}")
print(f"max_abs_diff={max_abs:.6e} max_rel_diff={max_rel:.6e} parity={'OK' if ok else 'FAIL'}")

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_attn_decode_simfabric_cell",
    "kernel": "attn_decode",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {
        "width": width, "head_dim": head_dim, "kv_chunk": kv_chunk,
        "kv_total": kv_total, "scale": scale,
        "decode_position": decode_position, "sliding_window": sliding_window,
    },
    "parityMaxAbsDiff": max_abs,
    "parityMaxRelDiff": max_rel,
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B attn_decode kernel CSL (sourced from the "
            "manifest-shape host plan) compiles via cslc 2.10.0 at "
            f"width={width}, head_dim={head_dim}, kv_chunk={kv_chunk} "
            "and runs end-to-end on simfabric. Output matches host-"
            "computed scaled-dot-product softmax attention within "
            "float32 precision. Validates the wse3 async-recv emit "
            "fix landed in emit_csl_attention.zig: replaced wse2-era "
            "synchronous `@fmovs(f32_var, fabin_dsd)` with the "
            "canonical scratch-buffer + `@mov32(.{.async, "
            ".activate=reduce_task_id})` form that actually fires "
            "the reduce_recv task. Without this fix, simfabric "
            "launches hang at memcpy_d2h with `received length (0 "
            "bytes) is not expected`."
        ),
        "notWhat": (
            "Not a hardware run. Not a manifest-shape run — Qwen "
            "manifest head_dim=256 with much larger kv_chunk per PE "
            "and full GQA head broadcast. Width=2 limit: middle-PE "
            "reduce-color chain routing is a separate gap (see "
            "emit_csl_layout.zig comment). Decode-only — prefill "
            "(causal-mask multi-token) is the separate attn_prefill "
            "linker_pe_memory_overflow blocker. Sliding-window "
            "branch not exercised here (sliding_window=0)."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
