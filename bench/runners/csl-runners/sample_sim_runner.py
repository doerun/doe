#!/usr/bin/env cs_python
"""Governed-lane runner for the sample kernel (greedy argmax, host-side reduce).

Each PE holds a chunk_size slice of the logits vector and produces
(local_max_val, local_max_idx) for that slice. The host collects all
per-PE pairs and computes the final token = argmax across PEs.
Numerical reference applies the same tanh-softcap-then-temperature
pre-processing the kernel does and verifies the kernel's chosen token
matches numpy's argmax bit-for-bit.
"""

from __future__ import annotations

import sys

import numpy as np

import common

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)


def main() -> int:
    args = common.parse_runtime_args(__doc__ or "")

    width = 4
    chunk_size = 1024
    vocab_size = width * chunk_size
    temperature = 1.0
    softcap = 0.0

    rng = np.random.default_rng(seed=23)
    logits = rng.standard_normal(size=(width, chunk_size), dtype=np.float32)

    processed = logits.copy()
    if softcap != 0.0:
        processed = softcap * np.tanh(processed / softcap)
    processed = processed / temperature
    expected_token = int(np.argmax(processed.ravel()))
    expected_val = float(np.max(processed))

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    logits_sym = runner.get_id("logits")
    vals_sym = runner.get_id("local_max_val")
    idxs_sym = runner.get_id("local_max_idx")
    runner.load()
    runner.run()

    runner.memcpy_h2d(logits_sym, logits.ravel(), 0, 0, width, 1, chunk_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)

    local_vals = np.zeros(width, dtype=np.float32)
    local_idxs = np.zeros(width, dtype=np.uint32)
    runner.memcpy_d2h(local_vals, vals_sym, 0, 0, width, 1, 1,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_d2h(local_idxs, idxs_sym, 0, 0, width, 1, 1,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    winning_pe = int(np.argmax(local_vals))
    actual_token = int(local_idxs[winning_pe])
    actual_val = float(local_vals[winning_pe])

    val_err = abs(actual_val - expected_val)
    token_matches = actual_token == expected_token

    if not token_matches:
        print(f"FAIL: token mismatch — expected={expected_token}, actual={actual_token}")
        print(f"  expected_val={expected_val:.6f} actual_val={actual_val:.6f}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="sample",
        cmaddr=cmaddr,
        width=width,
        chunk_size=chunk_size,
        total_elements=vocab_size,
        max_abs_err=val_err,
        sample_input=logits[0, :4].tolist(),
        sample_expected=[float(expected_token)],
        sample_actual=[float(actual_token)],
    )
    print(f"PASS: sample vocab={vocab_size} token={actual_token} "
          f"(matched numpy argmax, val_err={val_err:.3e}), trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
