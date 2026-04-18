#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the gather (embedding lookup) kernel.

Expected substitutions from csl_sdk_driver.run_simulation:
  --compile-dir={compile_output_dir}   # cslc output dir
  --trace-out={trace_path}             # schema-conforming trace JSON
  --cmaddr=...                         # optional CS endpoint
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compile-dir", required=True)
    parser.add_argument("--trace-out", required=True)
    parser.add_argument("--cmaddr", default="")
    args = parser.parse_args()

    width = 4
    hidden_size = 64
    rows_per_pe = 8
    num_tokens = 4
    total_rows = width * rows_per_pe

    rng = np.random.default_rng(seed=9)
    table_full = rng.standard_normal(size=(total_rows, hidden_size), dtype=np.float32)
    indices_host = rng.integers(0, total_rows, size=num_tokens, dtype=np.uint32)
    expected = table_full[indices_host]

    indices_flat = np.tile(indices_host, width)
    table_flat = np.zeros(width * rows_per_pe * hidden_size, dtype=np.float32)
    for pe in range(width):
        start = pe * rows_per_pe
        table_flat[pe * rows_per_pe * hidden_size:(pe + 1) * rows_per_pe * hidden_size] = \
            table_full[start:start + rows_per_pe].flatten()

    cmaddr = args.cmaddr.strip() or None
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    idx_sym = runner.get_id("indices")
    tbl_sym = runner.get_id("table")
    out_sym = runner.get_id("output")
    runner.load()
    runner.run()

    runner.memcpy_h2d(idx_sym, indices_flat, 0, 0, width, 1, num_tokens,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(tbl_sym, table_flat, 0, 0, width, 1, rows_per_pe * hidden_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)

    out_flat = np.zeros(width * num_tokens * hidden_size, dtype=np.float32)
    runner.memcpy_d2h(out_flat, out_sym, 0, 0, width, 1, num_tokens * hidden_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    out_per_pe = out_flat.reshape(width, num_tokens, hidden_size)
    actual = out_per_pe.sum(axis=0)
    max_abs_err = float(np.max(np.abs(actual - expected)))
    passed = bool(np.allclose(actual, expected, atol=1e-6, rtol=0.0))

    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err:.6f}")
        return 1

    # explicit_simulator_trace variant (user's iter-39 schema update).
    # Numerical detail lives inline; schema requires runtimePassed=true
    # so reaching here (after the passed guard) keeps the trace valid.
    trace = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_trace",
        "target": "wse3",
        "contract": "explicit_simulator_trace",
        "kernel": "gather",
        "executionTarget": "system" if cmaddr else "simfabric",
        "width": width,
        "chunkSize": hidden_size,
        "totalElements": num_tokens * hidden_size,
        "runtimePassed": True,
        "runtimeMaxAbsErr": max_abs_err,
        "sampleInput": indices_host.astype(np.float32).tolist(),
        "sampleExpected": expected[0, :4].tolist(),
        "sampleActual": actual[0, :4].tolist(),
    }
    trace_path = Path(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {num_tokens} tokens gathered, max_abs_err={max_abs_err:.3e}, trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
