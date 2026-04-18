#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the reduce-sum-workgroup kernel.

Verifies iteration-27's lane-preserving single-PE reduction lowering:
the WGSL 256-wide workgroup reduction must produce mathematically
correct per-PE partial sums (not collapsed single-lane semantics).
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


def main() -> int:
    args = common.parse_runtime_args(__doc__ or "")

    width = 4
    wg_size = 256       # WGSL @workgroup_size(256)
    hidden_size = 1024  # Per-PE storage buffer (CSL param default)

    per_pe_input = np.zeros((width, hidden_size), dtype=np.float32)
    for p in range(width):
        for i in range(hidden_size):
            per_pe_input[p, i] = p * hidden_size + i
    input_host = per_pe_input.flatten()

    expected_per_pe = np.zeros(width, dtype=np.float32)
    for p in range(width):
        expected_per_pe[p] = sum(p * hidden_size + lane for lane in range(wg_size))

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    input_sym = runner.get_id("input")
    output_sym = runner.get_id("output")
    runner.load()
    runner.run()

    runner.memcpy_h2d(
        input_sym, input_host, 0, 0, width, 1, hidden_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.launch("compute", nonblock=False)

    actual_flat = np.zeros(width * hidden_size, dtype=np.float32)
    runner.memcpy_d2h(
        actual_flat, output_sym, 0, 0, width, 1, hidden_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.stop()

    actual_full = actual_flat.reshape(width, hidden_size)
    # The WGSL writes output[wid.x] = sum; wid.x maps to pe_id in the
    # lowering, so PE p's sum lives at actual_full[p, p] (local slot p).
    actual_per_pe = np.array([actual_full[p, p] for p in range(width)], dtype=np.float32)
    max_abs_err = common.max_abs_error(actual_per_pe, expected_per_pe)
    passed = bool(np.allclose(actual_per_pe, expected_per_pe, atol=1e-3, rtol=1e-6))
    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err}")
        return 1

    common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="reduce-sum-workgroup",
        cmaddr=cmaddr,
        width=width,
        chunk_size=hidden_size,
        total_elements=width * hidden_size,
        max_abs_err=max_abs_err,
        sample_input=per_pe_input[0, :4].tolist(),
        sample_expected=expected_per_pe.tolist(),
        sample_actual=actual_per_pe.tolist(),
    )
    print(f"PASS: reduce-sum-workgroup {width} PEs, max_abs_err={max_abs_err:.3e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
