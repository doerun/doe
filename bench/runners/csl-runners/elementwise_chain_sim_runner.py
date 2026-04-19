#!/usr/bin/env cs_python
"""2-kernel chain: elementwise-double applied twice. output = input * 4.0.

For a chain of identical kernels, a single SdkRuntime drives two sequential
compute launches. Step 1: h2d(input) → launch → d2h(output1). Step 2:
h2d(output1 as input) → launch → d2h(output2). End-to-end parity verifies
output2 equals input * 4.0 bit-exactly against numpy.

SDK constraint surfaced during this work: two SdkRuntime instances in the
same Python process trigger `simfab_api.cc:111: Assertion '0' failed`.
That blocks chains of DIFFERENT kernels in a single process. Possible
paths for different-kernel chains: (a) spawn per-kernel subprocesses and
pipe tensors through host files; (b) partition PE grid so each kernel
occupies its own rectangle and one SdkRuntime drives the whole fabric.
This harness handles the same-kernel case today and documents (a)/(b)
as the generalization for the Gemma-prefill chain.

The chain schema for this receipt lives at
config/doe-kernel-chain-parity.schema.json.
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--compile-dir", required=True,
                   help="Single compile dir (elementwise-double) — same kernel runs twice.")
    p.add_argument("--chain-receipt-out", required=True)
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


def endpoint(raw: str) -> str | None:
    stripped = raw.strip()
    return stripped or None


def max_abs(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.max(np.abs(a - b)))


def main() -> int:
    args = parse_args()
    width = 4
    chunk_size = 1024
    total = width * chunk_size

    input_host = (np.arange(total, dtype=np.float32) + 0.5)
    expected_step1 = input_host * 2.0
    expected_end_to_end = input_host * 4.0

    cmaddr = endpoint(args.cmaddr)

    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    in_sym = runner.get_id("input")
    out_sym = runner.get_id("output")
    runner.load()
    runner.run()

    # Step 1: h2d(input) → launch → d2h(output1).
    runner.memcpy_h2d(in_sym, input_host, 0, 0, width, 1, chunk_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)
    output_step1 = np.zeros([total], dtype=np.float32)
    runner.memcpy_d2h(output_step1, out_sym, 0, 0, width, 1, chunk_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    step1_err = max_abs(output_step1, expected_step1)

    # Step 2: h2d(output1 → input) → launch → d2h(output2).
    runner.memcpy_h2d(in_sym, output_step1, 0, 0, width, 1, chunk_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)
    output_step2 = np.zeros([total], dtype=np.float32)
    runner.memcpy_d2h(output_step2, out_sym, 0, 0, width, 1, chunk_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    step2_err = max_abs(output_step2, output_step1 * 2.0)
    end_to_end_err = max_abs(output_step2, expected_end_to_end)

    step1_pass = bool(np.allclose(output_step1, expected_step1, atol=1e-6, rtol=0.0))
    step2_pass = bool(np.allclose(output_step2, output_step1 * 2.0, atol=1e-6, rtol=0.0))
    end_to_end_pass = bool(np.allclose(output_step2, expected_end_to_end, atol=1e-6, rtol=0.0))

    if end_to_end_err == 0.0 and step1_err == 0.0 and step2_err == 0.0:
        lane_status = "bit_exact"
    elif end_to_end_pass and step1_pass and step2_pass:
        lane_status = "bit_close"
    else:
        lane_status = "failed"

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_kernel_chain_parity",
        "target": "wse3",
        "chainName": "elementwise-double-x2",
        "description": "Apply elementwise-double twice: output = input * 4.0. Smallest composition that exercises the d2h→h2d handoff pattern.",
        "executionTarget": "system" if cmaddr else "simfabric",
        "steps": [
            {
                "stepIndex": 0,
                "fixtureId": "elementwise-double",
                "kernelPattern": "element_wise",
                "compileDir": str(args.compile_dir),
                "perStepParity": {
                    "maxAbsErr": step1_err,
                    "passed": step1_pass,
                    "atol": 1e-6,
                    "rtol": 0.0,
                },
            },
            {
                "stepIndex": 1,
                "fixtureId": "elementwise-double",
                "kernelPattern": "element_wise",
                "compileDir": str(args.compile_dir),
                "perStepParity": {
                    "maxAbsErr": step2_err,
                    "passed": step2_pass,
                    "atol": 1e-6,
                    "rtol": 0.0,
                },
            },
        ],
        "endToEndParity": {
            "maxAbsErr": end_to_end_err,
            "passed": end_to_end_pass,
            "atol": 1e-6,
            "rtol": 0.0,
            "sampleExpected": expected_end_to_end[:4].tolist(),
            "sampleActual": output_step2[:4].tolist(),
        },
        "laneStatus": lane_status,
    }

    out_path = Path(args.chain_receipt_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    if not end_to_end_pass:
        print(f"FAIL: end-to-end max_abs_err={end_to_end_err:.6f} "
              f"(step1={step1_err:.6f}, step2={step2_err:.6f})")
        return 1
    print(f"PASS: chain elementwise-double x 2 "
          f"(step1 err={step1_err:.3e}, step2 err={step2_err:.3e}, "
          f"end-to-end err={end_to_end_err:.3e}, status={lane_status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
