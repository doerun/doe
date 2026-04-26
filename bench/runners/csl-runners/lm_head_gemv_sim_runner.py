#!/usr/bin/env cs_python
"""Real-canary CSL sim runner for the lm_head_gemv kernel.

Closes the CSL backend lane in `bench/tools/doe_parity.py:_run_csl_simfabric_backend`
for the bootstrap-shape lm_head_gemv real-canary fixture (A: [4] f32 input
vector, B: [16] f32 = 4x4 matrix, output: [4] f32). Pre-compiled compile-dir
lives at `bench/out/csl-real-canary-compile/lm_head_gemv/lm_head_gemv/`;
source CSL at `bench/out/csl-real-canary-source/lm_head_gemv/`.

Algorithm: output[i] = sum_k(B[i*K + k] * A[k]) for i in [0, M), k in [0, K)
with M=K=4. Reduction is in-order so the f32 output is bit-identical to the
numpy reference computed in source order, satisfying the algorithm_exact
contract. The reference output (zeros) is in
bench/fixtures/tsir-real-doppler-transcripts/lm_head_gemv.doppler-transcript.json
with probe hash 374708fff7719dd5979ec875d56cd2286f6d3cf7ec317a3b25632aab28ec37bb
(sha256 of 4 f32 zeros).

Usage (via runtime/zig/tools/cs_python_singularity.sh):

  cs_python_singularity.sh lm_head_gemv_sim_runner.py \\
    --compile-dir bench/out/csl-real-canary-compile/lm_head_gemv/lm_head_gemv \\
    --inputs bench/fixtures/tsir-bootstrap-inputs/lm_head_gemv.json \\
    --output-hash-out <path/to/lm_head_gemv.csl.hash>
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
    A = np.array(inputs["A"]["values"], dtype=np.float32)
    B = np.array(inputs["B"]["values"], dtype=np.float32)
    if A.size != 4 or B.size != 16:
        sys.stderr.write(
            f"lm_head_gemv_sim_runner: bootstrap fixture shape mismatch — "
            f"A has {A.size} elements (expected 4), B has {B.size} (expected 16)\n"
        )
        return 2

    cmaddr = args.cmaddr.strip() or None
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    A_sym = runner.get_id("A")
    B_sym = runner.get_id("B")
    output_sym = runner.get_id("output")

    runner.load()
    runner.run()

    runner.memcpy_h2d(
        A_sym, A, 0, 0, 1, 1, 4,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_h2d(
        B_sym, B.ravel(), 0, 0, 1, 1, 16,
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
