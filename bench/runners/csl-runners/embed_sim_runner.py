#!/usr/bin/env cs_python
"""Real-canary CSL sim runner for the embed kernel.

Closes the CSL backend lane in `bench/tools/doe_parity.py:_run_csl_simfabric_backend`
for the bootstrap-shape embed real-canary fixture (indices: [1] f32,
embeddings: [4] f32 = vocab*hidden = 1*4, output: [4] f32).
Pre-compiled compile-dir lives at
`bench/out/csl-real-canary-compile/embed/embed/`; source CSL at
`bench/out/csl-real-canary-source/embed/`.

The bootstrap fixture is all-zero; the canary verifies that the CSL
emit + dispatch path produces the expected 4-element f32 zero output
matching the Doppler reference probe hash
374708fff7719dd5979ec875d56cd2286f6d3cf7ec317a3b25632aab28ec37bb at
bench/fixtures/tsir-real-doppler-transcripts/embed.doppler-transcript.json.

Usage (via runtime/zig/tools/cs_python_singularity.sh):

  cs_python_singularity.sh embed_sim_runner.py \\
    --compile-dir bench/out/csl-real-canary-compile/embed/embed \\
    --inputs bench/fixtures/tsir-bootstrap-inputs/embed.json \\
    --output-hash-out <path/to/embed.csl.hash>
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
    indices_f32 = np.array(inputs["indices"]["values"], dtype=np.float32)
    embeddings = np.array(inputs["embeddings"]["values"], dtype=np.float32)
    if indices_f32.size != 1 or embeddings.size != 4:
        sys.stderr.write(
            f"embed_sim_runner: bootstrap fixture shape mismatch — "
            f"indices has {indices_f32.size} elements (expected 1), "
            f"embeddings has {embeddings.size} (expected 4)\n"
        )
        return 2
    # Fixture stores indices as f32 with all-zero values; the CSL
    # kernel reads indices as u32. Cast bit-equivalent (0.0 f32 → 0 u32).
    indices = indices_f32.astype(np.uint32)

    cmaddr = args.cmaddr.strip() or None
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    indices_sym = runner.get_id("indices")
    embeddings_sym = runner.get_id("embeddings")
    output_sym = runner.get_id("output")

    runner.load()
    runner.run()

    runner.memcpy_h2d(
        indices_sym, indices, 0, 0, 1, 1, 1,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_h2d(
        embeddings_sym, embeddings, 0, 0, 1, 1, 4,
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
