#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the attention_linear kernel."""

from __future__ import annotations

import sys

import numpy as np

import common

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)


def main() -> int:
    args = common.parse_runtime_args(__doc__ or "")

    width = 4
    head_dim = 64
    kv_len = 16
    scale = 0.125

    rng = np.random.default_rng(seed=13)
    Q_host = rng.standard_normal(size=(width, head_dim), dtype=np.float32)
    K_host = rng.standard_normal(size=(width, kv_len, head_dim), dtype=np.float32)
    V_host = rng.standard_normal(size=(width, kv_len, head_dim), dtype=np.float32)
    expected = np.zeros((width, head_dim), dtype=np.float32)
    for pe in range(width):
        for kv in range(kv_len):
            s = float(np.dot(Q_host[pe], K_host[pe, kv]) * scale)
            expected[pe] += s * V_host[pe, kv]

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    q_sym = runner.get_id("query"); k_sym = runner.get_id("key")
    v_sym = runner.get_id("val"); o_sym = runner.get_id("output")
    runner.load(); runner.run()
    runner.memcpy_h2d(q_sym, Q_host.flatten(), 0, 0, width, 1, head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(k_sym, K_host.reshape(width, -1).flatten(), 0, 0, width, 1, kv_len * head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(v_sym, V_host.reshape(width, -1).flatten(), 0, 0, width, 1, kv_len * head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)
    actual_flat = np.zeros(width * head_dim, dtype=np.float32)
    runner.memcpy_d2h(actual_flat, o_sym, 0, 0, width, 1, head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    actual = actual_flat.reshape(width, head_dim)
    max_abs_err = common.max_abs_error(actual, expected)
    passed = bool(np.allclose(actual, expected, atol=1e-3, rtol=1e-3))
    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err}")
        return 1

    common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="attention-linear",
        cmaddr=cmaddr,
        width=width,
        chunk_size=head_dim,
        total_elements=width * head_dim,
        max_abs_err=max_abs_err,
        sample_input=Q_host[0, :4].tolist(),
        sample_expected=expected[0, :4].tolist(),
        sample_actual=actual[0, :4].tolist(),
    )
    print(f"PASS: attention_linear head_dim={head_dim} kv_len={kv_len}, max_abs_err={max_abs_err:.3e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
