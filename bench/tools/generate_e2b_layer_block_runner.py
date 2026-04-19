#!/usr/bin/env python3
"""Generate an SdkLayout runner for one E2B layer block from the plan.

Reads gemma-4-e2b-stream-execution-plan.json, pulls out the
per-layer-schedule entry for one layer (default: layer 0), and emits a
cs_python runner script that:

  - creates an SdkLayout code region named after plan.codeRegion
    ('transformer_layer_shape'),
  - declares one input port per stream named in the plan
    (ple_rows_stream, ple_projection_stream, layer_weights_stream),
  - declares one output port for the activation the layer emits,
  - feeds all streams from the host at smoke-sized payloads,
  - verifies activation_out == sum(ple_rows, ple_projection, layer_weights)
    bit-exact (stub combine; real kernel replaces this),
  - writes a trace with layerBlockSmokeStatus=succeeded.

The CSL kernel that consumes these streams is at
bench/out/streaming-executor/e2b-layer-block-source/
transformer_layer_shape.csl — hand-written stub today, will be
replaced by generated per-stage code (RMSNorm + attention + MLP)
as follow-up work.

The generator itself produces a plain Python file (not a template),
so reviewers can read the runner directly and the regeneration is
byte-stable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--execution-plan",
        default="bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json",
    )
    p.add_argument("--layer-index", type=int, default=0)
    p.add_argument("--smoke-size", type=int, default=16,
                   help="Per-stream f32 count for smoke payloads (default 16).")
    p.add_argument(
        "--kernel-source",
        default="bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl",
    )
    p.add_argument(
        "--runner-out",
        default="bench/runners/csl-runners/e2b_layer_block_smoke.py",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else REPO_ROOT / p


TEMPLATE = '''#!/usr/bin/env cs_python
"""GENERATED — first E2B layer-block smoke runner.

Produced by bench/tools/generate_e2b_layer_block_runner.py from
{plan_path_rel} (layer {layer_index}). Do not hand-edit; rerun the
generator instead.

Plan stream contract for this layer:
{stream_contract_comment}

Smoke path: each stream carries {smoke_size} f32 values; the stub
kernel combines them as activation_out = ple_rows + ple_projection +
layer_weights and emits the result. When the stub is replaced by
real per-stage kernels, the stream IDs and payload types above are
the stable contract.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (
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
KERNEL_SOURCE = REPO_ROOT / "{kernel_source_rel}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--size", type=int, default={smoke_size})
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/e2b-layer-block-smoke",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/e2b-layer-block-smoke-trace.json",
    )
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else REPO_ROOT / p


