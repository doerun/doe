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

import argparse
import json
import os
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
    parser.add_argument("--compile-dir", required=True, help="cslc -o directory containing bin/")
    parser.add_argument("--trace-out", required=True)
    parser.add_argument("--cmaddr", default="", help="Optional CS system endpoint")
    args = parser.parse_args()

    width = 4
    chunk_size = 1024
    total = width * chunk_size
    input_host = (np.arange(total, dtype=np.float32) + 0.5)
    expected = input_host * 2.0

    cmaddr = args.cmaddr.strip() or None
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

    max_abs_err = float(np.max(np.abs(actual - expected)))
    passed = bool(np.allclose(actual, expected, atol=1e-6, rtol=0.0))

    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err:.6f}")
        return 1

    # Write a csl_simulator_trace artifact conforming to
    # config/doe-wgsl-simulator-trace.schema.json (contract:
    # compile_run_smoke_summary, runtimeMode: sdk_runtime_smoke,
    # additionalProperties: false). Kernel-specific numerical details
    # (max_abs_err, samples) live in the sibling result JSON below.
    from datetime import datetime, timezone
    trace = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_trace",
        "target": "wse3",
        "contract": "compile_run_smoke_summary",
        "driverExecutable": os.environ.get("DOE_CSL_RUNTIME_EXECUTABLE", "cs_python"),
        "compiledTargetCount": 1,
        "compiledTargets": [
            {"name": "elementwise-double", "artifactDir": args.compile_dir},
        ],
        "peGrid": {"width": width, "height": 1},
        "prefillLaunchCount": 1,
        "decodeLaunchCount": 0,
        "runtimeMode": "sdk_runtime_smoke",
        "simfabTracesPath": None,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    trace_path = Path(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    # Kernel-specific numerical receipt alongside the schema-conforming trace.
    result_path = trace_path.with_suffix(".kernel-result.json")
    result_path.write_text(
        json.dumps({
            "kernel": "elementwise-double",
            "passed": True,
            "maxAbsErr": max_abs_err,
            "width": width,
            "chunkSize": chunk_size,
            "totalElements": total,
            "executionTarget": "system" if cmaddr else "simfabric",
            "sampleInput": input_host[:4].tolist(),
            "sampleExpected": expected[:4].tolist(),
            "sampleActual": actual[:4].tolist(),
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PASS: {total} elements, max_abs_err={max_abs_err:.3e}, trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
