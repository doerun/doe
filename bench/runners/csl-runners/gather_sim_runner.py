#!/usr/bin/env cs_python
"""Dual-mode simulator runner for the gather (embedding lookup) kernel.

Two CLI shapes are supported, dispatched by which flags are present:

1. Real-canary mode (used by `bench/tools/doe_parity.py:_run_csl_simfabric_backend`):
     --compile-dir <bench/out/csl-real-canary-compile/gather/gather>
     --inputs <bench/fixtures/tsir-bootstrap-inputs/gather.json>
     --output-hash-out <path/to/gather.csl.hash>
   Loads bootstrap input fixture (indices: [2] u32, table: [3,4] f32),
   memcpy_h2d's both, dispatches the kernel, reads back output ([2,4]
   f32), hashes its f32 bytes, and writes the hex digest. The
   bootstrap-shape PE program lives at
   `bench/out/csl-real-canary-source/gather/`.

2. Governed-lane mode (used by `csl_sdk_driver.run_simulation` with
   substitutions from `config/csl-runtime-fixtures.json`):
     --compile-dir <compile_output_dir>
     --trace-out <trace_path>
     --cmaddr <optional CS endpoint>
   Pre-existing behavior — runs against
   `runtime/zig/examples/simulator/gather-runtime/...` with width=4,
   rows_per_pe=8, hidden_size=64, num_tokens=4 and emits an
   explicit_simulator_trace JSON.

Mode is selected by the presence of `--inputs` (or `--output-hash-out`):
real-canary if present, governed-lane otherwise.
"""

from __future__ import annotations

import sys


def main() -> int:
    if any(flag in sys.argv for flag in ("--inputs", "--output-hash-out")):
        return _real_canary_main()
    return _governed_lane_main()


def _real_canary_main() -> int:
    import argparse
    import hashlib
    import json
    from pathlib import Path

    import numpy as np
    from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
        SdkRuntime,
        MemcpyDataType,
        MemcpyOrder,
    )

    p = argparse.ArgumentParser(description="real-canary gather sim runner")
    p.add_argument("--compile-dir", required=True)
    p.add_argument("--inputs", required=True)
    p.add_argument("--output-hash-out", required=True)
    p.add_argument("--cmaddr", default="")
    args = p.parse_args()

    fixture = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    inputs = fixture["inputs"]
    indices = np.array(inputs["indices"]["values"], dtype=np.uint32)
    table = np.array(inputs["table"]["values"], dtype=np.float32)
    if indices.size != 2 or table.size != 12:
        sys.stderr.write(
            f"gather_sim_runner: bootstrap fixture shape mismatch — "
            f"indices:{indices.size} (want 2), table:{table.size} (want 12)\n"
        )
        return 2

    cmaddr = args.cmaddr.strip() or None
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    indices_sym = runner.get_id("indices")
    table_sym = runner.get_id("table")
    output_sym = runner.get_id("output")

    runner.load()
    runner.run()

    runner.memcpy_h2d(
        indices_sym, indices, 0, 0, 1, 1, 2,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.memcpy_h2d(
        table_sym, table.ravel(), 0, 0, 1, 1, 12,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.launch("compute", nonblock=False)

    output = np.zeros(8, dtype=np.float32)
    runner.memcpy_d2h(
        output, output_sym, 0, 0, 1, 1, 8,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False,
    )
    runner.stop()

    digest = hashlib.sha256(output.tobytes()).hexdigest()
    out_path = Path(args.output_hash_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(digest + "\n", encoding="utf-8")
    print(f"OK {digest} output={output.tolist()}")
    return 0


def _governed_lane_main() -> int:
    import numpy as np
    import common
    from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
        SdkRuntime,
        MemcpyDataType,
        MemcpyOrder,
    )

    args = common.parse_runtime_args(__doc__ or "")

    width = 4
    hidden_size = 64
    rows_per_pe = 8
    num_tokens = 4
    total_rows = width * rows_per_pe

    rng = np.random.default_rng(seed=9)
    table_full = rng.standard_normal(size=(total_rows, hidden_size), dtype=np.float32)
    indices_host = rng.integers(0, total_rows, size=num_tokens, dtype=np.uint32)
    expected = table_full[indices_host]

    indices_flat = np.tile(indices_host, width)
    table_flat = np.zeros(width * rows_per_pe * hidden_size, dtype=np.float32)
    for pe in range(width):
        start = pe * rows_per_pe
        table_flat[pe * rows_per_pe * hidden_size:(pe + 1) * rows_per_pe * hidden_size] = \
            table_full[start:start + rows_per_pe].flatten()

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    idx_sym = runner.get_id("indices")
    tbl_sym = runner.get_id("table")
    out_sym = runner.get_id("output")
    runner.load()
    runner.run()

    runner.memcpy_h2d(idx_sym, indices_flat, 0, 0, width, 1, num_tokens,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(tbl_sym, table_flat, 0, 0, width, 1, rows_per_pe * hidden_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)

    out_flat = np.zeros(width * num_tokens * hidden_size, dtype=np.float32)
    runner.memcpy_d2h(out_flat, out_sym, 0, 0, width, 1, num_tokens * hidden_size,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    out_per_pe = out_flat.reshape(width, num_tokens, hidden_size)
    actual = out_per_pe.sum(axis=0)
    max_abs_err = common.max_abs_error(actual, expected)
    passed = bool(np.allclose(actual, expected, atol=1e-6, rtol=0.0))

    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err:.6f}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="gather",
        cmaddr=cmaddr,
        width=width,
        chunk_size=hidden_size,
        total_elements=num_tokens * hidden_size,
        max_abs_err=max_abs_err,
        sample_input=indices_host.astype(np.float32).tolist(),
        sample_expected=expected[0, :4].tolist(),
        sample_actual=actual[0, :4].tolist(),
    )
    print(f"PASS: {num_tokens} tokens gathered, max_abs_err={max_abs_err:.3e}, trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
