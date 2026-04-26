#!/usr/bin/env cs_python
"""Real-canary CSL sim runner for the fused_gemv kernel.

Closes the CSL backend lane in `bench/tools/doe_parity.py:_run_csl_simfabric_backend`
for the bootstrap-shape fused_gemv real-canary fixture (W: 4x3 f32,
x: 3 f32, y: 4 f32). Pre-compiled compile-dir lives at
`bench/out/csl-real-canary-compile/fused_gemv/fused_gemv/`; source CSL
at `bench/out/csl-real-canary-source/fused_gemv/`.

Reads the bootstrap input JSON via --inputs (the same fixture
`bench/fixtures/tsir-bootstrap-inputs/fused_gemv.json` that the
WebGPU lane consumes), dispatches the kernel through simfabric via
SdkRuntime, reads back y, hashes its f32 bytes, and writes the hex
digest to --output-hash-out.

Doe_parity.py compares this hash against the Doppler reference
transcript's `kernelProbe.hash` for fused_gemv. The reference output
is computed in source order (k = 0, 1, 2) so the in-order accumulation
in this CSL kernel matches bit-for-bit; algorithm_exact passes.

Usage (via runtime/zig/tools/cs_python_singularity.sh):

  cs_python_singularity.sh fused_gemv_sim_runner.py \\
    --compile-dir bench/out/csl-real-canary-compile/fused_gemv/fused_gemv \\
    --inputs bench/fixtures/tsir-bootstrap-inputs/fused_gemv.json \\
    --output-hash-out <path/to/fused_gemv.csl.hash>
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
    W = np.array(inputs["W"]["values"], dtype=np.float32)
    x = np.array(inputs["x"]["values"], dtype=np.float32)
    if W.size != 12 or x.size != 3:
        sys.stderr.write(
            f"fused_gemv_sim_runner: bootstrap fixture shape mismatch — "
            f"W has {W.size} elements (expected 12), x has {x.size} "
            f"(expected 3)\n"
        )
        return 2

    cmaddr = args.cmaddr.strip() or None
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    W_sym = runner.get_id("W")
    x_sym = runner.get_id("x")
    y_sym = runner.get_id("y")

    runner.load()
    runner.run()

    runner.memcpy_h2d(
        W_sym, W.ravel(), 0, 0, 1, 1, 12,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_h2d(
        x_sym, x, 0, 0, 1, 1, 3,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.launch("compute", nonblock=False)

    y = np.zeros(4, dtype=np.float32)
    runner.memcpy_d2h(
        y, y_sym, 0, 0, 1, 1, 4,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.stop()

    digest = hashlib.sha256(y.tobytes()).hexdigest()
    out_path = Path(args.output_hash_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(digest + "\n", encoding="utf-8")
    print(f"OK {digest} y={y.tolist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
