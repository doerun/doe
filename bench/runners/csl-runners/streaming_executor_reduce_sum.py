#!/usr/bin/env cs_python
"""SdkLayout streaming executor — blocked reduce-sum.

Fifth hand-ported kernel into the SdkLayout form. First kernel where
the output stream size differs from the input stream size — input is
`input_size` f32s, output is `input_size / block_size` f32s, each the
sum of its block. Models the per-workgroup reduction in the WGSL
reduce-sum-workgroup kernel.

Bit-close tolerance: f32 sum over 16 elements has unavoidable rounding,
but maxAbsErr should be well within 1e-5 relative.

Widens the WGSL backend equivalence crosswalk's csl-sdklayout column
from 4 to 5 kernels, and closes the reduce-sum-workgroup gap that
existed in the crosswalk (previously csl-memcpy only).
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
        default="bench/out/streaming-executor/reduce-source/stream_reduce_sum.csl",
    )
    p.add_argument("--region-name", default="stream_reduce_sum")
    p.add_argument("--input-size", type=int, default=256)
    p.add_argument("--block-size", type=int, default=16)
    p.add_argument("--tolerance", type=float, default=1e-4)
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/reduce",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/reduce-trace.json",
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

    if args.input_size % args.block_size != 0:
        raise SystemExit("input_size must be a multiple of block_size")
    output_size = args.input_size // args.block_size

    compile_start = time.time()
    config = SimfabConfig(dump_core=False)
    target = SdkTarget.WSE3
    platform = get_platform(args.cmaddr.strip(), config, target)
    layout = SdkLayout(platform)

    region = layout.create_code_region(
        str(kernel_source_path), args.region_name, 1, 1
    )
    rx = Color("rx")
    tx = Color("tx")
    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])

    region.set_param_all("input_size", args.input_size)
    region.set_param_all("output_size", output_size)
    region.set_param_all("block_size", args.block_size)
    region.set_param_all(rx)
    region.set_param_all(tx)

    rx_port = region.create_input_port(rx, Edge.LEFT, [recv], args.input_size)
    tx_port = region.create_output_port(tx, Edge.RIGHT, [send], output_size)
    region.place(4, 1)

    in_stream = layout.create_input_stream(rx_port)
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

        rng = np.random.default_rng(seed=211)
        sent = rng.standard_normal(size=args.input_size, dtype=np.float32)
        expected = sent.reshape(output_size, args.block_size).sum(axis=1)
        received = np.empty(output_size, dtype=np.float32)
        runtime.send(in_stream, sent, nonblock=True)
        runtime.receive(out_stream, received, output_size, nonblock=True)
        runtime.stop()

        max_abs_err = float(np.max(np.abs(received - expected)))
        passed = max_abs_err <= args.tolerance
        run_status = "succeeded" if passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:{type(exc).__name__}:{str(exc)[:160]}"
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    observed_bytes = args.input_size * 4 + output_size * 4

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "reduce-sum-workgroup",
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
                "atol": args.tolerance,
                "passed": passed,
            },
        },
        "streams": [
            {"role": "input",  "color": "rx", "size": args.input_size, "dtype": "float32"},
            {"role": "output", "color": "tx", "size": output_size,      "dtype": "float32"},
        ],
        "notes": (
            f"Hand-ported blocked reduce-sum (input_size={args.input_size}, "
            f"block_size={args.block_size}, output_size={output_size}). First "
            f"SdkLayout kernel with asymmetric input/output stream sizes. "
            f"Models per-workgroup reduction; tolerance reflects unavoidable "
            f"f32 summation rounding."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(
        f"executor reduce-sum: compile={compile_elapsed_ms:.1f}ms, "
        f"run={run_elapsed_ms:.1f}ms, in={args.input_size}, out={output_size}, "
        f"run_status={run_status!r}, passed={passed}, "
        f"max_abs_err={max_abs_err:.3e} -> {trace_path}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
