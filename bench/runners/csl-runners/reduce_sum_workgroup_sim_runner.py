#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the reduce-sum-workgroup kernel.

Verifies iteration-27's lane-preserving single-PE reduction lowering:
the WGSL 256-wide workgroup reduction must produce mathematically
correct per-PE partial sums (not collapsed single-lane semantics).
"""

from __future__ import annotations

import argparse
import json
import sys
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

    cmaddr = args.cmaddr.strip() or None
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
    max_abs_err = float(np.max(np.abs(actual_per_pe - expected_per_pe)))
    passed = bool(np.allclose(actual_per_pe, expected_per_pe, atol=1e-3, rtol=1e-6))
    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err}")
        return 1

    trace = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_trace",
        "target": "wse3",
        "contract": "explicit_simulator_trace",
        "kernel": "reduce-sum-workgroup",
        "executionTarget": "system" if cmaddr else "simfabric",
        "width": width,
        "chunkSize": hidden_size,
        "totalElements": width * hidden_size,
        "runtimePassed": True,
        "runtimeMaxAbsErr": max_abs_err,
        "sampleInput": per_pe_input[0, :4].tolist(),
        "sampleExpected": expected_per_pe.tolist(),
        "sampleActual": actual_per_pe.tolist(),
    }
    Path(args.trace_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.trace_out).write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: reduce-sum-workgroup {width} PEs, max_abs_err={max_abs_err:.3e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
