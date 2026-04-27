#!/usr/bin/env cs_python
"""Qwen 3.6 27B kv_write kernel — simfabric end-to-end run.

Compiles small-shape (width=4 heads, height=1 position-shard,
head_dim=8, slots_per_pe=8 = max_seq_len) version of the manifest-
shape Qwen kv_write CSL, runs it under simfabric, and verifies the
KV cache row at the requested position equals the input projection
(identity copy at slot).

Manifest scale: GQA 24:4 → kv_heads=4 head-axis × 213 PE row-shard
on the position axis (slots_per_pe ≈ 20). This canary uses height=1
to match the existing kv_write_sim_runner pattern; the position-
ownership-guard branch (`owning_pe == pe_id` on the height axis)
is exercised by the rest of the lane via larger configurations.
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

width = 4         # head axis (kv_heads)
height = 1        # position-shard axis
head_dim = 8
slots_per_pe = 8
max_seq_len = slots_per_pe * height
target_position = 5

rng = np.random.default_rng(seed=27)
key_proj_host = rng.standard_normal(size=(width, head_dim)).astype(np.float32)
val_proj_host = rng.standard_normal(size=(width, head_dim)).astype(np.float32)
position_host = np.full(width, target_position, dtype=np.uint32)

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
key_proj_sym = runner.get_id("key_proj")
val_proj_sym = runner.get_id("val_proj")
key_cache_sym = runner.get_id("key_cache")
val_cache_sym = runner.get_id("val_cache")
position_sym = runner.get_id("position")

runner.load()
runner.run()

runner.memcpy_h2d(key_proj_sym, key_proj_host.ravel(), 0, 0, width, 1, head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.memcpy_h2d(val_proj_sym, val_proj_host.ravel(), 0, 0, width, 1, head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.memcpy_h2d(position_sym, position_host, 0, 0, width, 1, 1,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.launch("compute", nonblock=False)

key_flat = np.zeros(width * max_seq_len * head_dim, dtype=np.float32)
val_flat = np.zeros(width * max_seq_len * head_dim, dtype=np.float32)
runner.memcpy_d2h(key_flat, key_cache_sym, 0, 0, width, 1, max_seq_len * head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.memcpy_d2h(val_flat, val_cache_sym, 0, 0, width, 1, max_seq_len * head_dim,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.stop()

key_cache = key_flat.reshape(width, max_seq_len, head_dim)
val_cache = val_flat.reshape(width, max_seq_len, head_dim)

max_write_err = 0.0
max_stray_abs = 0.0
for pe in range(width):
    write_err = float(np.max(np.abs(key_cache[pe, target_position] - key_proj_host[pe])))
    write_err = max(write_err, float(np.max(np.abs(val_cache[pe, target_position] - val_proj_host[pe]))))
    max_write_err = max(max_write_err, write_err)
    stray = np.concatenate([
        key_cache[pe, :target_position].ravel(),
        key_cache[pe, target_position + 1:].ravel(),
        val_cache[pe, :target_position].ravel(),
        val_cache[pe, target_position + 1:].ravel(),
    ])
    stray_abs = float(np.max(np.abs(stray))) if stray.size else 0.0
    max_stray_abs = max(max_stray_abs, stray_abs)

ok = (max_write_err == 0.0) and (max_stray_abs == 0.0)
print(f"shape: width={width} height={height} head_dim={head_dim} "
      f"slots_per_pe={slots_per_pe} max_seq_len={max_seq_len}")
print(f"target_position={target_position} max_write_err={max_write_err:.6e} "
      f"max_stray_abs={max_stray_abs:.6e} parity={'OK' if ok else 'FAIL'}")

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_kv_write_simfabric_cell",
    "kernel": "kv_write",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {
        "width": width, "height": height, "head_dim": head_dim,
        "slots_per_pe": slots_per_pe, "max_seq_len": max_seq_len,
        "target_position": target_position,
    },
    "parityMaxWriteError": max_write_err,
    "parityMaxStrayAbs": max_stray_abs,
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B kv_write kernel CSL (sourced from the "
            "manifest-shape host plan) compiles via cslc 2.10.0 at "
            f"width={width} (kv_heads), height={height} (position-"
            f"shard), head_dim={head_dim}, slots_per_pe={slots_per_pe} "
            "and runs end-to-end on simfabric. The KV cache row at "
            f"position={target_position} matches the input projection "
            "exactly across all heads; all other slots remain zero "
            "(no stray writes)."
        ),
        "notWhat": (
            "Not a hardware run. Not a manifest-shape run — manifest "
            "is GQA 24:4 with kv_heads=4 × 213 PE row-shard "
            "(head_dim=256, slots_per_pe ≈ 20). Single-shard canary "
            "(height=1) — multi-shard ownership-guard "
            "(`owning_pe == pe_id` on the position axis) is "
            "exercised by larger lane configurations, not by this "
            "small canary."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
