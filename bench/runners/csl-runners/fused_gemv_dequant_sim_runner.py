#!/usr/bin/env cs_python
"""Governed-lane runner for fused_gemv_dequant (host-side reduce variant).

Each PE dequants its Q4K weight slice and computes partial dot products into
`partial`. The host reads per-PE `partial` buffers and sums across PEs for the
final result. Bypasses the fabric allreduce whose hand-rolled async-send chain
has a known teardown-ordering stall (see bench/out/dual-compile-evidence/
fused-gemv-dequant/runtime-run/result.json iter-35/36 notes).

Numerical reference uses the same Q4K dequant semantics as the PE program:
  - QK_K = 256 values per block, 144 bytes per block layout:
      bytes 0..1 : f16 scale `d`
      bytes 2..15: padding (zero)
      bytes 16..143 : 128 packed bytes = 256 4-bit nibbles
  - Each byte yields (lo = byte & 0x0F, hi = byte >> 4) as unsigned integers,
    scaled by `d`, multiplied with two successive activations.
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


def build_block(rng: np.random.Generator) -> tuple[np.ndarray, float]:
    """Make one 144-byte Q4K block and return (bytes, scale_as_f32)."""
    d_f16 = np.array([rng.uniform(0.01, 0.1)], dtype=np.float16)
    d_bytes = d_f16.view(np.uint8)
    packed = rng.integers(0, 256, size=128, dtype=np.uint8)
    block = np.zeros(Q4K_BLOCK_BYTES, dtype=np.uint8)
    block[0:2] = d_bytes
    block[16:144] = packed
    return block, float(d_f16[0])


def dequant_block_mul(block: np.ndarray, d: float, activations: np.ndarray) -> float:
    """Matches the PE program's accumulation order bit-for-bit."""
    acc = np.float32(0.0)
    packed = block[16:16 + 128]
    for j in range(128):
        byte = int(packed[j])
        lo = np.float32((byte & 0x0F)) * np.float32(d)
        hi = np.float32((byte >> 4)) * np.float32(d)
        acc += lo * activations[j * 2]
        acc += hi * activations[j * 2 + 1]
    return float(acc)


def main() -> int:
    args = common.parse_runtime_args(__doc__ or "")

    width = 4
    out_dim = 64
    num_blocks_per_row = 2
    in_dim_per_pe = num_blocks_per_row * QK_K

    rng = np.random.default_rng(seed=17)
    activations = rng.standard_normal(size=(width, in_dim_per_pe), dtype=np.float32)
    weights_per_pe = np.zeros((width, out_dim, num_blocks_per_row, Q4K_BLOCK_BYTES), dtype=np.uint8)
    scales_per_pe = np.zeros((width, out_dim, num_blocks_per_row), dtype=np.float32)
    for pe in range(width):
        for r in range(out_dim):
            for b in range(num_blocks_per_row):
                block, scale = build_block(rng)
                weights_per_pe[pe, r, b] = block
                scales_per_pe[pe, r, b] = scale

    expected_partial = np.zeros((width, out_dim), dtype=np.float32)
    for pe in range(width):
        for r in range(out_dim):
            total = np.float32(0.0)
            for b in range(num_blocks_per_row):
                act_slice = activations[pe, b * QK_K:(b + 1) * QK_K]
                total += dequant_block_mul(weights_per_pe[pe, r, b], scales_per_pe[pe, r, b], act_slice)
            expected_partial[pe, r] = total

    expected_result = expected_partial.sum(axis=0)

    activations_flat = activations.ravel().astype(np.float32)
    weights_flat = weights_per_pe.reshape(width, -1).ravel().astype(np.uint8)

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    act_sym = runner.get_id("activations")
    wts_sym = runner.get_id("weights")
    par_sym = runner.get_id("partial")
    runner.load()
    runner.run()

    runner.memcpy_h2d(act_sym, activations_flat, 0, 0, width, 1, in_dim_per_pe,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    weights_per_pe_bytes = out_dim * num_blocks_per_row * Q4K_BLOCK_BYTES
    assert weights_per_pe_bytes % 4 == 0, "weight buffer must be 32-bit-aligned for memcpy"
    weights_u32 = weights_flat.view(np.uint32)
    runner.memcpy_h2d(wts_sym, weights_u32, 0, 0, width, 1, weights_per_pe_bytes // 4,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)

    partial_flat = np.zeros(width * out_dim, dtype=np.float32)
    runner.memcpy_d2h(partial_flat, par_sym, 0, 0, width, 1, out_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    actual_partial = partial_flat.reshape(width, out_dim)
    actual_result = actual_partial.sum(axis=0)

    per_pe_err = common.max_abs_error(actual_partial, expected_partial)
    reduce_err = common.max_abs_error(actual_result, expected_result)
    passed = bool(
        np.allclose(actual_partial, expected_partial, atol=1e-4, rtol=1e-4)
        and np.allclose(actual_result, expected_result, atol=1e-3, rtol=1e-4)
    )

    if not passed:
        print(f"FAIL: per_pe_err={per_pe_err:.6f} reduce_err={reduce_err:.6f}")
        print(f"  expected_partial[0, :4] = {expected_partial[0, :4]}")
        print(f"  actual_partial[0, :4]   = {actual_partial[0, :4]}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="fused-gemv-dequant",
        cmaddr=cmaddr,
        width=width,
        chunk_size=out_dim,
        total_elements=width * out_dim,
        max_abs_err=reduce_err,
        sample_input=activations[0, :4].tolist(),
        sample_expected=expected_result[:4].tolist(),
        sample_actual=actual_result[:4].tolist(),
    )
    print(f"PASS: fused-gemv-dequant out_dim={out_dim} per_pe_err={per_pe_err:.3e} "
          f"reduce_err={reduce_err:.3e}, trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
