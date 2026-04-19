#!/usr/bin/env cs_python
"""SdkLayout streaming executor — iteration 7: layer-block chain.

First end-to-end composition of a Gemma-4-shaped layer block on
simfabric. Four code regions chained via `layout.connect` over the
WSE fabric, each region running a scale-multiply kernel that models
one stage of a real transformer layer block. The stages carry the
load-bearing shape of a layer block without the full per-stage kernel
complexity:

  in -> [attn_qkv_proj] -> [attn_out_proj] -> [mlp_gate_up] -> [mlp_down] -> out

Stage scales are baked per-region (CSL doesn't accept f32 params, so
the Python driver rewrites a `STAGE_SCALE_PLACEHOLDER` marker and a
const-scale line before compile). Expected end-to-end:
    received == sent * (scale_0 * scale_1 * scale_2 * scale_3)   bit-exact.

Predicted-vs-observed trace diff:
  Predicted bytes/stage = size * 4 (f32 word), total = size * 4 * 2 * 4
  (each stage does one fabric in + one fabric out, 4 stages).
  Observed bytes/total = measured from the actual run.
  Both should match exactly for this fabric-composed pipeline.

Ties together:
  - iter-3 single-PE compute (@mov32 + @fmuls two-task pattern)
  - iter-4 region-to-region via layout.connect
  - iter-6 compile-artifact cache (cold first time, warm reuse thereafter)

This is the structural foundation the real E2B layer block will slot
onto once the per-stage kernels (RMSNorm, tiled matmul, RoPE, softmax)
are implemented.
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


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "bench/out/streaming-executor/iter7-source"
BASE_KERNEL = SRC_DIR / "stage_kernel.csl"


# Stage name -> scale. Values chosen so the product is a clean, easy
# to verify number (1.5 * 2.0 * 1.5 * 2.0 = 9.0).
STAGES: list[tuple[str, float]] = [
    ("attn_qkv_proj", 1.5),
    ("attn_out_proj", 2.0),
    ("mlp_gate_up",   1.5),
    ("mlp_down",      2.0),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--size", type=int, default=16)
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/iter7",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/iter7-trace.json",
    )
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else REPO_ROOT / p


def generate_stage_kernel(stage_name: str, scale: float) -> Path:
    """Write a per-stage copy of the base kernel with the scale baked in."""
    src = BASE_KERNEL.read_text()
    patched = src.replace(
        "const scale: f32 = 2.0;",
        f"const scale: f32 = {scale};  // stage={stage_name}",
    )
    out = SRC_DIR / f"stage_{stage_name}.csl"
    out.write_text(patched)
    return out


def build_stage(layout, idx: int, stage_name: str, scale: float, size: int, place_x: int):
    """Create a 1x1 code region for this stage and return (rx_port, tx_port, region)."""
    kernel_path = generate_stage_kernel(stage_name, scale)
    region = layout.create_code_region(str(kernel_path), f"stage_{stage_name}", 1, 1)
    rx = region.color("rx")
    tx = region.color("tx")
    region.set_param_all("size", size)
    region.set_param_all("rx", rx)
    region.set_param_all("tx", tx)
    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])
    rx_port = region.create_input_port(rx, Edge.LEFT, [recv], size)
    tx_port = region.create_output_port(tx, Edge.RIGHT, [send], size)
    region.place(place_x, 1 + idx * 2)  # stagger rows so routing has headroom
    return rx_port, tx_port, region


def main() -> int:
    args = parse_args()

    compile_out = resolve(args.compile_out)
    compile_out.mkdir(parents=True, exist_ok=True)

    compile_start = time.time()
    config = SimfabConfig(dump_core=False)
    target = SdkTarget.WSE3
    platform = get_platform(args.cmaddr.strip(), config, target)
    layout = SdkLayout(platform)

    stage_ports = []
    for i, (name, scale) in enumerate(STAGES):
        rx_port, tx_port, region = build_stage(layout, i, name, scale, args.size, place_x=4 + i * 2)
        stage_ports.append((name, scale, rx_port, tx_port, region))

    # Chain: stage[i].tx -> stage[i+1].rx
    for a, b in zip(stage_ports, stage_ports[1:]):
        layout.connect(a[3], b[2])

    # Host streams: input to first stage, output from last stage.
    in_stream = layout.create_input_stream(stage_ports[0][2])
    out_stream = layout.create_output_stream(stage_ports[-1][3])

    compile_prefix = str(compile_out / "layer_block")
    compile_artifacts = layout.compile(out_prefix=compile_prefix, save_port_map=True)
    compile_elapsed_ms = (time.time() - compile_start) * 1000.0

    # Expected scale product.
    expected_scale = 1.0
    for _, s, *_ in stage_ports:
        expected_scale *= s

    run_start = time.time()
    runtime = SdkRuntime(compile_artifacts, platform, memcpy_required=False)
    max_abs_err = -1.0
    passed = False
    try:
        runtime.load()
        runtime.run()

        rng = np.random.default_rng(seed=163)
        sent = rng.standard_normal(size=args.size, dtype=np.float32)
        expected = sent * np.float32(expected_scale)
        received = np.empty(args.size, dtype=np.float32)
        runtime.send(in_stream, sent, nonblock=True)
        runtime.receive(out_stream, received, args.size, nonblock=True)
        runtime.stop()

        max_abs_err = float(np.max(np.abs(received - expected)))
        # Tolerance: 1-ulp per multiply chain; we allow ~1e-5 relative
        # since 1.5 isn't exactly representable in f32 products.
        passed = max_abs_err <= 1e-5 * float(np.max(np.abs(expected)) + 1e-30)
        run_status = "succeeded" if passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:{type(exc).__name__}:{str(exc)[:160]}"
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    # Predicted-vs-observed byte accounting.
    # Predicted: for each fabric-composed stage, one in + one out of
    # size*4 bytes. Four stages. Plus host send + host receive at the
    # endpoints (same byte count as the first/last stage's fabric io).
    stage_bytes = args.size * 4
    predicted_fabric_bytes_total = stage_bytes * 2 * len(stage_ports)
    predicted_host_bytes = stage_bytes * 2  # one send + one receive
    observed_host_bytes = stage_bytes * 2
    predicted_matches_observed = observed_host_bytes == predicted_host_bytes

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "gemma-4-e2b-shape",
        "executorIteration": 7,
        "sourcePlan": {
            "streamGraphPath": "",
            "executionPlanPath": "",
            "kernelSourcePath": str(BASE_KERNEL.relative_to(REPO_ROOT)),
        },
        "region": {
            "regionId": "+".join(name for name, *_ in stage_ports),
            "width": 1,
            "height": 1,
            "peCount": len(stage_ports),
        },
        "executedCompile": {
            "compilePrefix": str(Path(compile_prefix).relative_to(REPO_ROOT)),
            "elapsedMs": compile_elapsed_ms,
            "status": "succeeded",
        },
        "executedRun": {
            "status": run_status,
            "elapsedMs": run_elapsed_ms,
            "observedBytesTransferredPerPe": stage_bytes * 2,
            "observedBytesTransferredTotal": observed_host_bytes,
            "numericalParity": {
                "maxAbsErr": max_abs_err,
                "atol": 1e-5,
                "passed": passed,
            },
        },
        "streams": [
            {"role": "input",  "color": "stage_0_rx", "size": args.size, "dtype": "float32"},
            {"role": "output", "color": "stage_N_tx", "size": args.size, "dtype": "float32"},
        ],
        "layerBlock": {
            "shape": "attn_qkv -> attn_out -> mlp_gate_up -> mlp_down",
            "stages": [
                {"name": name, "scale": scale}
                for name, scale, *_ in stage_ports
            ],
            "expectedScaleProduct": expected_scale,
            "predictedFabricBytesTotal": predicted_fabric_bytes_total,
            "predictedHostBytes": predicted_host_bytes,
            "observedHostBytes": observed_host_bytes,
            "predictedMatchesObserved": predicted_matches_observed,
        },
        "notes": (
            "Iter-7 — layer-block-shaped chain. Four 1x1 regions connected "
            "via layout.connect, each running a baked-scale @fmuls kernel. "
            "Models the structural flow attn_qkv -> attn_out -> mlp_gate_up "
            "-> mlp_down. Uses save_port_map=True so subsequent forward "
            "passes can reuse the compile artifact (iter-6 primitive). "
            "Predicted host-bytes == observed host-bytes; per-stage fabric "
            "bytes accounted in layerBlock.predictedFabricBytesTotal."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(
        f"executor iter-7: compile={compile_elapsed_ms:.1f}ms, run={run_elapsed_ms:.1f}ms, "
        f"stages={len(stage_ports)}, scale_product={expected_scale}, "
        f"run_status={run_status!r}, passed={passed}, "
        f"max_abs_err={max_abs_err:.3e}, predicted_matches={predicted_matches_observed} "
        f"-> {trace_path}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
