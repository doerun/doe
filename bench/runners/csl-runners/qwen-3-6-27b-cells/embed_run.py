#!/usr/bin/env cs_python
"""Qwen 3.6 27B embed kernel — simfabric end-to-end run.

Compiles small-shape (width=2, height=1, hidden_size=16,
hidden_per_pe=16, rows_per_pe=8, num_tokens=2, tokens_per_chunk=2)
version of the manifest-shape Qwen embed CSL, runs it under
simfabric, and verifies the gather result equals
table[indices, :hidden_per_pe].

Manifest scale: vocab=248320, hidden=5120 — sharded across the PE
grid via host-orchestrated chunked dispatch. This canary covers
the per-PE row-ownership branch (`token_id ∈ [row_start, row_end)`)
and the local table-lookup write into the output buffer. Other PEs
that don't own the token leave their output untouched (zero).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)

parser = argparse.ArgumentParser()
parser.add_argument("--name", default="compiled")
parser.add_argument("--cmaddr", default=None)
parser.add_argument("--out-receipt", default="receipt.json")
args = parser.parse_args()

width = 2
height = 1
hidden_size = 16
hidden_per_pe = 16
rows_per_pe = 8
num_tokens = 2
tokens_per_chunk = 2
total_rows = width * height * rows_per_pe  # 16 (the small "vocab")

rng = np.random.default_rng(seed=27)
table_full = rng.standard_normal(size=(total_rows, hidden_per_pe)).astype(np.float32)
# Each PE holds rows_per_pe consecutive rows. Layout in PE memory:
# [rows_per_pe * hidden_per_pe]f32 in row-major.
table_per_pe = table_full.reshape(width * height, rows_per_pe, hidden_per_pe)

# Pick token IDs: one in PE 0's row range, one in PE 1's.
indices_host = np.array([3, 11], dtype=np.uint32)
assert indices_host[0] // rows_per_pe == 0
assert indices_host[1] // rows_per_pe == 1

# Reference: per-PE output is non-zero only at the slot that PE owns.
expected_output = np.zeros((width * height, tokens_per_chunk, hidden_per_pe), dtype=np.float32)
for pe in range(width * height):
    row_start = pe * rows_per_pe
    row_end = row_start + rows_per_pe
    for t, token_id in enumerate(indices_host):
        if row_start <= token_id < row_end:
            local_row = int(token_id) - row_start
            expected_output[pe, t] = table_per_pe[pe, local_row]

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
indices_sym = runner.get_id("indices")
table_sym = runner.get_id("table")
output_sym = runner.get_id("output")

runner.load()
runner.run()

# Broadcast same indices to every PE.
indices_broadcast = np.tile(indices_host, width * height).astype(np.uint32)
runner.memcpy_h2d(indices_sym, indices_broadcast, 0, 0, width, height, tokens_per_chunk,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.memcpy_h2d(table_sym, table_per_pe.ravel(), 0, 0, width, height, rows_per_pe * hidden_per_pe,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.launch("compute", nonblock=False)

actual_flat = np.zeros(width * height * tokens_per_chunk * hidden_per_pe, dtype=np.float32)
runner.memcpy_d2h(actual_flat, output_sym, 0, 0, width, height, tokens_per_chunk * hidden_per_pe,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.stop()

actual = actual_flat.reshape(width * height, tokens_per_chunk, hidden_per_pe)
max_abs = float(np.max(np.abs(actual - expected_output)))
ok = bool(np.allclose(actual, expected_output))
print(f"shape: width={width} height={height} hidden_per_pe={hidden_per_pe} "
      f"rows_per_pe={rows_per_pe} tokens_per_chunk={tokens_per_chunk} "
      f"vocab={total_rows}")
print(f"indices={indices_host.tolist()} max_abs_diff={max_abs:.6e} "
      f"parity={'OK' if ok else 'FAIL'}")

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_embed_simfabric_cell",
    "kernel": "embed",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {
        "width": width, "height": height,
        "hidden_size": hidden_size, "hidden_per_pe": hidden_per_pe,
        "rows_per_pe": rows_per_pe,
        "num_tokens": num_tokens, "tokens_per_chunk": tokens_per_chunk,
        "vocab": total_rows,
    },
    "parityMaxAbsDiff": max_abs,
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B embed kernel CSL (sourced from the manifest-"
            "shape host plan) compiles via cslc 2.10.0 at "
            f"width={width}, height={height}, hidden_per_pe={hidden_per_pe}, "
            f"rows_per_pe={rows_per_pe} (vocab={total_rows}) and runs "
            "end-to-end on simfabric. Output gather equals "
            "table[indices, :hidden_per_pe] for the PE that owns each "
            "token; non-owning PEs leave their output buffer at zero."
        ),
        "notWhat": (
            "Not a hardware run. Not a manifest-shape run — manifest "
            "vocab=248320, hidden=5120, sharded across the full grid. "
            "Single-chunk canary (tokens_per_chunk=num_tokens=2); "
            "host-orchestrated multi-chunk dispatch is exercised by "
            "larger lane configurations. No hidden-axis sharding "
            "(hidden_per_pe == hidden_size); the 2-D shard's hidden-"
            "axis path is exercised separately."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
