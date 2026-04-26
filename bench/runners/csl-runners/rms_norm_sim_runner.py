#!/usr/bin/env cs_python
"""Real-canary CSL sim runner for the rmsnorm kernel.

Closes the CSL backend lane in `bench/tools/doe_parity.py:_run_csl_simfabric_backend`
for the bootstrap-shape rmsnorm real-canary fixture (input: [4] f32,
weight: [4] f32, u: [2] f32 with [size, epsilon], output: [4] f32).
Pre-compiled compile-dir lives at
`bench/out/csl-real-canary-compile/rms_norm/rms_norm/`; source CSL at
`bench/out/csl-real-canary-source/rms_norm/`.

Algorithm (matches the numpy reference in
bench/fixtures/tsir-real-doppler-transcripts/rmsnorm.doppler-transcript.json):

  sum_sq = sum_{i=0..N} input[i] * input[i]   (in-order accumulation)
  mean_sq = sum_sq / N
  inv_rms = 1.0 / sqrt(mean_sq + u[1])         (straight 1/sqrt, NOT sqrt_nr)
  output[i] = input[i] * inv_rms * weight[i]

algorithm_exact contract: same reduction order + same dtype (f32) =>
bit-identical output bytes to the numpy reference. Probe hash:
8ad3e84903b3f0eca62a7ea22ed988839aef0bb554e27a945f34ab6ec682297f.

Usage (via runtime/zig/tools/cs_python_singularity.sh):

  cs_python_singularity.sh rms_norm_sim_runner.py \\
    --compile-dir bench/out/csl-real-canary-compile/rms_norm/rms_norm \\
    --inputs bench/fixtures/tsir-bootstrap-inputs/rmsnorm.json \\
    --output-hash-out <path/to/rmsnorm.csl.hash>
"""

from __future__ import annotations

import argparse
import hashlib
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
    p = argparse.ArgumentParser(description=__doc__ or "")
    p.add_argument("--compile-dir", required=True)
    p.add_argument("--inputs", required=True, help="bootstrap input fixture path")
    p.add_argument(
        "--output-hash-out",
        required=True,
        help="path to write the sha256 hex digest of the f32 output bytes",
    )
    p.add_argument("--cmaddr", default="", help="optional CS endpoint")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    fixture = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    inputs = fixture["inputs"]
    input_v = np.array(inputs["input"]["values"], dtype=np.float32)
    weight = np.array(inputs["weight"]["values"], dtype=np.float32)
    u = np.array(inputs["u"]["values"], dtype=np.float32)
    if input_v.size != 4 or weight.size != 4 or u.size < 2:
        sys.stderr.write(
            f"rmsnorm_sim_runner: bootstrap fixture shape mismatch — "
            f"input/weight must be 4 (got {input_v.size}/{weight.size}), "
            f"u must have >=2 elements (got {u.size})\n"
        )
        return 2
    # Pad u to exactly 2 elements (CSL kernel reads u[0]/u[1]; only u[1]
    # = epsilon is used).
    u2 = np.zeros(2, dtype=np.float32)
    u2[: min(2, u.size)] = u[: min(2, u.size)]

    cmaddr = args.cmaddr.strip() or None
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    input_sym = runner.get_id("input")
    weight_sym = runner.get_id("weight")
    u_sym = runner.get_id("u")
    output_sym = runner.get_id("output")

    runner.load()
    runner.run()

    runner.memcpy_h2d(
        input_sym, input_v, 0, 0, 1, 1, 4,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_h2d(
        weight_sym, weight, 0, 0, 1, 1, 4,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_h2d(
        u_sym, u2, 0, 0, 1, 1, 2,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.launch("compute", nonblock=False)

    output = np.zeros(4, dtype=np.float32)
    runner.memcpy_d2h(
        output, output_sym, 0, 0, 1, 1, 4,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.stop()

    digest = hashlib.sha256(output.tobytes()).hexdigest()
    out_path = Path(args.output_hash_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(digest + "\n", encoding="utf-8")
    print(f"OK {digest} output={output.tolist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
