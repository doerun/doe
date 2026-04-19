#!/usr/bin/env cs_python
"""SdkLayout streaming executor — iteration 4: two-region chain.

Extends iter-3 (1 region, 1 PE, double-by-2.0 through streams) to
**two** 1x1 code regions connected via `layout.connect(A.out, B.in)`.
Region A takes the host input, multiplies by 2.0, and forwards the
result to Region B via the WSE fabric. Region B takes that fabric
input, multiplies by 2.0 again, and sends the final result back to
the host. Host expects `received == sent * 4.0` bit-exact.

This proves the load-bearing piece every composable layer block needs:
one region's output can be piped into another region's input via the
on-wafer fabric without host round-trips. For an E2B layer block this
is how attention → MLP (or RMSNorm → attention) composes: each stage
is its own code region connected via layout.connect.

Both regions reuse the iter-3 stream_double.csl kernel (param rx: color;
param tx: color; two-task async @mov32 + @fmuls x 2.0) — no new CSL.

Kernel: bench/out/streaming-executor/iter3-source/stream_double.csl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    Edge,
    Route,
    RoutingPosition,
    SdkLayout,
    SdkRuntime,
    SdkTarget,
    SimfabConfig,
    get_platform,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--kernel-source",
        default="bench/out/streaming-executor/iter3-source/stream_double.csl",
    )
    p.add_argument("--region-a-name", default="stage_a")
    p.add_argument("--region-b-name", default="stage_b")
    p.add_argument("--size", type=int, default=16)
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/iter4",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/iter4-trace.json",
    )
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


REPO_ROOT = Path(__file__).resolve().parents[3]


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

    receiver_routes = RoutingPosition().set_output([Route.RAMP])
    sender_routes = RoutingPosition().set_input([Route.RAMP])

    # Region A — host input → *2.0 → fabric output (toward region B).
    region_a = layout.create_code_region(
        str(kernel_source_path), args.region_a_name, 1, 1
    )
    rx_a = region_a.color("rx")
    tx_a = region_a.color("tx")
    region_a.set_param_all("size", args.size)
    region_a.set_param_all("rx", rx_a)
    region_a.set_param_all("tx", tx_a)
    rx_a_port = region_a.create_input_port(rx_a, Edge.LEFT, [receiver_routes], args.size)
    tx_a_port = region_a.create_output_port(tx_a, Edge.RIGHT, [sender_routes], args.size)
    region_a.place(4, 1)

    # Region B — fabric input (from region A) → *2.0 → host output.
    region_b = layout.create_code_region(
        str(kernel_source_path), args.region_b_name, 1, 1
    )
    rx_b = region_b.color("rx")
    tx_b = region_b.color("tx")
    region_b.set_param_all("size", args.size)
    region_b.set_param_all("rx", rx_b)
    region_b.set_param_all("tx", tx_b)
    rx_b_port = region_b.create_input_port(rx_b, Edge.LEFT, [receiver_routes], args.size)
    tx_b_port = region_b.create_output_port(tx_b, Edge.RIGHT, [sender_routes], args.size)
    region_b.place(8, 1)

    # Stitch region A's fabric output to region B's fabric input.
    layout.connect(tx_a_port, rx_b_port)

    # Host-facing streams.
    in_stream = layout.create_input_stream(rx_a_port)
    out_stream = layout.create_output_stream(tx_b_port)

    compile_prefix = str(compile_out / "chain")
    compile_artifacts = layout.compile(out_prefix=compile_prefix)
    compile_elapsed_ms = (time.time() - compile_start) * 1000.0

    run_start = time.time()
    runtime = SdkRuntime(compile_artifacts, platform, memcpy_required=False)
    max_abs_err = -1.0
    passed = False
    try:
        runtime.load()
        runtime.run()

        rng = np.random.default_rng(seed=151)
        sent = rng.standard_normal(size=args.size, dtype=np.float32)
        # Each region multiplies by 2.0, so after A+B we expect *4.0.
        expected = sent * 4.0
        received = np.empty(args.size, dtype=np.float32)
        runtime.send(in_stream, sent, nonblock=True)
        runtime.receive(out_stream, received, args.size, nonblock=True)
        runtime.stop()

        max_abs_err = float(np.max(np.abs(received - expected)))
        passed = bool(np.array_equal(received, expected))
        run_status = "succeeded" if passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:{type(exc).__name__}:{str(exc)[:160]}"
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    observed_bytes = args.size * 4 * 2  # f32 send + f32 receive

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "",
        "executorIteration": 4,
        "sourcePlan": {
            "streamGraphPath": "",
            "executionPlanPath": "",
            "kernelSourcePath": str(kernel_source_path.relative_to(REPO_ROOT)),
        },
        "region": {
            "regionId": f"{args.region_a_name}+{args.region_b_name}",
            "width": 1,
            "height": 1,
            "peCount": 2,
        },
        "executedCompile": {
            "compilePrefix": str(Path(compile_prefix).relative_to(REPO_ROOT)),
            "elapsedMs": compile_elapsed_ms,
            "status": "succeeded",
        },
        "executedRun": {
            "status": run_status,
            "elapsedMs": run_elapsed_ms,
            "observedBytesTransferredPerPe": args.size * 4 * 2,
            "observedBytesTransferredTotal": observed_bytes,
            "numericalParity": {
                "maxAbsErr": max_abs_err,
                "atol": 0,
                "passed": passed,
            },
        },
        "streams": [
            {"role": "input",  "color": "rx_a", "size": args.size, "dtype": "float32"},
            {"role": "output", "color": "tx_b", "size": args.size, "dtype": "float32"},
        ],
        "notes": (
            "Iter-4 — region-to-region chain via layout.connect. Two 1x1 "
            "code regions each run the iter-3 stream_double kernel; region "
            "A's fabric output (color tx_a) is connected to region B's "
            "fabric input (color rx_b). Host expects received == sent * 4.0. "
            "Proves on-wafer region composition — the primitive every "
            "multi-stage layer block needs (e.g. RMSNorm -> attention, "
            "attention -> MLP)."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(f"executor iter-4: compile {compile_elapsed_ms:.1f} ms, "
          f"run {run_elapsed_ms:.1f} ms, regions=2x(1x1), chain=A->B, "
          f"size={args.size}, run_status={run_status!r}, "
          f"passed={passed}, max_abs_err={max_abs_err} → {trace_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
