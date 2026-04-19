#!/usr/bin/env cs_python
"""SdkLayout streaming executor — iteration 5: multi-PE single region SPMD.

Extends iter-4 (two 1x1 regions chained via layout.connect) to a
genuine multi-PE SPMD compute region, using the demux/mux adaptor
pattern from the Cerebras SDK's sdklayout-05-gemv tutorial. This is
the pattern every hidden-dim-parallel layer block needs: one host
stream → demuxed across W PEs → SPMD compute → muxed back into one
host stream.

Layout:
  demux_adaptor (1x1)  →  demux (Wx1)  →  compute (Wx1)  →  mux (1xW)  →  host

- demux_adaptor: 1-PE, receives the host input stream, forwards each
  batch of `per_pe_size` wavelets to the demux layer with a switch-
  advance control wavelet between batches.
- demux: Wx1 horizontal, forwards batch i to compute-PE i via the
  WSE's per-PE routing switch.
- compute: Wx1 SPMD, each PE reads its `per_pe_size` f32 values from
  the fabric, multiplies by 2.0, emits to the fabric.
- mux: 1xW vertical, collects per-PE outputs and funnels them into a
  single stream whose 1-PE top port feeds back to the host.

Kernel files (under bench/out/streaming-executor/iter5-source/):
  demux_adaptor.csl, demux.csl, compute_double.csl, mux.csl

demux_adaptor.csl / demux.csl / mux.csl are copied verbatim from the
sdklayout-05-gemv tutorial; compute_double.csl is the iter-3 kernel.
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
    get_edge_routing,
    get_platform,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "bench/out/streaming-executor/iter5-source"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--per-pe-size", type=int, default=8)
    p.add_argument("--pe-width", type=int, default=2)
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/iter5",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/iter5-trace.json",
    )
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else REPO_ROOT / p


def get_demux_adaptor(layout, name, batch_size, num_batches):
    region = layout.create_code_region(str(SRC_DIR / "demux_adaptor.csl"), name, 1, 1)
    region.set_param_all("batch_size", batch_size)
    region.set_param_all("num_batches", num_batches)
    in_color = region.color("in_color")
    out_color = region.color("out_color")
    region.set_param_all(in_color)
    region.set_param_all(out_color)
    input_routes = RoutingPosition().set_output([Route.RAMP])
    output_routes = RoutingPosition().set_input([Route.RAMP])
    size = batch_size * num_batches
    in_port = region.create_input_port(in_color, Edge.LEFT, [input_routes], size)
    out_port = region.create_output_port(out_color, Edge.RIGHT, [output_routes], size)
    return in_port, out_port, region


def get_x_demux(layout, name, batch_size, width):
    # Matches sdklayout-05-gemv's get_x_demux with has_sentinel=0.
    region = layout.create_code_region(str(SRC_DIR / "demux.csl"), name, width, 1)
    region.set_param_all("size", batch_size)
    region.set_param_all("has_sentinel", 0)
    region.set_param_all("entry_point", 0)
    in_color = region.color("in_color")
    out_color = region.color("out_color")
    region.set_param_all(in_color)
    region.set_param_all(out_color)
    pos1 = RoutingPosition().set_input([Route.WEST]).set_output([Route.RAMP])
    pos2 = RoutingPosition().set_input([Route.WEST]).set_output([Route.EAST])
    edge_route = get_edge_routing(Edge.RIGHT, [pos1])
    region.paint_all(in_color, [pos1, pos2], [edge_route])
    input_routes = RoutingPosition().set_output([Route.RAMP])
    output_routes = RoutingPosition().set_input([Route.RAMP])
    size = batch_size * width
    forward = RoutingPosition().set_output([Route.EAST])
    in_port = region.create_input_port(in_color, Edge.LEFT, [input_routes, forward], size)
    out_port = region.create_output_port(out_color, Edge.BOTTOM, [output_routes], size)
    return in_port, out_port, region


def get_compute(layout, name, batch_size, width):
    region = layout.create_code_region(str(SRC_DIR / "compute_double.csl"), name, width, 1)
    region.set_param_all("size", batch_size)
    rx = Color("compute_rx")
    tx = Color("compute_tx")
    region.set_param_all("rx", rx)
    region.set_param_all("tx", tx)
    # rx enters from the north (fed by demux below compute? No — demux is
    # to the left of compute, but demux's out_port is Edge.BOTTOM, so
    # demux sits above compute and the connection comes from NORTH).
    rx_core = RoutingPosition().set_input([Route.NORTH]).set_output([Route.RAMP])
    tx_core = RoutingPosition().set_input([Route.RAMP]).set_output([Route.SOUTH])
    region.paint_all(rx, [rx_core])
    region.paint_all(tx, [tx_core])
    rx_port = region.create_input_port(
        rx, Edge.TOP, [RoutingPosition().set_output([Route.RAMP])], batch_size * width
    )
    tx_port = region.create_output_port(
        tx, Edge.BOTTOM, [RoutingPosition().set_input([Route.RAMP])], batch_size * width
    )
    return rx_port, tx_port, region


def get_mux(layout, name, batch_size, height):
    region = layout.create_code_region(str(SRC_DIR / "mux.csl"), name, 1, height)
    region.set_param_all("size", batch_size)
    in_color = region.color("in_color")
    out_color = region.color("out_color")
    region.set_param_all(in_color)
    region.set_param_all(out_color)
    core_out = RoutingPosition().set_input([Route.RAMP]).set_output([Route.NORTH])
    forward = RoutingPosition().set_input([Route.SOUTH]).set_output([Route.NORTH])
    region.paint_all(out_color, [core_out, forward])
    input_routes = RoutingPosition().set_output([Route.RAMP])
    output_routes = RoutingPosition().set_input([Route.RAMP])
    forward_port_routes = RoutingPosition().set_input([Route.SOUTH])
    size = batch_size * height
    in_port = region.create_input_port(in_color, Edge.LEFT, [input_routes], size)
    out_port = region.create_output_port(
        out_color, Edge.TOP, [output_routes, forward_port_routes], size
    )
    return in_port, out_port, region


def main() -> int:
    args = parse_args()

    per_pe = args.per_pe_size
    W = args.pe_width
    total = per_pe * W

    compile_out = resolve(args.compile_out)
    compile_out.mkdir(parents=True, exist_ok=True)

    compile_start = time.time()
    config = SimfabConfig(dump_core=False)
    target = SdkTarget.WSE3
    platform = get_platform(args.cmaddr.strip(), config, target)
    layout = SdkLayout(platform)

    # Adaptor → demux → compute → mux.
    adaptor_in, adaptor_out, adaptor = get_demux_adaptor(layout, "adaptor", per_pe, W)
    demux_in, demux_out, demux = get_x_demux(layout, "demux_x", per_pe, W)
    compute_in, compute_out, compute = get_compute(layout, "compute", per_pe, W)
    mux_in, mux_out, mux = get_mux(layout, "mux_y", per_pe, W)

    adaptor.place(1, 2)
    demux.place(3, 0)     # above compute so its Edge.BOTTOM feeds compute's Edge.TOP via connect
    compute.place(3, 2)
    mux.place(3 + W + 1, 0)  # to the right of compute; its own height=W

    # Stitch: adaptor.out → demux.in, demux.out → compute.in (top), compute.out → mux.in.
    layout.connect(adaptor_out, demux_in)
    layout.connect(demux_out, compute_in)
    layout.connect(compute_out, mux_in)

    in_stream = layout.create_input_stream(adaptor_in)
    out_stream = layout.create_output_stream(mux_out)

    compile_prefix = str(compile_out / "multi_pe_spmd")
    compile_artifacts = layout.compile(out_prefix=compile_prefix)
    compile_elapsed_ms = (time.time() - compile_start) * 1000.0

    run_start = time.time()
    runtime = SdkRuntime(compile_artifacts, platform, memcpy_required=False)
    max_abs_err = -1.0
    passed = False
    try:
        runtime.load()
        runtime.run()

        rng = np.random.default_rng(seed=157)
        sent = rng.standard_normal(size=total, dtype=np.float32)
        expected = sent * 2.0
        received = np.empty(total, dtype=np.float32)
        runtime.send(in_stream, sent, nonblock=True)
        runtime.receive(out_stream, received, total, nonblock=True)
        runtime.stop()

        max_abs_err = float(np.max(np.abs(received - expected)))
        passed = bool(np.array_equal(received, expected))
        run_status = "succeeded" if passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:{type(exc).__name__}:{str(exc)[:160]}"
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    observed_bytes = total * 4 * 2

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "",
        "executorIteration": 5,
        "sourcePlan": {
            "streamGraphPath": "",
            "executionPlanPath": "",
            "kernelSourcePath": str((SRC_DIR / "compute_double.csl").relative_to(REPO_ROOT)),
        },
        "region": {
            "regionId": "adaptor+demux+compute+mux",
            "width": W,
            "height": 1,
            "peCount": 1 + W + W + W,  # adaptor + demux + compute + mux
        },
        "executedCompile": {
            "compilePrefix": str(Path(compile_prefix).relative_to(REPO_ROOT)),
            "elapsedMs": compile_elapsed_ms,
            "status": "succeeded",
        },
        "executedRun": {
            "status": run_status,
            "elapsedMs": run_elapsed_ms,
            "observedBytesTransferredPerPe": per_pe * 4 * 2,
            "observedBytesTransferredTotal": observed_bytes,
            "numericalParity": {
                "maxAbsErr": max_abs_err,
                "atol": 0,
                "passed": passed,
            },
        },
        "streams": [
            {"role": "input",  "color": "adaptor_in",  "size": total, "dtype": "float32"},
            {"role": "output", "color": "mux_out",     "size": total, "dtype": "float32"},
        ],
        "notes": (
            "Iter-5 — multi-PE single-region SPMD via demux/mux adaptors. "
            "One host stream → 1-PE demux_adaptor → Wx1 demux → Wx1 compute "
            "(SPMD @fmuls x 2.0) → 1xW mux → one host stream. Proves "
            "hidden-dim parallelism, the pattern every E2B / 31B layer "
            "block needs."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(f"executor iter-5: compile {compile_elapsed_ms:.1f} ms, "
          f"run {run_elapsed_ms:.1f} ms, PEs={1 + 3 * W}, per_pe={per_pe}, "
          f"total={total}, run_status={run_status!r}, "
          f"passed={passed}, max_abs_err={max_abs_err} → {trace_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
