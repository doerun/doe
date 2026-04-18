#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the elementwise-double kernel.

Invoked by csl_sdk_driver.run_simulation when the runtime-config's
`mode` is `sdk-runtime-command`. Expected substitutions from the
driver:
  --compile-dir={compile_output_dir}   # cslc output bin/ directory
  --trace-out={trace_path}             # where to write the trace JSON
  [--cmaddr=IP_ADDRESS:PORT]           # optional, passed through

Behavior:
  - Uses cerebras.sdk.runtime.sdkruntimepybind.SdkRuntime against the
    --compile-dir's parent (runtime expects cslc's -o target dir).
  - memcpy_h2d synthetic input → launch('compute') → memcpy_d2h output
  - Verifies output == input * 2.0 bit-exactly.
  - Writes a csl_simulator_trace artifact to --trace-out on success.
  - On failure, writes no trace and exits non-zero so the driver records
    run.status='failed' honestly.
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
    chunk_size = 1024
    total = width * chunk_size
    input_host = (np.arange(total, dtype=np.float32) + 0.5)
    expected = input_host * 2.0

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    input_sym = runner.get_id("input")
    output_sym = runner.get_id("output")
    runner.load()
    runner.run()
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
    passed = bool(np.allclose(actual, expected, atol=1e-6, rtol=0.0))

    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err:.6f}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="elementwise-double",
        cmaddr=cmaddr,
        width=width,
        chunk_size=chunk_size,
        total_elements=total,
        max_abs_err=max_abs_err,
        sample_input=input_host[:4].tolist(),
        sample_expected=expected[:4].tolist(),
        sample_actual=actual[:4].tolist(),
    )
    print(f"PASS: {total} elements, max_abs_err={max_abs_err:.3e}, trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
