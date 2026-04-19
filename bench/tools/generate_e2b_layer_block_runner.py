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
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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

    io_buffer_size = 1024  # SdkLayout default; exposed for the receipt.
    rows_stream = layout.create_input_stream(rows_port, io_buffer_size=io_buffer_size)
    proj_stream = layout.create_input_stream(proj_port, io_buffer_size=io_buffer_size)
    wts_stream  = layout.create_input_stream(wts_port, io_buffer_size=io_buffer_size)
    act_stream  = layout.create_output_stream(act_port, io_buffer_size=io_buffer_size)

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
            "planSha256": "{plan_sha256}",
            "layerIndex": {layer_index},
            "regionName": "{region_name}",
            "kernelSourcePath": "{kernel_source_rel}",
            "kernelSourceSha256": "{kernel_source_sha256}",
            "kernelIsStub": True,
            "combineRule": "activation_out[i] = ple_rows[i] + ple_projection[i] + layer_weights[i]",
            "status": run_status,
            "targetMode": "local_simfabric",
            "compileArtifactDir": str(compile_out.relative_to(REPO_ROOT)),
            "compileArtifactPrefix": str(Path(compile_prefix).relative_to(REPO_ROOT)),
            "connectionGraph": {{
                "region": "{region_name}",
                "grid": {{"width": 1, "height": 1, "peCount": 1, "place": [4, 2]}},
                "inputPorts": [
                    {{"color": "rx_ple_rows",       "edge": "LEFT",   "size": args.size}},
                    {{"color": "rx_ple_projection", "edge": "TOP",    "size": args.size}},
                    {{"color": "rx_layer_weights",  "edge": "BOTTOM", "size": args.size}},
                ],
                "outputPorts": [
                    {{"color": "tx_activation",     "edge": "RIGHT",  "size": args.size}},
                ],
                "crossRegionConnections": [],
            }},
            "hostIoLayout": [
                {{"streamId": "ple_rows_stream",       "role": "input",  "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 2}},
                {{"streamId": "ple_projection_stream", "role": "input",  "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 23}},
                {{"streamId": "layer_weights_stream",  "role": "input",  "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 2166}},
                {{"streamId": "activation_out_stream", "role": "output", "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 0}},
            ],
            "ioBufferSizes": {{
                "rows": io_buffer_size,
                "proj": io_buffer_size,
                "wts":  io_buffer_size,
                "activation": io_buffer_size,
            }},
            "sendReceiveCounts": {{"sends": 3, "receives": 1}},
            "simulatorArtifactPaths": {{
                "compileDir": str(compile_out.relative_to(REPO_ROOT)),
                "runLogs": [],
                "coreFile": None,
            }},
            "sourceModelReceiptPath": "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
            "perKernelShapes": {per_kernel_shapes_literal},
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


def derive_per_kernel_shapes(
    plan: dict,
    manifest: dict,
    smoke_size: int,
) -> list[dict]:
    """Pick --params shape for each real kernel pattern this layer touches.

    Today only gather is widened (see plan Build-order step 2 audit at
    bench/out/layout-2d-needs/layout-2d-needs.json). This function
    demonstrates the per-kernel-shape-emission pattern that plan step 1
    owes the step-2 sweep. Extending to more patterns (rope, attention,
    dequant, etc.) is follow-up; the data structure's shape is what
    matters for cross-step readability.

    Derivation rule for gather:
      width         = smoke_size (so num_tokens = smoke_size stays <= i16;
                      real deployment uses num_tokens from the step expansion)
      height        = 1    (1-D smoke; 2-D for 31B full-grid is a future flip)
      hidden_size   = manifest.modelConfig.hiddenDim
      rows_per_pe   = 8    (emitter default; the manifest has no override yet)
      num_tokens    = smoke_size
    """
    mc = manifest.get("modelConfig", {})
    hidden_dim = int(mc.get("hiddenDim", 0))
    head_dim = int(mc.get("headDim", 0))
    shapes: list[dict] = []
    # Smoke-shape gather: the manifest has two gather steps
    # (embed_tokens and ple_gather); emit one shape entry that covers
    # the shared pattern-level --params. Real deployment would pick
    # per-step widths based on the weight matrix / token count.
    shapes.append({
        "pattern": "gather",
        "emitter": "emitGatherLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:237)",
        "emitterWidened2D": True,
        "paramsShape": {
            "width": smoke_size,
            "height": 1,
            "hidden_size": hidden_dim or 64,
            "rows_per_pe": 8,
            "num_tokens": smoke_size,
        },
        "cslcParamsString": (
            f"width:{smoke_size},height:1,"
            f"hidden_size:{hidden_dim or 64},"
            f"rows_per_pe:8,num_tokens:{smoke_size}"
        ),
        "derivationSource": (
            "width/num_tokens from --size smoke arg; hidden_size from "
            "manifest.modelConfig.hiddenDim; height=1 for smoke (2-D "
            "needed for 31B full-grid per layout-2d-needs audit); "
            "rows_per_pe is the emitter default with no manifest override yet."
        ),
        "manifestSteps": [
            s["name"] for s in manifest.get("steps", [])
            if s.get("op") in ("embed", "ple_gather")
        ],
    })
    # Smoke-shape rope: the audit keeps rope 1-D since its width is
    # per-token (num_tokens <= max_seq_len <= ~4k, well under i16).
    # num_pairs follows the standard RoPE complex-rotation layout:
    # head_dim f32 values pair up into head_dim/2 (cos,sin) pairs.
    rope_num_pairs = (head_dim // 2) if head_dim else 64
    shapes.append({
        "pattern": "rope",
        "emitter": "emitRoPELayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:263)",
        "emitterWidened2D": False,
        "paramsShape": {
            "width": smoke_size,
            "head_dim": head_dim or 128,
            "num_pairs": rope_num_pairs,
        },
        "cslcParamsString": (
            f"width:{smoke_size},"
            f"head_dim:{head_dim or 128},"
            f"num_pairs:{rope_num_pairs}"
        ),
        "derivationSource": (
            "width = num_tokens from --size (1-D layout, per-token — "
            "layout-2d-needs audit keeps rope 1-D since num_tokens<=i16); "
            "head_dim from manifest.modelConfig.headDim; num_pairs is the "
            "standard RoPE half-head_dim convention (cos+sin pair count)."
        ),
        "manifestSteps": [
            s["name"] for s in manifest.get("steps", [])
            if s.get("op") == "rope"
        ],
    })
    return shapes


def main() -> int:
    args = parse_args()
    plan_path = resolve(args.execution_plan)
    plan = json.loads(plan_path.read_text())

    layers = plan["perLayerSchedule"]
    if args.layer_index < 0 or args.layer_index >= len(layers):
        raise SystemExit(f"--layer-index {args.layer_index} out of range 0..{len(layers) - 1}")
    layer = layers[args.layer_index]

    # Read the manifest that produced this plan so per-kernel shapes can be
    # grounded in modelConfig dims, not hand-typed numbers.
    manifest_rel = "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json"
    manifest_path = REPO_ROOT / manifest_rel
    manifest = json.loads(manifest_path.read_text())
    per_kernel_shapes = derive_per_kernel_shapes(plan, manifest, args.smoke_size)

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

    kernel_source_path = resolve(args.kernel_source)
    kernel_source_rel = str(kernel_source_path.relative_to(REPO_ROOT))
    plan_path_rel = str(plan_path.relative_to(REPO_ROOT))
    plan_sha256 = sha256(plan_path)
    kernel_source_sha256 = sha256(kernel_source_path)

    # Render perKernelShapes as a Python-literal dict inside the runner
    # (the runner embeds it verbatim in the trace). json.dumps gives valid
    # Python for the values we emit here (True is JSON true, which Python
    # also accepts under json.loads; the generated runner serializes via
    # json.dumps so the True/False/None mapping round-trips cleanly).
    per_kernel_shapes_literal = json.dumps(per_kernel_shapes, indent=4) \
        .replace("true", "True").replace("false", "False").replace("null", "None")

    runner_text = TEMPLATE.format(
        plan_path_rel=plan_path_rel,
        plan_sha256=plan_sha256,
        layer_index=args.layer_index,
        smoke_size=args.smoke_size,
        kernel_source_rel=kernel_source_rel,
        kernel_source_sha256=kernel_source_sha256,
        region_name=layer["codeRegion"],
        model_id=plan.get("modelId", ""),
        stream_contract_comment=stream_contract_comment,
        per_kernel_shapes_literal=per_kernel_shapes_literal,
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
