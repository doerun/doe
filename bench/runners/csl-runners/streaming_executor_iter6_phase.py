#!/usr/bin/env cs_python
"""Iter-6 phase script — one simfab session per invocation.

simfab is process-global and crashes on multi-runtime usage, so each
compile-or-reload phase runs in its own subprocess. Called by
streaming_executor_iter6.py.
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
    SdkCompileArtifacts,
    SdkLayout,
    SdkRuntime,
    SdkTarget,
    SimfabConfig,
    get_platform,
)


def build_layout(platform, kernel_source_path: str, size: int, io_buffer_size: int):
    layout = SdkLayout(platform)
    region = layout.create_code_region(kernel_source_path, "stream_double", 1, 1)
    rx = Color("rx")
    tx = Color("tx")
    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])
    region.set_param_all("size", size)
    region.set_param_all(rx)
    region.set_param_all(tx)
    rx_port = region.create_input_port(rx, Edge.LEFT, [recv], size)
    tx_port = region.create_output_port(tx, Edge.RIGHT, [send], size)
    region.place(4, 1)
    in_name = layout.create_input_stream(rx_port, io_buffer_size=io_buffer_size)
    out_name = layout.create_output_stream(tx_port, io_buffer_size=io_buffer_size)
    return layout, in_name, out_name


def run_once(rt: SdkRuntime, in_name: str, out_name: str, size: int, seed: int):
    sent = np.random.default_rng(seed).standard_normal(size, dtype=np.float32)
    expected = sent * 2.0
    received = np.empty(size, dtype=np.float32)
    rt.load()
    rt.run()
    rt.send(in_name, sent, nonblock=True)
    rt.receive(out_name, received, size, nonblock=True)
    rt.stop()
    max_err = float(np.max(np.abs(received - expected)))
    return bool(np.array_equal(received, expected)), max_err


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["cold", "warm", "large"], required=True)
    p.add_argument("--kernel-source", required=True)
    p.add_argument("--size", type=int, default=16)
    p.add_argument("--compile-dir", required=True)
    p.add_argument("--io-buffer-size", type=int, default=16)
    p.add_argument("--report-json", required=True)
    p.add_argument("--seed", type=int, default=137)
    args = p.parse_args()

    platform = get_platform("", SimfabConfig(dump_core=False), SdkTarget.WSE3)
    compile_dir = Path(args.compile_dir)
    compile_dir.mkdir(parents=True, exist_ok=True)
    prefix = str(compile_dir / "stream_double")
    port_map_path = prefix + "_port_map.json"

    report: dict = {"phase": args.phase}

    if args.phase in ("cold", "large"):
        t0 = time.time()
        layout, in_name, out_name = build_layout(
            platform, args.kernel_source, args.size, args.io_buffer_size
        )
        ca = layout.compile(out_prefix=prefix, save_port_map=True)
        compile_ms = (time.time() - t0) * 1000.0
        report["compileMs"] = compile_ms
        report["portMapPath"] = port_map_path
        report["streamIn"] = in_name
        report["streamOut"] = out_name
    else:  # warm
        t0 = time.time()
        ca = SdkCompileArtifacts(str(compile_dir))
        ca = ca.add_port_mapping(port_map_path)
        report["setupMs"] = (time.time() - t0) * 1000.0
        in_name = "stream_double_rx_port"
        out_name = "stream_double_tx_port"

    t1 = time.time()
    rt = SdkRuntime(ca, platform, memcpy_required=False)
    runtime_ctor_ms = (time.time() - t1) * 1000.0
    report["runtimeCtorMs"] = runtime_ctor_ms

    t2 = time.time()
    passed, max_err = run_once(rt, in_name, out_name, args.size, seed=args.seed)
    run_ms = (time.time() - t2) * 1000.0
    report["runMs"] = run_ms
    report["passed"] = passed
    report["maxAbsErr"] = max_err

    Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_json).write_text(json.dumps(report, indent=2) + "\n")
    print(f"phase={args.phase} passed={passed} run_ms={run_ms:.1f} report={args.report_json}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