def main() -> int:
    args = parse_args()
    compile_out = resolve(args.compile_out)
    compile_out.mkdir(parents=True, exist_ok=True)

    compile_start = time.time()
    config = SimfabConfig(dump_core=False)
    target = SdkTarget.WSE3
    platform = get_platform(args.cmaddr.strip(), config, target)
    layout = SdkLayout(platform)

    region = layout.create_code_region(
        str(KERNEL_SOURCE), "{region_name}", 1, 1
    )

    rx_ple_rows = Color("rx_ple_rows")
    rx_ple_projection = Color("rx_ple_projection")
    rx_layer_weights = Color("rx_layer_weights")
    tx_activation = Color("tx_activation")

    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])

    region.set_param_all("size", args.size)
    region.set_param_all("rx_ple_rows", rx_ple_rows)
    region.set_param_all("rx_ple_projection", rx_ple_projection)
    region.set_param_all("rx_layer_weights", rx_layer_weights)
    region.set_param_all("tx_activation", tx_activation)

    rows_port = region.create_input_port(rx_ple_rows, Edge.LEFT, [recv], args.size)
    proj_port = region.create_input_port(rx_ple_projection, Edge.TOP, [recv], args.size)
    wts_port  = region.create_input_port(rx_layer_weights, Edge.BOTTOM, [recv], args.size)
    act_port  = region.create_output_port(tx_activation, Edge.RIGHT, [send], args.size)

    region.place(4, 2)

    rows_stream = layout.create_input_stream(rows_port)
    proj_stream = layout.create_input_stream(proj_port)
    wts_stream  = layout.create_input_stream(wts_port)
    act_stream  = layout.create_output_stream(act_port)

    compile_prefix = str(compile_out / "transformer_layer_shape")
    compile_artifacts = layout.compile(out_prefix=compile_prefix)
    compile_elapsed_ms = (time.time() - compile_start) * 1000.0

    run_start = time.time()
    runtime = SdkRuntime(compile_artifacts, platform, memcpy_required=False)
    max_abs_err = -1.0
    passed = False
    try:
        runtime.load()
        runtime.run()

        rng = np.random.default_rng(seed=223)
        rows = rng.standard_normal(size=args.size, dtype=np.float32)
        proj = rng.standard_normal(size=args.size, dtype=np.float32)
        wts  = rng.standard_normal(size=args.size, dtype=np.float32)
        expected = rows + proj + wts
        received = np.empty(args.size, dtype=np.float32)

        runtime.send(rows_stream, rows, nonblock=True)
        runtime.send(proj_stream, proj, nonblock=True)
        runtime.send(wts_stream,  wts,  nonblock=True)
        runtime.receive(act_stream, received, args.size, nonblock=True)
        runtime.stop()

        max_abs_err = float(np.max(np.abs(received - expected)))
        passed = bool(np.array_equal(received, expected))
        run_status = "succeeded" if passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:" + type(exc).__name__ + ":" + str(exc)[:160]
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    trace = {{
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "{model_id}",
        "executorIteration": 8,
        "sourcePlan": {{
            "streamGraphPath": "",
            "executionPlanPath": "{plan_path_rel}",
            "kernelSourcePath": "{kernel_source_rel}",
        }},
        "region": {{
            "regionId": "{region_name}_L{layer_index:02d}",
            "width": 1,
            "height": 1,
            "peCount": 1,
        }},
        "executedCompile": {{
            "compilePrefix": str(Path(compile_prefix).relative_to(REPO_ROOT)),
            "elapsedMs": compile_elapsed_ms,
            "status": "succeeded",
        }},
        "executedRun": {{
            "status": run_status,
            "elapsedMs": run_elapsed_ms,
            "observedBytesTransferredPerPe": args.size * 4 * 4,
            "observedBytesTransferredTotal": args.size * 4 * 4,
            "numericalParity": {{
                "maxAbsErr": max_abs_err,
                "atol": 0,
                "passed": passed,
            }},
        }},
        "streams": [
            {{"role": "input",  "color": "rx_ple_rows",        "size": args.size, "dtype": "float32"}},
            {{"role": "input",  "color": "rx_ple_projection",  "size": args.size, "dtype": "float32"}},
            {{"role": "input",  "color": "rx_layer_weights",   "size": args.size, "dtype": "float32"}},
            {{"role": "output", "color": "tx_activation",      "size": args.size, "dtype": "float32"}},
        ],
        "layerBlockSmoke": {{
            "planPath": "{plan_path_rel}",
            "layerIndex": {layer_index},
            "regionName": "{region_name}",
            "kernelIsStub": True,
            "combineRule": "activation_out[i] = ple_rows[i] + ple_projection[i] + layer_weights[i]",
            "status": run_status,
        }},
        "notes": (
            "GENERATED from bench/tools/generate_e2b_layer_block_runner.py. "
            "First SdkLayout runner emitted from the E2B stream-execution-plan. "
            "The kernel is a stub that combines the 3 plan-named streams into "
            "one activation output; real per-stage kernels (RMSNorm, attention, "
            "MLP) replace the stub in follow-up. The stream contract "
            "(rx_ple_rows + rx_ple_projection + rx_layer_weights -> "
            "tx_activation) stays stable across that swap."
        ),
    }}

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\\n", encoding="utf-8")

    print(
        "e2b layer-block smoke (L{layer_index:02d}): "
        f"compile={{compile_elapsed_ms:.1f}}ms, run={{run_elapsed_ms:.1f}}ms, "
        f"run_status={{run_status!r}}, passed={{passed}}, "
        f"max_abs_err={{max_abs_err:.3e}} -> {{trace_path}}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
'''


def main() -> int:
    args = parse_args()
    plan_path = resolve(args.execution_plan)
    plan = json.loads(plan_path.read_text())

    layers = plan["perLayerSchedule"]
    if args.layer_index < 0 or args.layer_index >= len(layers):
        raise SystemExit(f"--layer-index {args.layer_index} out of range 0..{len(layers) - 1}")
    layer = layers[args.layer_index]

    # Build the comment that captures the stream contract from the plan.
    stream_contract_lines = [
        f"//   region:  {layer['codeRegion']}",
        f"//   layer:   {layer['layerIndex']}",
    ]
    for s in layer.get("streams", []):
        stream_contract_lines.append(
            f"//   input:   {s['streamId']} ({s['payloadBytes']} bytes/PE)"
        )
    stream_contract_comment = "\n".join(stream_contract_lines)

    kernel_source_rel = str(resolve(args.kernel_source).relative_to(REPO_ROOT))
    plan_path_rel = str(plan_path.relative_to(REPO_ROOT))

    runner_text = TEMPLATE.format(
        plan_path_rel=plan_path_rel,
        layer_index=args.layer_index,
        smoke_size=args.smoke_size,
        kernel_source_rel=kernel_source_rel,
        region_name=layer["codeRegion"],
        model_id=plan.get("modelId", ""),
        stream_contract_comment=stream_contract_comment,
    )

    runner_out = resolve(args.runner_out)
    runner_out.parent.mkdir(parents=True, exist_ok=True)
    runner_out.write_text(runner_text, encoding="utf-8")
    runner_out.chmod(0o755)

    print(
        f"generated {runner_out.relative_to(REPO_ROOT)} from "
        f"{plan_path_rel} (layer {args.layer_index}, "
        f"{len(layer.get('streams', []))} input streams, "
        f"region={layer['codeRegion']!r})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
