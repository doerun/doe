#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the rope (rotary position embedding) kernel."""

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
    head_dim = 128
    num_pairs = 64

    rng = np.random.default_rng(seed=17)
    per_pe_input = rng.standard_normal(size=(width, head_dim), dtype=np.float32)
    cos_host = np.cos(np.arange(num_pairs, dtype=np.float32) * 0.1)
    sin_host = np.sin(np.arange(num_pairs, dtype=np.float32) * 0.1)
    expected = per_pe_input.copy()
    for pe in range(width):
        for p in range(num_pairs):
            e, o = 2 * p, 2 * p + 1
            x0 = per_pe_input[pe, e]
            x1 = per_pe_input[pe, o]
            expected[pe, e] = x0 * cos_host[p] - x1 * sin_host[p]
            expected[pe, o] = x0 * sin_host[p] + x1 * cos_host[p]

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    input_sym = runner.get_id("input")
    cos_sym = runner.get_id("freq_cos")
    sin_sym = runner.get_id("freq_sin")
    runner.load()
    runner.run()
    runner.memcpy_h2d(input_sym, per_pe_input.flatten(), 0, 0, width, 1, head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    cos_flat = np.tile(cos_host, width); sin_flat = np.tile(sin_host, width)
    runner.memcpy_h2d(cos_sym, cos_flat, 0, 0, width, 1, num_pairs,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(sin_sym, sin_flat, 0, 0, width, 1, num_pairs,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)
    actual_flat = np.zeros(width * head_dim, dtype=np.float32)
    runner.memcpy_d2h(actual_flat, input_sym, 0, 0, width, 1, head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    actual = actual_flat.reshape(width, head_dim)
    max_abs_err = common.max_abs_error(actual, expected)
    passed = bool(np.allclose(actual, expected, atol=1e-5, rtol=1e-5))
    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err}")
        return 1

    common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="rope",
        cmaddr=cmaddr,
        width=width,
        chunk_size=head_dim,
        total_elements=width * head_dim,
        max_abs_err=max_abs_err,
        sample_input=per_pe_input[0, :4].tolist(),
        sample_expected=expected[0, :4].tolist(),
        sample_actual=actual[0, :4].tolist(),
    )
    print(f"PASS: rope {width} PEs, max_abs_err={max_abs_err:.3e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
