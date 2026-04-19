#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the attention_tiled (Flash Attention) kernel.

Each PE computes a single attention output row: O[d] for d in [0, head_dim)
given Q[d], K[kv_len, head_dim], V[kv_len, head_dim] using blocked online
softmax (block_size=32) with scale=0.125 applied to QK^T.

The kernel's layout allocates Q, K, V, O as [q_len*head_dim], [kv_len*head_dim],
[kv_len*head_dim], [q_len*head_dim] per-PE but only references row 0 of Q/O,
so this runner uses distinct random (Q, K, V) per PE and verifies the
emitted O[0:head_dim] against a numpy Flash Attention reference.
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


def flash_attention_reference(q: np.ndarray, k: np.ndarray, v: np.ndarray, scale: float) -> np.ndarray:
    scores = (k @ q) * scale
    m = float(np.max(scores))
    w = np.exp(scores - m)
    l = float(np.sum(w))
    return (w @ v) / l


def main() -> int:
    args = common.parse_runtime_args(__doc__ or "")

    # Must match simulator-plan compileTargets[0].compileParams.
    width = 4
    head_dim = 32
    kv_len = 64
    q_len = 32
    scale = np.float32(0.125)

    q_elems = q_len * head_dim
    kv_elems = kv_len * head_dim

    rng = np.random.default_rng(seed=7)
    q_per_pe = rng.standard_normal(size=(width, q_len, head_dim), dtype=np.float32)
    k_per_pe = rng.standard_normal(size=(width, kv_len, head_dim), dtype=np.float32)
    v_per_pe = rng.standard_normal(size=(width, kv_len, head_dim), dtype=np.float32)

    expected = np.zeros((width, head_dim), dtype=np.float32)
    for pe in range(width):
        expected[pe] = flash_attention_reference(
            q_per_pe[pe, 0], k_per_pe[pe], v_per_pe[pe], float(scale)
        )

    q_flat = q_per_pe.reshape(width, q_elems).ravel()
    k_flat = k_per_pe.reshape(width, kv_elems).ravel()
    v_flat = v_per_pe.reshape(width, kv_elems).ravel()

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    q_sym = runner.get_id("Q")
    k_sym = runner.get_id("K")
    v_sym = runner.get_id("V")
    o_sym = runner.get_id("O")
    runner.load()
    runner.run()

    runner.memcpy_h2d(q_sym, q_flat, 0, 0, width, 1, q_elems,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(k_sym, k_flat, 0, 0, width, 1, kv_elems,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(v_sym, v_flat, 0, 0, width, 1, kv_elems,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)

    o_flat = np.zeros(width * q_elems, dtype=np.float32)
    runner.memcpy_d2h(o_flat, o_sym, 0, 0, width, 1, q_elems,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    actual = o_flat.reshape(width, q_len, head_dim)[:, 0, :]
    max_abs_err = common.max_abs_error(actual, expected)
    passed = bool(np.allclose(actual, expected, atol=5e-5, rtol=5e-4))

    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err:.6f}")
        print(f"  expected[0, :4] = {expected[0, :4]}")
        print(f"  actual[0, :4]   = {actual[0, :4]}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="attention-tiled",
        cmaddr=cmaddr,
        width=width,
        chunk_size=head_dim,
        total_elements=width * head_dim,
        max_abs_err=max_abs_err,
        sample_input=q_per_pe[0, 0, :4].tolist(),
        sample_expected=expected[0, :4].tolist(),
        sample_actual=actual[0, :4].tolist(),
    )
    print(f"PASS: {width} x flash-attention (kv_len={kv_len}, head_dim={head_dim}), "
          f"max_abs_err={max_abs_err:.3e}, trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
