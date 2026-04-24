#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the 2-D sharded lm_head fused GEMV.

Drives the host side of the 2-D sharding contract emit_csl_fused.zig now
produces: width shards in_dim (east-west reduce), height shards out_dim.
Host tiles activation across width, stages weight per (pe_y, pe_x) shard,
launches compute once, then D2H reads from each row's sink PE
(pe_x=width-1) and concatenates out_dim_per_pe slices across pe_y rows.

Verifies the reassembled out_dim_total output against a pure-numpy Q4K
dequant + matmul reference.
"""

from __future__ import annotations

import sys

import numpy as np

import common

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)


QK_K = 256
Q4K_BLOCK_BYTES = 144
QK_SUBBLOCK = 32  # 8 sub-blocks of 32 elements per Q4K super-block


def pack_q4k_block(values: np.ndarray, d: float, dmin: float) -> np.ndarray:
    """Emit a 144-byte Q4K block covering 256 weights.

    Layout (matches emit_csl_fused.zig's dequant path):
      bytes 0..1  f16 d   (super-block scale)
      bytes 2..3  f16 dmin (super-block min; unused by the kernel — it
                            uses dmin=0 semantics, so we set 0 here too)
      bytes 4..11 per-sub-block scale nibble (0x3F mask of byte)
                  and dmin-mul nibble (byte >> 6). The kernel reads a
                  single byte per sub-block.
      bytes 12..15 padding
      bytes 16..143 nibble-packed quantized values (128 bytes = 256 nibbles)
    """
    assert values.shape == (QK_K,)
    block = np.zeros(Q4K_BLOCK_BYTES, dtype=np.uint8)
    d_f16 = np.float16(d)
    dmin_f16 = np.float16(dmin)
    block[0:2] = np.frombuffer(d_f16.tobytes(), dtype=np.uint8)
    block[2:4] = np.frombuffer(dmin_f16.tobytes(), dtype=np.uint8)
    # Per-sub-block scale/min bytes: low 6 bits encode `sc`, top 2 bits
    # encode `dm_nibble`. We use sc=1, dm=0 so dequantized = d * nibble.
    for sb in range(8):
        block[4 + sb] = 1 & 0x3F
    # Quantize values to 4-bit nibbles by dividing by d (truncate to 0..15).
    # The kernel computes: out = nibble * scales[sb] - mins[sb], where
    # scales[sb] = d * (sc & 0x3F) = d * 1, mins[sb] = dmin * (sc >> 6) = 0.
    # So we quantize values / d and pack as nibbles.
    quant = np.clip(np.round(values / max(d, 1e-9)).astype(np.int32), 0, 15).astype(np.uint8)
    lo_nibbles = quant[0::2]
    hi_nibbles = quant[1::2]
    block[16:16 + 128] = (lo_nibbles | (hi_nibbles << 4)).astype(np.uint8)
    return block


def numpy_fused_gemv_reference(
    *, activation: np.ndarray, weight_blocks: np.ndarray,
    out_dim: int, num_blocks_per_row: int, in_dim_per_pe: int, width: int,
) -> np.ndarray:
    """Compute the expected fused-GEMV output: reduce across width PEs of
    per-row dot products between activation and the dequantized weight
    blocks. Weight layout matches the kernel: for each (row in 0..out_dim),
    num_blocks_per_row consecutive Q4K blocks of 256 weights each."""
    assert weight_blocks.shape == (width, out_dim, num_blocks_per_row * Q4K_BLOCK_BYTES)
    assert activation.shape == (width, in_dim_per_pe)
    result = np.zeros(out_dim, dtype=np.float32)
    for pe_x in range(width):
        for row in range(out_dim):
            row_bytes = weight_blocks[pe_x, row]
            partial = 0.0
            for blk in range(num_blocks_per_row):
                blk_base = blk * Q4K_BLOCK_BYTES
                d_bits = int(row_bytes[blk_base]) | (int(row_bytes[blk_base + 1]) << 8)
                d = np.frombuffer(
                    np.array([d_bits], dtype=np.uint16).tobytes(), dtype=np.float16
                )[0]
                data_off = blk_base + 16
                act_off = blk * QK_K
                for i in range(128):
                    byte = int(row_bytes[data_off + i])
                    lo = float(byte & 0x0F) * float(d)
                    hi = float(byte >> 4) * float(d)
                    partial += lo * float(activation[pe_x, act_off + i * 2])
                    partial += hi * float(activation[pe_x, act_off + i * 2 + 1])
            result[row] += partial
    return result


def main() -> int:
    args = common.parse_runtime_args(__doc__ or "")

    # Small-shape fixture sized to the pre-shard 1-D case (height=1) so
    # numpy reference time stays bounded. Real HostPlan-bound runs
    # override via compileParams. This is the governed-lane smoke.
    width = 4
    height = 1
    in_dim_per_pe = 512
    out_dim_total = 16
    out_dim_per_pe = 16
    num_blocks_per_row = 2

    rng = np.random.default_rng(seed=23)
    activation_per_pe = rng.standard_normal(
        size=(width, in_dim_per_pe), dtype=np.float32
    ).astype(np.float32)

    # Build a per-PE-row weight of shape
    # (height, width, out_dim_per_pe, num_blocks_per_row * Q4K_BLOCK_BYTES).
    weight_values = rng.standard_normal(
        size=(height, width, out_dim_per_pe, num_blocks_per_row, QK_K),
    ).astype(np.float32) * 0.01
    weight_bytes = np.zeros(
        (height, width, out_dim_per_pe, num_blocks_per_row * Q4K_BLOCK_BYTES),
        dtype=np.uint8,
    )
    d_per_row = 0.01
    for pe_y in range(height):
        for pe_x in range(width):
            for row in range(out_dim_per_pe):
                for blk in range(num_blocks_per_row):
                    block = pack_q4k_block(
                        weight_values[pe_y, pe_x, row, blk],
                        d=d_per_row, dmin=0.0,
                    )
                    off = blk * Q4K_BLOCK_BYTES
                    weight_bytes[pe_y, pe_x, row, off:off + Q4K_BLOCK_BYTES] = block

    # Numpy reference: reduce across width for this row-shard (pe_y=0).
    expected_per_row_shard = []
    for pe_y in range(height):
        row_shard_weight = weight_bytes[pe_y].reshape(
            width, out_dim_per_pe, num_blocks_per_row * Q4K_BLOCK_BYTES
        )
        expected_shard = numpy_fused_gemv_reference(
            activation=activation_per_pe,
            weight_blocks=row_shard_weight,
            out_dim=out_dim_per_pe,
            num_blocks_per_row=num_blocks_per_row,
            in_dim_per_pe=in_dim_per_pe,
            width=width,
        )
        expected_per_row_shard.append(expected_shard)
    expected_full = np.concatenate(expected_per_row_shard)[:out_dim_total]

    # Weight input to host helper: flatten per (pe_y, pe_x) to the shard's
    # out_dim_per_pe × num_blocks_per_row × Q4K_BLOCK_BYTES bytes.
    weight_shards = weight_bytes.reshape(
        height, width, out_dim_per_pe * num_blocks_per_row * Q4K_BLOCK_BYTES
    )

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    runner.load()
    runner.run()
    actual = common.run_fused_gemv_2d(
        runner=runner,
        activation=activation_per_pe,
        weight_shards=weight_shards,
        width=width,
        height=height,
        in_dim_per_pe=in_dim_per_pe,
        out_dim_per_pe=out_dim_per_pe,
        out_dim_total=out_dim_total,
        num_blocks_per_row=num_blocks_per_row,
        activation_symbol="activations",
        weight_symbol="weights",
        output_symbol="result",
        compute_symbol="compute",
        memcpy_data_type=MemcpyDataType,
        memcpy_order=MemcpyOrder,
    )
    runner.stop()

    max_abs_err = common.max_abs_error(actual, expected_full)
    passed = bool(np.allclose(actual, expected_full, atol=1e-3, rtol=1e-2))
    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err:.6f}")
        print(f"  expected[:4] = {expected_full[:4]}")
        print(f"  actual[:4]   = {actual[:4]}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="lm_head-gemv-2d",
        cmaddr=cmaddr,
        width=width,
        chunk_size=out_dim_per_pe,
        total_elements=out_dim_total,
        max_abs_err=max_abs_err,
        sample_input=activation_per_pe[0, :4].tolist(),
        sample_expected=expected_full[:4].tolist(),
        sample_actual=actual[:4].tolist(),
    )
    print(
        f"PASS: 2-D fused GEMV "
        f"(width={width}, height={height}, "
        f"out_dim_total={out_dim_total}, out_dim_per_pe={out_dim_per_pe}), "
        f"max_abs_err={max_abs_err:.3e}, trace={trace_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
