#!/usr/bin/env cs_python
"""Qwen 3.6 27B sample kernel — simfabric end-to-end run.

Compiles small-shape (width=4, chunk_size=64) version of the
manifest-shape Qwen sample CSL, runs it under simfabric, and
verifies the output token equals np.argmax over the concatenated
logits (greedy sample).

Manifest scale uses the q4k vocab=248320; this small canary
exercises the local-argmax + fabric-reduce-chain mechanism.
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
chunk_size = 128

rng = np.random.default_rng(seed=27)
logits_host = rng.standard_normal(size=(width, chunk_size)).astype(np.float32)
# Greedy argmax over the global concatenated logit vector. With the
# paired value+index reduction landed in emit_csl_sample.zig, the
# kernel correctly propagates both halves through the chain so the
# last PE writes the GLOBAL argmax index regardless of which PE
# chunk the max lives in.
flat = logits_host.ravel()
expected_token = int(np.argmax(flat))

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
logits_sym = runner.get_id("logits")
tokens_sym = runner.get_id("tokens")

runner.load()
runner.run()
runner.memcpy_h2d(
    logits_sym, logits_host.ravel(),
    0, 0, width, 1, chunk_size,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.launch("compute", nonblock=False)
# Sample writes its result on the last PE only — read 1 token from PE (width-1, 0).
token_buf = np.zeros(1, dtype=np.uint32)
runner.memcpy_d2h(
    token_buf, tokens_sym,
    width - 1, 0, 1, 1, 1,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
)
runner.stop()

actual_token = int(token_buf[0])
ok = actual_token == expected_token
print(f"shape: width={width} chunk_size={chunk_size} vocab_total={width*chunk_size}")
print(f"expected_token={expected_token} actual_token={actual_token} parity={'OK' if ok else 'FAIL'}")

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_sample_simfabric_cell",
    "kernel": "sample",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {
        "width": width,
        "chunk_size": chunk_size,
        "vocab_total": width * chunk_size,
    },
    "expectedToken": expected_token,
    "actualToken": actual_token,
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B sample kernel CSL (sourced from the "
            "manifest-shape host plan) compiles via cslc 2.10.0 at "
            f"width={width}, chunk_size={chunk_size} "
            f"(vocab_total={width*chunk_size}) and runs end-to-end "
            "on simfabric. Greedy-sampled token equals np.argmax "
            "over the concatenated host logit vector."
        ),
        "notWhat": (
            "Not a hardware run. Not a manifest-shape run — manifest "
            "vocab is 248320; small canary exercises the local-argmax "
            "+ paired-value-index fabric-reduce-chain mechanism. "
            "Greedy-only (temperature=1.0, no softcap); the kernel "
            "supports both but this canary does not exercise the "
            "temperature or softcap branches. The previous version of "
            "this kernel had an index-reduction emit gap (only value "
            "was reduced across PEs); fixed in emit_csl_sample.zig "
            "by switching to a 2-element scratch buffer that carries "
            "(max_val, @bitcast(f32, max_idx)) through the chain."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
