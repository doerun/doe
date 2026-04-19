#!/usr/bin/env cs_python
"""SdkLayout streaming executor — elementwise sigmoid.

Second hand-ported kernel into the SdkLayout form (after
stream_double in iter-3). Semantically equivalent to the WGSL source
`bench/out/dual-compile-evidence/elementwise-sigmoid/source.wgsl`
(output[i] = 1/(1+exp(-input[i]))) but wired through the fabric I/O
contract used by the streaming executor.

Widens the `csl-sdklayout` column in the WGSL backend equivalence
crosswalk from 1 kernel (elementwise-double) to 2. When
bench/tools/generate_wgsl_backend_equivalence.py sees this trace,
sigmoid's sdklayout entry is upgraded from not_yet_ported to
executionProven with bit-close tolerance (sigmoid has unavoidable
f32 rounding from exp).
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
        default="bench/out/streaming-executor/sigmoid-source/stream_sigmoid.csl",
    )
    p.add_argument("--region-name", default="stream_sigmoid")
    p.add_argument("--size", type=int, default=16)
    p.add_argument("--tolerance", type=float, default=1e-6)
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/sigmoid",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/sigmoid-trace.json",
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
    rx = Color("rx")
    tx = Color("tx")
    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])
    region.set_param_all("size", args.size)
    region.set_param_all(rx)
    region.set_param_all(tx)
    rx_port = region.create_input_port(rx, Edge.LEFT, [recv], args.size)
    tx_port = region.create_output_port(tx, Edge.RIGHT, [send], args.size)
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

        rng = np.random.default_rng(seed=179)
        sent = rng.standard_normal(size=args.size, dtype=np.float32)
        expected = 1.0 / (1.0 + np.exp(-sent.astype(np.float64))).astype(np.float32)
        received = np.empty(args.size, dtype=np.float32)
        runtime.send(in_stream, sent, nonblock=True)
        runtime.receive(out_stream, received, args.size, nonblock=True)
        runtime.stop()

        max_abs_err = float(np.max(np.abs(received - expected)))
        passed = max_abs_err <= args.tolerance
        run_status = "succeeded" if passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:{type(exc).__name__}:{str(exc)[:160]}"
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    observed_bytes = args.size * 4 * 2

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "elementwise-sigmoid",
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
            {"role": "input",  "color": "rx", "size": args.size, "dtype": "float32"},
            {"role": "output", "color": "tx", "size": args.size, "dtype": "float32"},
        ],
        "notes": (
            "Hand-ported elementwise-sigmoid for the SdkLayout streaming "
            "executor. Same 1x1 region shape and two-task async pattern "
            "as iter-3, but the done task runs a per-element sigmoid "
            "loop (1/(1+exp(-x))) via CSL's <math> module. Feeds the "
            "WGSL backend equivalence crosswalk."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(
        f"executor sigmoid: compile={compile_elapsed_ms:.1f}ms, "
        f"run={run_elapsed_ms:.1f}ms, run_status={run_status!r}, "
        f"passed={passed}, max_abs_err={max_abs_err:.3e} -> {trace_path}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
