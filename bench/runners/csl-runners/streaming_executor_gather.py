#!/usr/bin/env cs_python
"""SdkLayout streaming executor — gather (embedding lookup).

Fourth hand-ported kernel into the SdkLayout form (after stream_double,
stream_sigmoid, stream_add). First kernel that models a table lookup
(`output[i] = table[indices[i]]`), which is the first op in every
transformer forward pass (token id -> embedding row).

Two input streams:
  rx_table: f32 table, table_size entries
  rx_idx:   u32 indices, size entries
One output stream:
  tx: f32 gathered rows, size entries

Semantically equivalent to
    bench/out/dual-compile-evidence/gather/source.wgsl
(WGSL gather by global_invocation_id.x).

Widens the WGSL backend equivalence crosswalk's csl-sdklayout column
from 3 to 4 kernels.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    Color,
    Edge,
    Route,
    RoutingPosition,
    SdkLayout,
    SdkRuntime,
    SdkTarget,
    SimfabConfig,
    get_platform,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--kernel-source",
        default="bench/out/streaming-executor/gather-source/stream_gather.csl",
    )
    p.add_argument("--region-name", default="stream_gather")
    p.add_argument("--size", type=int, default=4)
    p.add_argument("--table-size", type=int, default=16)
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/gather",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/gather-trace.json",
    )
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else REPO_ROOT / p


def main() -> int:
    args = parse_args()
    kernel_source_path = resolve(args.kernel_source)
    compile_out = resolve(args.compile_out)
    compile_out.mkdir(parents=True, exist_ok=True)

    compile_start = time.time()
    config = SimfabConfig(dump_core=False)
    target = SdkTarget.WSE3
    platform = get_platform(args.cmaddr.strip(), config, target)
    layout = SdkLayout(platform)

    region = layout.create_code_region(
        str(kernel_source_path), args.region_name, 1, 1
    )

    rx_table = Color("rx_table")
    rx_idx = Color("rx_idx")
    tx = Color("tx")

    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])

    region.set_param_all("size", args.size)
    region.set_param_all("table_size", args.table_size)
    region.set_param_all("rx_table", rx_table)
    region.set_param_all("rx_idx", rx_idx)
    region.set_param_all("tx", tx)

    table_port = region.create_input_port(rx_table, Edge.LEFT, [recv], args.table_size)
    idx_port = region.create_input_port(rx_idx, Edge.TOP, [recv], args.size)
    tx_port = region.create_output_port(tx, Edge.RIGHT, [send], args.size)

    region.place(4, 2)

    table_stream = layout.create_input_stream(table_port)
    idx_stream = layout.create_input_stream(idx_port)
    out_stream = layout.create_output_stream(tx_port)

    compile_prefix = str(compile_out / args.region_name)
    compile_artifacts = layout.compile(out_prefix=compile_prefix)
    compile_elapsed_ms = (time.time() - compile_start) * 1000.0

    run_start = time.time()
    runtime = SdkRuntime(compile_artifacts, platform, memcpy_required=False)
    max_abs_err = -1.0
    passed = False
    try:
        runtime.load()
        runtime.run()

        rng = np.random.default_rng(seed=197)
        table = rng.standard_normal(size=args.table_size, dtype=np.float32)
        indices = rng.integers(0, args.table_size, size=args.size, dtype=np.uint32)
        expected = table[indices]
        received = np.empty(args.size, dtype=np.float32)

        runtime.send(table_stream, table, nonblock=True)
        runtime.send(idx_stream, indices, nonblock=True)
        runtime.receive(out_stream, received, args.size, nonblock=True)
        runtime.stop()

        max_abs_err = float(np.max(np.abs(received - expected)))
        passed = bool(np.array_equal(received, expected))
        run_status = "succeeded" if passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:{type(exc).__name__}:{str(exc)[:160]}"
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    observed_bytes = args.table_size * 4 + args.size * 4 * 2

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "gather",
        "executorIteration": 3,
        "sourcePlan": {
            "streamGraphPath": "",
            "executionPlanPath": "",
            "kernelSourcePath": str(kernel_source_path.relative_to(REPO_ROOT)),
        },
        "region": {
            "regionId": args.region_name,
            "width": 1,
            "height": 1,
            "peCount": 1,
        },
        "executedCompile": {
            "compilePrefix": str(Path(compile_prefix).relative_to(REPO_ROOT)),
            "elapsedMs": compile_elapsed_ms,
            "status": "succeeded",
        },
        "executedRun": {
            "status": run_status,
            "elapsedMs": run_elapsed_ms,
            "observedBytesTransferredPerPe": observed_bytes,
            "observedBytesTransferredTotal": observed_bytes,
            "numericalParity": {
                "maxAbsErr": max_abs_err,
                "atol": 0,
                "passed": passed,
            },
        },
        "streams": [
            {"role": "input",  "color": "rx_table", "size": args.table_size, "dtype": "float32"},
            {"role": "input",  "color": "rx_idx",   "size": args.size,       "dtype": "uint32"},
            {"role": "output", "color": "tx",       "size": args.size,       "dtype": "float32"},
        ],
        "notes": (
            "Hand-ported gather (embedding lookup). Three-task async "
            "chain receives the table and then the indices, then runs "
            "the per-row lookup output[i] = table[indices[i]] and emits. "
            "First SdkLayout kernel that does indexed table lookup — the "
            "first op in every transformer forward pass."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(
        f"executor gather: compile={compile_elapsed_ms:.1f}ms, "
        f"run={run_elapsed_ms:.1f}ms, run_status={run_status!r}, "
        f"passed={passed}, max_abs_err={max_abs_err:.3e} -> {trace_path}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
