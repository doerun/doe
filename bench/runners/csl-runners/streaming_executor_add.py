#!/usr/bin/env cs_python
"""SdkLayout streaming executor — elementwise-add (two input streams).

Third hand-ported kernel in the SdkLayout form (after stream_double
and stream_sigmoid). First with TWO host-to-PE input streams — proves
the streaming executor can feed multiple fabric inputs into a single
compute region, which is the primitive every multi-operand kernel
(matmul, attention Q·K^T, residual add) needs.

Semantically equivalent to
    bench/out/dual-compile-evidence/elementwise-add/source.wgsl
(WGSL `out[idx] = a[idx] + b[idx]`).

Topology: rx_a from Edge.LEFT, rx_b from Edge.TOP, tx to Edge.RIGHT.
One 1x1 code region running stream_add.csl. Three tasks:
  main -> got_b -> done
each doing an async mov32 (or the final sync add+emit).

Widens the WGSL backend equivalence crosswalk's csl-sdklayout column
to 3 bit-exact/bit-close kernels.
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
        default="bench/out/streaming-executor/add-source/stream_add.csl",
    )
    p.add_argument("--region-name", default="stream_add")
    p.add_argument("--size", type=int, default=16)
    p.add_argument("--tolerance", type=float, default=1e-6)
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/add",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/add-trace.json",
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

    rx_a = Color("rx_a")
    rx_b = Color("rx_b")
    tx = Color("tx")

    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])

    region.set_param_all("size", args.size)
    region.set_param_all("rx_a", rx_a)
    region.set_param_all("rx_b", rx_b)
    region.set_param_all("tx", tx)

    rx_a_port = region.create_input_port(rx_a, Edge.LEFT, [recv], args.size)
    rx_b_port = region.create_input_port(rx_b, Edge.TOP, [recv], args.size)
    tx_port   = region.create_output_port(tx, Edge.RIGHT, [send], args.size)

    region.place(4, 2)

    in_a_stream = layout.create_input_stream(rx_a_port)
    in_b_stream = layout.create_input_stream(rx_b_port)
    out_stream  = layout.create_output_stream(tx_port)

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

        rng = np.random.default_rng(seed=191)
        sent_a = rng.standard_normal(size=args.size, dtype=np.float32)
        sent_b = rng.standard_normal(size=args.size, dtype=np.float32)
        expected = sent_a + sent_b
        received = np.empty(args.size, dtype=np.float32)
        runtime.send(in_a_stream, sent_a, nonblock=True)
        runtime.send(in_b_stream, sent_b, nonblock=True)
        runtime.receive(out_stream, received, args.size, nonblock=True)
        runtime.stop()

        max_abs_err = float(np.max(np.abs(received - expected)))
        passed = max_abs_err <= args.tolerance
        run_status = "succeeded" if passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:{type(exc).__name__}:{str(exc)[:160]}"
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    observed_bytes = args.size * 4 * 3  # 2 sends + 1 receive, all f32

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "elementwise-add",
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
            {"role": "input",  "color": "rx_a", "size": args.size, "dtype": "float32"},
            {"role": "input",  "color": "rx_b", "size": args.size, "dtype": "float32"},
            {"role": "output", "color": "tx",   "size": args.size, "dtype": "float32"},
        ],
        "notes": (
            "Hand-ported elementwise-add. Three-task async chain "
            "(main -> got_b -> done) pulls both fabric inputs into "
            "PE-local buffers, then performs per-element f32 add and "
            "emits through fabric output. First SdkLayout kernel with "
            "multiple input streams — the primitive every matmul / "
            "attention / residual-add needs."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(
        f"executor add: compile={compile_elapsed_ms:.1f}ms, "
        f"run={run_elapsed_ms:.1f}ms, run_status={run_status!r}, "
        f"passed={passed}, max_abs_err={max_abs_err:.3e} -> {trace_path}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
