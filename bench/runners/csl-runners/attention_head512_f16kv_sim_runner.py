#!/usr/bin/env cs_python
"""Real-canary CSL sim runner for the attention_head512_f16kv kernel.

Closes the CSL backend lane in `bench/tools/doe_parity.py:_run_csl_simfabric_backend`
for the bootstrap-shape attention_head512_f16kv real-canary fixture
(Q/K/V: [256] f32, u: [15] f32, kv_len_buffer/page_table: [1] f32,
output: [256] f32). Pre-compiled compile-dir lives at
`bench/out/csl-real-canary-compile/attention_head512_f16kv/attention_head512_f16kv/`;
source CSL at `bench/out/csl-real-canary-source/attention_head512_f16kv/`.

The bootstrap fixture has all-zero inputs; the canary verifies the
CSL emit + dispatch path produces the expected 512-element f32
zero output matching the Doppler reference probe hash
sha256 e5a00aa9991ac8a5ee3109844d84a55583bd20572ad3ffcd42792f3c36b183ad
at bench/fixtures/tsir-real-doppler-transcripts/attention_head512_f16kv.doppler-transcript.json.

The TSIR `attention_scores` body op is unimplemented in
emit_kernel_body.zig; this hand-authored CSL closes the canary lane
without adding TSIR-CSL emit-time support. Manifest-shape attention
remains the open lane.

Usage (via runtime/zig/tools/cs_python_singularity.sh):

  cs_python_singularity.sh attention_head512_f16kv_sim_runner.py \\
    --compile-dir bench/out/csl-real-canary-compile/attention_head512_f16kv/attention_head512_f16kv \\
    --inputs bench/fixtures/tsir-bootstrap-inputs/attention_head512_f16kv.json \\
    --output-hash-out <path/to/attention_head512_f16kv.csl.hash>
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


HEAD_DIM = 512
U_LEN = 15


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
    u = np.array(inputs["u"]["values"], dtype=np.float32)
    Q = np.array(inputs["Q"]["values"], dtype=np.float32)
    K = np.array(inputs["K"]["values"], dtype=np.float32)
    V = np.array(inputs["V"]["values"], dtype=np.float32)
    kv_len_buffer = np.array(inputs["kv_len_buffer"]["values"], dtype=np.float32)
    page_table = np.array(inputs["page_table"]["values"], dtype=np.float32)
    if u.size != U_LEN or Q.size != HEAD_DIM or K.size != HEAD_DIM or V.size != HEAD_DIM:
        sys.stderr.write(
            f"attention_head512_f16kv_sim_runner: bootstrap fixture shape "
            f"mismatch — u:{u.size} Q:{Q.size} K:{K.size} V:{V.size}\n"
        )
        return 2

    cmaddr = args.cmaddr.strip() or None
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    u_sym = runner.get_id("u")
    Q_sym = runner.get_id("Q")
    K_sym = runner.get_id("K")
    V_sym = runner.get_id("V")
    kv_len_sym = runner.get_id("kv_len_buffer")
    page_table_sym = runner.get_id("page_table")
    output_sym = runner.get_id("output")

    runner.load()
    runner.run()

    def h2d(sym, arr, count):
        runner.memcpy_h2d(
            sym, arr, 0, 0, 1, 1, count,
            streaming=False,
            order=MemcpyOrder.ROW_MAJOR,
            data_type=MemcpyDataType.MEMCPY_32BIT,
            nonblock=False,
        )

    h2d(u_sym, u, U_LEN)
    h2d(Q_sym, Q, HEAD_DIM)
    h2d(K_sym, K, HEAD_DIM)
    h2d(V_sym, V, HEAD_DIM)
    h2d(kv_len_sym, kv_len_buffer, 1)
    h2d(page_table_sym, page_table, 1)
    runner.launch("compute", nonblock=False)

    output = np.zeros(HEAD_DIM, dtype=np.float32)
    runner.memcpy_d2h(
        output, output_sym, 0, 0, 1, 1, HEAD_DIM,
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
    print(f"OK {digest} output_first8={output[:8].tolist()} all_zero={bool(np.all(output == 0))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
