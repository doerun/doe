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
    # Smoke-shape tiled_matmul: emitter at L168 takes P × P SUMMA tiles
    # with Mt/Kt/Nt per-tile dims. Already 2-D per the audit (emitter
    # declares P with u16). Unlike gather/rope/reduction, tiled_matmul
    # has MULTIPLE call sites per layer (q/k/v/o projections plus FFN
    # gate/up/down), each with different K/N dims. Emit one pattern
    # entry with an `invocations[]` sub-list — a generalization the
    # remaining weight-matrix patterns (dequant, fused_gemv, fused_ffn)
    # will also use.
    ffn_expansion = int(mc.get("ffnExpansionFactor", 4))
    num_heads = int(mc.get("numHeads", 0))
    hidden = hidden_dim or 1536
    intermediate = hidden * ffn_expansion
    # Pick a small P for smoke so Mt/Kt/Nt stay small ints cslc can
    # round-trip. Real deployment uses larger P from memory-plan.
    P_smoke = 2
    qkv_out_dim = (num_heads or 8) * (head_dim or 512)  # total Q/K/V dim

    def mm_params(step_name: str, m: int, k: int, n: int) -> dict:
        """Compute {P, Mt, Kt, Nt} with simple even division; round up if
        needed. Smoke values — real deployment picks P from the memory plan."""
        def tile(d: int) -> int:
            return max(1, d // P_smoke)
        mt, kt, nt = tile(m), tile(k), tile(n)
        return {
            "stepName": step_name,
            "paramsShape": {"P": P_smoke, "Mt": mt, "Kt": kt, "Nt": nt},
            "cslcParamsString": f"P:{P_smoke},Mt:{mt},Kt:{kt},Nt:{nt}",
            "weightMatrixShape": f"M={m} K={k} N={n}",
        }

    mm_invocations = [
        mm_params("q_proj",    smoke_size, hidden,       qkv_out_dim),
        mm_params("k_proj",    smoke_size, hidden,       qkv_out_dim),
        mm_params("v_proj",    smoke_size, hidden,       qkv_out_dim),
        mm_params("o_proj",    smoke_size, qkv_out_dim,  hidden),
        mm_params("gate_proj", smoke_size, hidden,       intermediate),
        mm_params("up_proj",   smoke_size, hidden,       intermediate),
        mm_params("down_proj", smoke_size, intermediate, hidden),
    ]
    shapes.append({
        "pattern": "tiled_matmul",
        "emitter": "emitMatmulLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:168)",
        "emitterWidened2D": True,
        "invocations": mm_invocations,
        "derivationSource": (
            "P = 2 for smoke (even SUMMA partition; real deployment picks P "
            "from memory-plan); Mt/Kt/Nt = weight-matrix dim // P. Weight "
            "matrix M/K/N derived from manifest.modelConfig: M = num_tokens "
            "(--size), K/N chosen per step — hiddenDim for projection inputs "
            "and output (q/k/v/o), intermediate = hiddenDim * ffnExpansionFactor "
            "for FFN gate/up N-dim and down K-dim, qkv_out_dim = numHeads * "
            "headDim for QKV N-dim. This per-invocation shape emission is the "
            "pattern the 4 audit-blocked emitters (dequant/sample/fused_gemv/"
            "fused_ffn) will also use."
        ),
        "manifestSteps": [
            s["name"] for s in manifest.get("steps", [])
            if s.get("op") == "matmul" and s.get("kernelKey") == "tiled"
        ],
    })
    # Smoke-shape attention_tiled: emitter at L403 takes width + head_dim
    # + kv_len + q_len. Per the audit attention_tiled stays 1-D since the
    # width is per-tile (per-head-per-row). Manifest has one tiled
    # attention step per layer (prefill); the decode variants land on
    # attention_decode, not this pattern.
    max_seq_len = int(mc.get("maxSeqLen", 4096))
    attn_tiled_steps = [
        s["name"] for s in manifest.get("steps", [])
        if s.get("op") == "attention_prefill"
    ]
    shapes.append({
        "pattern": "attention_tiled",
        "emitter": "emitTiledAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:403)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": step_name,
                "paramsShape": {
                    "width": smoke_size,
                    "head_dim": head_dim or 128,
                    "kv_len": max_seq_len,
                    "q_len": smoke_size,
                },
                "cslcParamsString": (
                    f"width:{smoke_size},"
                    f"head_dim:{head_dim or 128},"
                    f"kv_len:{max_seq_len},"
                    f"q_len:{smoke_size}"
                ),
            }
            for step_name in (attn_tiled_steps or ["attention"])
        ],
        "derivationSource": (
            "width/q_len = num_tokens from --size (1-D per-tile row); "
            "head_dim from manifest.modelConfig.headDim; kv_len = "
            "manifest.modelConfig.maxSeqLen as the prefill upper bound "
            "(4096 for both E2B and 31B — well under i16). Per the "
            "layout-2d-needs audit, attention_tiled stays 1-D."
        ),
        "manifestSteps": attn_tiled_steps,
    })
    # Smoke-shape attention_decode: emitter at L379 takes width + head_dim
    # + kv_chunk (NOT kv_len — the decode emitter chunks the KV cache).
    # Manifest has two decode-attention variants per layer: sliding
    # (bounded by slidingWindowSize) and global (bounded by maxSeqLen).
    # Per the audit stays 1-D (per-head-per-chunk width).
    sliding_window = int(m.get("slidingWindowSize", 0)) if (m := manifest) else 0
    decode_invocations = []
    for s in manifest.get("steps", []):
        op = s.get("op", "")
        key = s.get("kernelKey", "")
        if op == "attention_sliding":
            kv_len = sliding_window or 512
            variant = "sliding"
        elif op == "attention" and "decode" in key:
            kv_len = max_seq_len
            variant = "global"
        else:
            continue
        kv_chunk = max(1, kv_len // smoke_size)
        decode_invocations.append({
            "stepName": s["name"],
            "variant": variant,
            "paramsShape": {
                "width": smoke_size,
                "head_dim": head_dim or 128,
                "kv_chunk": kv_chunk,
            },
            "cslcParamsString": (
                f"width:{smoke_size},"
                f"head_dim:{head_dim or 128},"
                f"kv_chunk:{kv_chunk}"
            ),
            "kvLenBound": kv_len,
        })
    if decode_invocations:
        shapes.append({
            "pattern": "attention_decode",
            "emitter": "emitDecodeAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:379)",
            "emitterWidened2D": False,
            "invocations": decode_invocations,
            "derivationSource": (
                "width = num_tokens from --size (1-D per-head-per-chunk); "
                "head_dim from manifest.modelConfig.headDim; kv_chunk = "
                "kv_len_bound // width with kv_len_bound = slidingWindowSize "
                "for the sliding variant and maxSeqLen for the global decode. "
                "Both bounds stay well under i16 at Gemma-4 shapes. Per the "
                "layout-2d-needs audit, attention_decode stays 1-D."
            ),
            "manifestSteps": [inv["stepName"] for inv in decode_invocations],
        })
    # Smoke-shape dequant (dormant): emitter at L305 takes width +
    # num_blocks. Gemma-4 fuses dequant into GEMV (see
    # fused_gemv_dequant above), so no standalone dequant step appears
    # in the manifest. Record emitter-default shape and flag as dormant.
    dequant_steps = [s["name"] for s in manifest.get("steps", []) if s.get("op") == "dequant"]
    if not dequant_steps:
        shapes.append({
            "pattern": "dequant",
            "emitter": "emitDequantLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:305)",
            "emitterWidened2D": False,
            "invocations": [{
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": smoke_size,
                    "num_blocks": 1,
                },
                "cslcParamsString": f"width:{smoke_size},num_blocks:1",
            }],
            "derivationSource": (
                "width = --size smoke arg; num_blocks = 1 fallback (no "
                "manifest step drives this). Gemma-4 fuses dequant into "
                "fused_gemv_dequant rather than issuing standalone "
                "dequant — this emitter stays live for future models "
                "that separate the two."
            ),
            "manifestSteps": [],
            "status": "dormant_pattern_no_manifest_step",
        })

    # Smoke-shape fused_ffn (dormant): emitter at L557 takes width +
    # in_dim + out_dim + in_per_pe. Gemma-4 decomposes FFN into
    # gate_proj / up_proj / down_proj matmuls (via tiled_matmul and
    # fused_gemv_dequant) rather than one fused op, so no manifest
    # step references this emitter today.
    fused_ffn_steps = [s["name"] for s in manifest.get("steps", []) if s.get("op") == "fused_ffn"]
    if not fused_ffn_steps:
        in_per_pe = max(1, hidden // smoke_size)
        shapes.append({
            "pattern": "fused_ffn",
            "emitter": "emitFusedFfnLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:557)",
            "emitterWidened2D": False,
            "invocations": [{
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": smoke_size,
                    "in_dim": hidden,
                    "out_dim": intermediate,
                    "in_per_pe": in_per_pe,
                },
                "cslcParamsString": (
                    f"width:{smoke_size},"
                    f"in_dim:{hidden},"
                    f"out_dim:{intermediate},"
                    f"in_per_pe:{in_per_pe}"
                ),
            }],
            "derivationSource": (
                "width = --size; in_dim = hiddenDim; out_dim = "
                "intermediate = hiddenDim*ffnExpansionFactor; in_per_pe "
                "= in_dim // width. No manifest step — Gemma-4 runs the "
                "FFN as three separate matmul steps (gate_proj / up_proj "
                "/ down_proj) rather than fusing into one kernel, so "
                "this entry covers emitter presence only."
            ),
            "manifestSteps": [],
            "status": "dormant_pattern_no_manifest_step",
        })

    # Smoke-shape sample: emitter at L428 takes width + chunk_size.
    # vocabSize = 262,144 for Gemma-4 (both E2B and 31B) — well above
    # i16 if distributed with chunk_size=1. Per the audit this is one
    # of the 4 audit-blocked emitters: whether deployment chooses a
    # chunk_size that keeps width below i16 depends on the step-1
    # generator's output.
    vocab_size = int(mc.get("vocabSize", 0))
    sample_steps = [s["name"] for s in manifest.get("steps", []) if s.get("op") == "sample"]
    if vocab_size and sample_steps:
        chunk_size = max(1, vocab_size // smoke_size)
        shapes.append({
            "pattern": "sample",
            "emitter": "emitSampleLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:428)",
            "emitterWidened2D": False,
            "invocations": [{
                "stepName": sample_steps[0],
                "paramsShape": {
                    "width": smoke_size,
                    "chunk_size": chunk_size,
                },
                "cslcParamsString": f"width:{smoke_size},chunk_size:{chunk_size}",
                "vocabSize": vocab_size,
            }],
            "derivationSource": (
                "width = --size smoke arg; chunk_size = vocabSize // width "
                "(vocabSize from manifest.modelConfig.vocabSize = 262,144 "
                "for Gemma-4). Smoke partitions evenly but deployment "
                "will pick a chunk_size that balances per-PE SRAM budget "
                "against reduce-chain hop count — that choice lives in "
                "the step-1 generator, so this entry is flagged "
                "audit_needs_deployment_generator."
            ),
            "manifestSteps": sample_steps,
            "status": "audit_needs_deployment_generator",
        })
    # Smoke-shape fused_gemv_dequant: emitter at L448 takes width +
    # out_dim + in_dim_per_pe + num_blocks_per_row. Per the audit this
    # is one of the 4 entries whose needs2DFor31B resolves to "likely"
    # and is gated on the step-1 generator's per-weight-matrix width
    # derivation. The shapes below use a fixed smoke width (--size)
    # and partition each weight matrix's in_dim by width; deployment
    # will pick width from memory-plan budgets.
    #
    # Q4K packs scales + quants in 32-element blocks (GGML convention).
    Q4K_BLOCK = 32
    gemv_invocations = []
    for s in manifest.get("steps", []):
        if s.get("op") != "matmul_q4k" or s.get("kernelKey") != "gemv":
            continue
        name = s["name"]
        # Same weight-matrix shape table as tiled_matmul — the decode
        # path uses the same matrices, dequantized on the fly.
        if name in ("q_proj", "k_proj", "v_proj"):
            in_dim, out_dim = hidden, qkv_out_dim
        elif name == "o_proj":
            in_dim, out_dim = qkv_out_dim, hidden
        elif name in ("gate_proj", "up_proj"):
            in_dim, out_dim = hidden, intermediate
        elif name == "down_proj":
            in_dim, out_dim = intermediate, hidden
        else:
            # Unknown step — defer to deployment generator.
            continue
        in_dim_per_pe = max(1, in_dim // smoke_size)
        num_blocks_per_row = max(1, in_dim_per_pe // Q4K_BLOCK)
        gemv_invocations.append({
            "stepName": name,
            "paramsShape": {
                "width": smoke_size,
                "out_dim": out_dim,
                "in_dim_per_pe": in_dim_per_pe,
                "num_blocks_per_row": num_blocks_per_row,
            },
            "cslcParamsString": (
                f"width:{smoke_size},"
                f"out_dim:{out_dim},"
                f"in_dim_per_pe:{in_dim_per_pe},"
                f"num_blocks_per_row:{num_blocks_per_row}"
            ),
            "weightMatrixShape": f"M=1 K={in_dim} N={out_dim} (decode row-vector)",
        })
    if gemv_invocations:
        shapes.append({
            "pattern": "fused_gemv_dequant",
            "emitter": "emitFusedGemvLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:448)",
            "emitterWidened2D": False,
            "invocations": gemv_invocations,
            "derivationSource": (
                "width = --size smoke arg (deployment picks per-weight-matrix "
                "width from memory-plan budgets; the audit flags this pattern "
                "as needs2DFor31B=likely pending step-1 generator output). "
                "out_dim per step from manifest.modelConfig: hiddenDim, "
                "qkv_out_dim = numHeads*headDim, or intermediate = "
                "hiddenDim*ffnExpansionFactor. in_dim_per_pe = in_dim // width. "
                "num_blocks_per_row = in_dim_per_pe // 32 (Q4K GGML block)."
            ),
            "manifestSteps": [inv["stepName"] for inv in gemv_invocations],
            "status": "audit_needs_deployment_generator",
        })
    # Smoke-shape attention_streaming (dormant): emitter at L357 takes
    # width + head_dim + kv_len. Per the audit stays 1-D (per-head). No
    # Gemma-4 manifest step currently lands on this pattern — the model
    # uses attention_tiled for prefill and attention_decode for decode.
    # The entry records emitter-default shape so the 14-pattern coverage
    # stays complete; real deployment would populate this when a future
    # model adds a streaming-attention variant.
    shapes.append({
        "pattern": "attention_streaming",
        "emitter": "emitStreamingAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:357)",
        "emitterWidened2D": False,
        "invocations": [{
            "stepName": "(dormant)",
            "paramsShape": {
                "width": smoke_size,
                "head_dim": head_dim or 128,
                "kv_len": max_seq_len,
            },
            "cslcParamsString": (
                f"width:{smoke_size},"
                f"head_dim:{head_dim or 128},"
                f"kv_len:{max_seq_len}"
            ),
        }],
        "derivationSource": (
            "width = num_tokens from --size; head_dim from "
            "manifest.modelConfig.headDim; kv_len = manifest.modelConfig.maxSeqLen. "
            "Pattern is dormant in Gemma-4 — no manifest step has op=attention_streaming."
        ),
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step",
    })
    # Smoke-shape attention_linear (dormant): emitter at L489 takes
    # width + head_dim + kv_len (no q_len). Same dormant story as
    # streaming attention — Gemma-4 doesn't use linear attention.
    shapes.append({
        "pattern": "attention_linear",
        "emitter": "emitLinearAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:489)",
        "emitterWidened2D": False,
        "invocations": [{
            "stepName": "(dormant)",
            "paramsShape": {
                "width": smoke_size,
                "head_dim": head_dim or 64,
                "kv_len": max_seq_len,
            },
            "cslcParamsString": (
                f"width:{smoke_size},"
                f"head_dim:{head_dim or 64},"
                f"kv_len:{max_seq_len}"
            ),
        }],
        "derivationSource": (
            "width = num_tokens from --size; head_dim from "
            "manifest.modelConfig.headDim; kv_len = manifest.modelConfig.maxSeqLen. "
            "Pattern is dormant in Gemma-4 — no manifest step has op=attention_linear."
        ),
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step",
    })
    # Smoke-shape kv_write: emitter at L512 takes width + head_dim +
    # max_seq_len. 1-D per audit (per-head). Manifest has two kv_write
    # variants: standard and shared. Both land on the kv_write pattern.
    kv_write_invocations = []
    for s in manifest.get("steps", []):
        if s.get("op") in ("kv_write", "kv_write_shared"):
            kv_write_invocations.append({
                "stepName": s["name"],
                "variant": "shared" if s.get("op") == "kv_write_shared" else "standard",
                "paramsShape": {
                    "width": smoke_size,
                    "head_dim": head_dim or 128,
                    "max_seq_len": max_seq_len,
                },
                "cslcParamsString": (
                    f"width:{smoke_size},"
                    f"head_dim:{head_dim or 128},"
                    f"max_seq_len:{max_seq_len}"
                ),
            })
    if kv_write_invocations:
        shapes.append({
            "pattern": "kv_write",
            "emitter": "emitKvWriteLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:512)",
            "emitterWidened2D": False,
            "invocations": kv_write_invocations,
            "derivationSource": (
                "width = num_tokens from --size (1-D per-head). "
                "head_dim from manifest.modelConfig.headDim; max_seq_len "
                "is the KV-cache capacity bound from "
                "manifest.modelConfig.maxSeqLen. Shared variant uses the "
                "same --params shape; the shared/standard split is "
                "surfaced via the invocation's `variant` field for "
                "downstream routing."
            ),
            "manifestSteps": [inv["stepName"] for inv in kv_write_invocations],
        })
    # Smoke-shape kv_read: emitter at L535 takes width + head_dim +
    # read_len. 1-D per audit. Not in E2B/31B manifests today — the
    # pattern is dormant in current Gemma-4 steps; every attention
    # kernel inlines its own KV fetch. Emit the entry anyway so the
    # generator's shape coverage matches the 14-emitter audit.
    shapes.append({
        "pattern": "kv_read",
        "emitter": "emitKvReadLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:535)",
        "emitterWidened2D": False,
        "invocations": [{
            "stepName": "(dormant)",
            "paramsShape": {
                "width": smoke_size,
                "head_dim": head_dim or 128,
                "read_len": smoke_size,
            },
            "cslcParamsString": (
                f"width:{smoke_size},"
                f"head_dim:{head_dim or 128},"
                f"read_len:{smoke_size}"
            ),
        }],
        "derivationSource": (
            "width = num_tokens from --size; head_dim from "
            "manifest.modelConfig.headDim; read_len defaults to "
            "num_tokens for the smoke case — the dormant pattern has "
            "no manifest step driving its shape. If a future graph adds "
            "an explicit kv_read step, derivation should key on that "
            "step's payload."
        ),
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step",
    })
    # Smoke-shape reduction (RMSNorm / softmax single-PE lowering): the
    # emitter at L112 declares only `param width: i16;` — reduce_color,
    # pe_id, and num_pes are set at tile-code time by the layout, not
    # via --params. Width is per-token (one PE per token for the single-
    # PE RMSNorm lowering); per the audit reduction stays 1-D because
    # num_tokens stays <= i16.
    reduction_manifest_ops = ("rmsnorm", "ple_norm", "softmax", "layernorm")
    shapes.append({
        "pattern": "reduction",
        "emitter": "emitReductionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:112)",
        "emitterWidened2D": False,
        "paramsShape": {
            "width": smoke_size,
        },
        "cslcParamsString": f"width:{smoke_size}",
        "derivationSource": (
            "width = num_tokens from --size (reduction emitter declares "
            "only `param width` at layout level; pe_id/num_pes/reduce_color "
            "are set per-tile by the layout not via --params). Single-PE "
            "mode per emit_csl_reduction.zig: each PE processes one full "
            "token — width <= max_seq_len <= i16, so 1-D stays fine."
        ),
        "manifestSteps": [
            s["name"] for s in manifest.get("steps", [])
            if s.get("op") in reduction_manifest_ops
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
