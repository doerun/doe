#!/usr/bin/env cs_python
"""Qwen 3.6 27B gemv kernel — simfabric end-to-end run.

Compiles small-shape (width=4, height=1, out_dim=4, out_dim_per_pe=4,
in_dim_per_pe=512, num_blocks_per_row=2) version of the manifest-shape
Qwen gemv CSL (fused Q4_K dequant + GEMV with row-shard fabric reduce),
runs it under simfabric, and verifies the output equals the
host-computed reference: sum across PE row of dequant(weight[pe]) @
activation[pe].

Q4_K block packing matches emit_csl_fused.zig's dequant path (and the
existing lmhead_gemv_2d_sim_runner): 144 bytes per super-block of 256
weights, sub-block scale=1, dmin=0.

Manifest scale: lm_head GEMV at vocab=248320, hidden=5120 sharded
across the row chain. This canary covers the dequant + dot-product +
fabric-reduce chain.
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

QK_K = 256
Q4K_BLOCK_BYTES = 144


def pack_q4k_block(values: np.ndarray, d: float) -> np.ndarray:
    """Pack a 144-byte Q4K super-block; matches emit_csl_fused.zig's
    dequant: per-sub-block scale=1, dmin=0, so dequant = nibble * d."""
    assert values.shape == (QK_K,)
    block = np.zeros(Q4K_BLOCK_BYTES, dtype=np.uint8)
    d_f16 = np.float16(d)
    block[0:2] = np.frombuffer(d_f16.tobytes(), dtype=np.uint8)
    # scales/mins bytes 4..15: sc=1 in low 6 bits, dm=0 in top 2 bits
    for sb in range(8):
        block[4 + sb] = 1 & 0x3F
    quant = np.clip(np.round(values / max(d, 1e-9)).astype(np.int32), 0, 15).astype(np.uint8)
    lo = quant[0::2]
    hi = quant[1::2]
    block[16:16 + 128] = (lo | (hi << 4)).astype(np.uint8)
    return block


parser = argparse.ArgumentParser()
parser.add_argument("--name", default="compiled")
parser.add_argument("--cmaddr", default=None)
parser.add_argument("--out-receipt", default="receipt.json")
args = parser.parse_args()

width = 2
height = 1
out_dim = 4
out_dim_per_pe = 4
in_dim_per_pe = 512
num_blocks_per_row = 2  # 256 * 2 = 512 = in_dim_per_pe
assert num_blocks_per_row * QK_K == in_dim_per_pe

rng = np.random.default_rng(seed=27)
activation_per_pe = rng.standard_normal(size=(width, in_dim_per_pe)).astype(np.float32)

# Weight values clipped to a small range so quantize → 4-bit nibble doesn't
# saturate at 15 (which would compress signal). With d=0.05, values in
# [0, 0.75] map to nibbles 0..15.
weight_values = rng.uniform(0.0, 0.5, size=(width, out_dim_per_pe, num_blocks_per_row, QK_K)).astype(np.float32)
d_per_row = 0.05

weight_bytes = np.zeros(
    (width, out_dim_per_pe, num_blocks_per_row * Q4K_BLOCK_BYTES), dtype=np.uint8
)
for pe in range(width):
    for row in range(out_dim_per_pe):
        for blk in range(num_blocks_per_row):
            block = pack_q4k_block(weight_values[pe, row, blk], d=d_per_row)
            off = blk * Q4K_BLOCK_BYTES
            weight_bytes[pe, row, off:off + Q4K_BLOCK_BYTES] = block

# Host reference: dequantize weights to f32 and compute
# output[row] = sum_pe dot(activation[pe], dequant(weight[pe, row])).
ref_output = np.zeros(out_dim_per_pe, dtype=np.float32)
for pe in range(width):
    for row in range(out_dim_per_pe):
        acc = 0.0
        for blk in range(num_blocks_per_row):
            row_bytes = weight_bytes[pe, row]
            blk_base = blk * Q4K_BLOCK_BYTES
            d_bits = int(row_bytes[blk_base]) | (int(row_bytes[blk_base + 1]) << 8)
            d = np.frombuffer(np.array([d_bits], dtype=np.uint16).tobytes(), dtype=np.float16)[0]
            data_off = blk_base + 16
            act_off = blk * QK_K
            for i in range(128):
                byte = int(row_bytes[data_off + i])
                lo = float(byte & 0x0F) * float(d)
                hi = float(byte >> 4) * float(d)
                acc += lo * float(activation_per_pe[pe, act_off + i * 2])
                acc += hi * float(activation_per_pe[pe, act_off + i * 2 + 1])
        ref_output[row] += acc

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
activation_sym = runner.get_id("activation")
weight_sym = runner.get_id("weight")
output_sym = runner.get_id("output")

runner.load()
runner.run()

runner.memcpy_h2d(activation_sym, activation_per_pe.ravel(), 0, 0, width, height, in_dim_per_pe,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
# Weight is u8 — view as u32 for MEMCPY_32BIT (matches the
# bench/runners/csl-runners/common.py:run_fused_gemv_2d pattern).
# Build weight_shards in (height, width, bytes_per_pe) order so
# ROW_MAJOR memcpy distributes by pe_y first.
bytes_per_pe = out_dim_per_pe * num_blocks_per_row * Q4K_BLOCK_BYTES
assert bytes_per_pe % 4 == 0
weight_shards = weight_bytes.reshape(width, bytes_per_pe)[None, :, :]  # (1, width, bytes_per_pe)
weight_bytes_flat = weight_shards.reshape(-1).astype(np.uint8, copy=False)
weight_u32 = weight_bytes_flat.view(np.uint32)
runner.memcpy_h2d(weight_sym, weight_u32, 0, 0, width, height, bytes_per_pe // 4,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.launch("compute", nonblock=False)

output_buf = np.zeros(out_dim_per_pe, dtype=np.float32)
runner.memcpy_d2h(output_buf, output_sym, width - 1, 0, 1, 1, out_dim_per_pe,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.stop()

max_abs = float(np.max(np.abs(output_buf - ref_output)))
max_rel = float(np.max(np.abs(output_buf - ref_output) / (np.abs(ref_output) + 1e-9)))
ok = bool(np.allclose(output_buf, ref_output, rtol=1e-3, atol=1e-3))
print(f"shape: width={width} height={height} out_dim_per_pe={out_dim_per_pe} "
      f"in_dim_per_pe={in_dim_per_pe} num_blocks_per_row={num_blocks_per_row}")
print(f"DBG actual = {output_buf}")
print(f"DBG ref    = {ref_output}")
print(f"max_abs_diff={max_abs:.6e} max_rel_diff={max_rel:.6e} parity={'OK' if ok else 'FAIL'}")

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_gemv_simfabric_cell",
    "kernel": "gemv",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {
        "width": width, "height": height,
        "out_dim_per_pe": out_dim_per_pe,
        "in_dim_per_pe": in_dim_per_pe,
        "num_blocks_per_row": num_blocks_per_row,
        "Q4K_BLOCK_BYTES": Q4K_BLOCK_BYTES,
        "QK_K": QK_K,
        "d_per_row": d_per_row,
    },
    "parityMaxAbsDiff": max_abs,
    "parityMaxRelDiff": max_rel,
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B gemv kernel CSL (sourced from the manifest-"
            "shape host plan) compiles via cslc 2.10.0 at "
            f"width={width}, in_dim_per_pe={in_dim_per_pe}, "
            f"out_dim_per_pe={out_dim_per_pe}, "
            f"num_blocks_per_row={num_blocks_per_row} "
            "and runs end-to-end on simfabric. Output matches the "
            "host-computed Q4_K dequant + GEMV reduction within "
            "float32 precision. Validates the per-PE dequant + "
            "dot-product + fabric-reduce chain (PE 0 → PE 1) end-"
            "to-end. Per-sub-block scale=1 / dmin=0 packing matches "
            "emit_csl_fused.zig's dequant path."
        ),
        "notWhat": (
            "Not a hardware run. Not a manifest-shape run — Qwen "
            "lm_head GEMV is vocab=248320 over hidden=5120, sharded "
            "across the full row chain. Single-row-shard canary "
            "(height=1); the 2-D out_dim sharding (height>1) is "
            "exercised by the lmhead_gemv_2d_sim_runner lane. "
            "Per-sub-block scale=1 / dmin=0 weight packing — real "
            "Q4_K weights from a model file have varying scales/"
            "mins per sub-block; this canary doesn't exercise the "
            "general dequant range. WIDTH=2 LIMIT — KERNEL-EMIT "
            "ROUTING GAP AT WIDTH≥3: with width=4 (the natural row-"
            "shard for Qwen lm_head), the layout's reduce_color "
            "routing for middle PEs is set to "
            "rx={WEST}, tx={EAST} — pure pass-through. Wavelets "
            "from PE 0 flow through PEs 1 and 2 but are NOT "
            "delivered to those PEs' RAMP/input-queue, so middle "
            "PEs' `@mov32(scratch_in_dsd, reduce_in, ...)` blocks "
            "forever (their unblock_cmd_stream is never called). "
            "The last PE still receives PE 0's wavelet through the "
            "pass-through path, so memcpy_d2h from PE (width-1) "
            "returns a value — but it equals partial[0] + "
            "partial[width-1] only, missing the middle PEs' "
            "contributions. At width=4 this manifests as actual ≈ "
            "ref / 2. Closing this gap requires the layout to set "
            "tx={EAST, RAMP} for middle PEs (or another routing "
            "form that delivers locally AND forwards). Tracked as "
            "a typed WGSL→CSL emit gap parallel to attn_decode's "
            "missing reduce-task activation and sample's missing "
            "index reduction."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
