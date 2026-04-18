#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the GELU element-wise kernel."""

from __future__ import annotations

import sys

import numpy as np

import common

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)


def gelu_reference(x: np.ndarray) -> np.ndarray:
    inner = np.float32(0.7978845608) * (
        x + np.float32(0.044715) * x * x * x
    )
    inner_clamped = np.clip(inner, np.float32(-15.0), np.float32(15.0))
    return np.float32(0.5) * x * (np.float32(1.0) + np.tanh(inner_clamped))


def main() -> int:
    args = common.parse_runtime_args(__doc__ or "")

    width = 16
    chunk_size = 1024
    total = width * chunk_size
    input_host = np.linspace(-5.0, 5.0, num=total, dtype=np.float32)
    expected = gelu_reference(input_host).astype(np.float32)
    uniform_per_pe = np.array([total, 0, 0, 0], dtype=np.uint32)
    uniform_host = np.tile(uniform_per_pe, width)

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    u_sym = runner.get_id("u")
    input_sym = runner.get_id("input")
    output_sym = runner.get_id("output")
    runner.load()
    runner.run()
    runner.memcpy_h2d(
        u_sym, uniform_host, 0, 0, width, 1, 4,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.memcpy_h2d(
        input_sym, input_host, 0, 0, width, 1, chunk_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.launch("compute", nonblock=False)
    actual = np.zeros([total], dtype=np.float32)
    runner.memcpy_d2h(
        actual, output_sym, 0, 0, width, 1, chunk_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.stop()

    max_abs_err = common.max_abs_error(actual, expected)
    passed = bool(np.allclose(actual, expected, atol=1e-5, rtol=1e-5))
    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="gelu",
        cmaddr=cmaddr,
        width=width,
        chunk_size=chunk_size,
        total_elements=total,
        max_abs_err=max_abs_err,
        sample_input=input_host[:4].tolist(),
        sample_expected=expected[:4].tolist(),
        sample_actual=actual[:4].tolist(),
    )
    print(f"PASS: gelu {total} elements, max_abs_err={max_abs_err:.3e}, trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
