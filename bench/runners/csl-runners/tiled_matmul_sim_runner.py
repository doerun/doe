#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the tiled_matmul (SUMMA GEMM) kernel.

Expected substitutions from csl_sdk_driver.run_simulation:
  --compile-dir={compile_output_dir}   # cslc output dir
  --trace-out={trace_path}             # schema-conforming trace JSON
  --cmaddr=...                         # optional CS endpoint

Host tile placement follows the canonical SDK SUMMA reference at
csl-extras/examples/benchmarks/gemm-collectives_2d/run.py: local tiles
are stored COLUMN-MAJOR via A1.reshape(h,Mt,w,Kt).transpose(0,2,3,1)
before flatten; memcpy_h2d is called with (x=w, y=h).

Iteration 43 achieved bit-exact parity (max_abs_err=0.0) after the Doe
emitter's GEMM step was rewritten to the canonical @set_dsd_base_addr
+ @increment_dsd_offset pattern. This runner is the shared-runner-template
registration of that win.
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

    # Must match --params passed at cslc time via the simulator-plan
    # compileTargets[0].compileParams: P:2 Mt:8 Kt:8 Nt:8
    P = 2
    Mt = 8
    Kt = 8
    Nt = 8
    M = P * Mt
    K = P * Kt
    N = P * Nt

    rng = np.random.default_rng(seed=42)
    A = rng.standard_normal(size=(M, K), dtype=np.float32)
    B = rng.standard_normal(size=(K, N), dtype=np.float32)
    expected = A @ B

    h = P
    w = P
    A1 = A.reshape(h, Mt, w, Kt)
    A2 = A1.transpose(0, 2, 3, 1)
    A3 = A2.reshape(h, w, Mt * Kt)

    B1 = B.reshape(h, Kt, w, Nt)
    B2 = B1.transpose(0, 2, 3, 1)
    B3 = B2.reshape(h, w, Kt * Nt)

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    a_sym = runner.get_id("A")
    b_sym = runner.get_id("B")
    c_sym = runner.get_id("C")
    runner.load()
    runner.run()

    runner.memcpy_h2d(
        a_sym, A3.ravel(), 0, 0, w, h, Mt * Kt,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.memcpy_h2d(
        b_sym, B3.ravel(), 0, 0, w, h, Kt * Nt,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.launch("compute", nonblock=False)

    c_flat = np.zeros(h * w * Mt * Nt, dtype=np.float32)
    runner.memcpy_d2h(
        c_flat, c_sym, 0, 0, w, h, Mt * Nt,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.stop()

    c_tiles = c_flat.reshape((h, w, Nt, Mt)).transpose(0, 3, 1, 2)
    actual = c_tiles.reshape(M, N)

    max_abs_err = common.max_abs_error(actual, expected)
    passed = bool(np.allclose(actual, expected, atol=1e-3, rtol=1e-3))

    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err:.6f}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="tiled-matmul",
        cmaddr=cmaddr,
        width=w * h,
        chunk_size=Mt * Nt,
        total_elements=M * N,
        max_abs_err=max_abs_err,
        sample_input=A[0, :4].tolist(),
        sample_expected=expected[0, :4].tolist(),
        sample_actual=actual[0, :4].tolist(),
    )
    print(f"PASS: {M}x{K} @ {K}x{N} SUMMA matmul, max_abs_err={max_abs_err:.3e}, trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
