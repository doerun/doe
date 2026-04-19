#!/usr/bin/env cs_python
"""GENERATED — first E2B layer-block smoke runner.

Produced by bench/tools/generate_e2b_layer_block_runner.py from
bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json (layer 0). Do not hand-edit; rerun the
generator instead.

Plan stream contract for this layer:
//   region:  transformer_layer_shape
//   layer:   0
//   input:   ple_rows_stream (2 bytes/PE)
//   input:   ple_projection_stream (23 bytes/PE)
//   input:   layer_weights_stream (2166 bytes/PE)

Smoke path: each stream carries 16 f32 values; the stub
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
KERNEL_SOURCE = REPO_ROOT / "bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--size", type=int, default=16)
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
        str(KERNEL_SOURCE), "transformer_layer_shape", 1, 1
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

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "gemma-4-e2b-it-text-q4k-ehf16-af32",
        "executorIteration": 8,
        "sourcePlan": {
            "streamGraphPath": "",
            "executionPlanPath": "bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json",
            "kernelSourcePath": "bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl",
        },
        "region": {
            "regionId": "transformer_layer_shape_L00",
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
            "observedBytesTransferredPerPe": args.size * 4 * 4,
            "observedBytesTransferredTotal": args.size * 4 * 4,
            "numericalParity": {
                "maxAbsErr": max_abs_err,
                "atol": 0,
                "passed": passed,
            },
        },
        "streams": [
            {"role": "input",  "color": "rx_ple_rows",        "size": args.size, "dtype": "float32"},
            {"role": "input",  "color": "rx_ple_projection",  "size": args.size, "dtype": "float32"},
            {"role": "input",  "color": "rx_layer_weights",   "size": args.size, "dtype": "float32"},
            {"role": "output", "color": "tx_activation",      "size": args.size, "dtype": "float32"},
        ],
        "layerBlockSmoke": {
            "planPath": "bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json",
            "planSha256": "e8fa1420ddcac5700338b9a1b96071d3403c95618c5c6ea536f24e581a505729",
            "layerIndex": 0,
            "regionName": "transformer_layer_shape",
            "kernelSourcePath": "bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl",
            "kernelSourceSha256": "ceb12027ca5781107559bfb1121df8935d0ffd42d0f3d7980b7950cccda56662",
            "kernelIsStub": True,
            "combineRule": "activation_out[i] = ple_rows[i] + ple_projection[i] + layer_weights[i]",
            "status": run_status,
            "targetMode": "local_simfabric",
            "compileArtifactDir": str(compile_out.relative_to(REPO_ROOT)),
            "compileArtifactPrefix": str(Path(compile_prefix).relative_to(REPO_ROOT)),
            "connectionGraph": {
                "region": "transformer_layer_shape",
                "grid": {"width": 1, "height": 1, "peCount": 1, "place": [4, 2]},
                "inputPorts": [
                    {"color": "rx_ple_rows",       "edge": "LEFT",   "size": args.size},
                    {"color": "rx_ple_projection", "edge": "TOP",    "size": args.size},
                    {"color": "rx_layer_weights",  "edge": "BOTTOM", "size": args.size},
                ],
                "outputPorts": [
                    {"color": "tx_activation",     "edge": "RIGHT",  "size": args.size},
                ],
                "crossRegionConnections": [],
            },
            "hostIoLayout": [
                {"streamId": "ple_rows_stream",       "role": "input",  "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 2},
                {"streamId": "ple_projection_stream", "role": "input",  "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 23},
                {"streamId": "layer_weights_stream",  "role": "input",  "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 2166},
                {"streamId": "activation_out_stream", "role": "output", "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 0},
            ],
            "ioBufferSizes": {
                "rows": io_buffer_size,
                "proj": io_buffer_size,
                "wts":  io_buffer_size,
                "activation": io_buffer_size,
            },
            "sendReceiveCounts": {"sends": 3, "receives": 1},
            "simulatorArtifactPaths": {
                "compileDir": str(compile_out.relative_to(REPO_ROOT)),
                "runLogs": [],
                "coreFile": None,
            },
            "sourceModelReceiptPath": "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
            "perKernelShapes": [
    {
        "pattern": "gather",
        "emitter": "emitGatherLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:237)",
        "emitterWidened2D": True,
        "paramsShape": {
            "width": 16,
            "height": 1,
            "hidden_size": 1536,
            "rows_per_pe": 8,
            "num_tokens": 16
        },
        "cslcParamsString": "width:16,height:1,hidden_size:1536,rows_per_pe:8,num_tokens:16",
        "fixtureEquivalentParams": {
            "width": 4,
            "height": 1
        },
        "fixtureEquivalentCslcParamsString": "width:4,height:1",
        "derivationSource": "width/num_tokens from --size smoke arg; hidden_size from manifest.modelConfig.hiddenDim; height=1 for smoke (2-D needed for 31B full-grid per layout-2d-needs audit); rows_per_pe is the emitter default with no manifest override yet. fixtureEquivalentParams carries the governed-lane fixture's width/height (the fixture only passes --params=width:4,height:1 and relies on emitter defaults for the rest); used by the footprint derivation's predictedMatchesObservedShape test.",
        "manifestSteps": [
            "embed_tokens",
            "ple_gather",
            "ple_gather"
        ]
    },
    {
        "pattern": "rope",
        "emitter": "emitRoPELayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:263)",
        "emitterWidened2D": False,
        "paramsShape": {
            "width": 16,
            "head_dim": 512,
            "num_pairs": 256
        },
        "cslcParamsString": "width:16,head_dim:512,num_pairs:256",
        "derivationSource": "width = num_tokens from --size (1-D layout, per-token \u2014 layout-2d-needs audit keeps rope 1-D since num_tokens<=i16); head_dim from manifest.modelConfig.headDim; num_pairs is the standard RoPE half-head_dim convention (cos+sin pair count).",
        "manifestSteps": [
            "rope_q",
            "rope_k",
            "rope_q",
            "rope_k"
        ]
    },
    {
        "pattern": "tiled_matmul",
        "emitter": "emitMatmulLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:168)",
        "emitterWidened2D": True,
        "invocations": [
            {
                "stepName": "q_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 8,
                    "Kt": 768,
                    "Nt": 2048
                },
                "cslcParamsString": "P:2,Mt:8,Kt:768,Nt:2048",
                "weightMatrixShape": "M=16 K=1536 N=4096"
            },
            {
                "stepName": "k_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 8,
                    "Kt": 768,
                    "Nt": 2048
                },
                "cslcParamsString": "P:2,Mt:8,Kt:768,Nt:2048",
                "weightMatrixShape": "M=16 K=1536 N=4096"
            },
            {
                "stepName": "v_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 8,
                    "Kt": 768,
                    "Nt": 2048
                },
                "cslcParamsString": "P:2,Mt:8,Kt:768,Nt:2048",
                "weightMatrixShape": "M=16 K=1536 N=4096"
            },
            {
                "stepName": "o_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 8,
                    "Kt": 2048,
                    "Nt": 768
                },
                "cslcParamsString": "P:2,Mt:8,Kt:2048,Nt:768",
                "weightMatrixShape": "M=16 K=4096 N=1536"
            },
            {
                "stepName": "gate_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 8,
                    "Kt": 768,
                    "Nt": 3072
                },
                "cslcParamsString": "P:2,Mt:8,Kt:768,Nt:3072",
                "weightMatrixShape": "M=16 K=1536 N=6144"
            },
            {
                "stepName": "up_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 8,
                    "Kt": 768,
                    "Nt": 3072
                },
                "cslcParamsString": "P:2,Mt:8,Kt:768,Nt:3072",
                "weightMatrixShape": "M=16 K=1536 N=6144"
            },
            {
                "stepName": "down_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 8,
                    "Kt": 3072,
                    "Nt": 768
                },
                "cslcParamsString": "P:2,Mt:8,Kt:3072,Nt:768",
                "weightMatrixShape": "M=16 K=6144 N=1536"
            }
        ],
        "derivationSource": "P = 2 for smoke (even SUMMA partition; real deployment picks P from memory-plan); Mt/Kt/Nt = weight-matrix dim // P. Weight matrix M/K/N derived from manifest.modelConfig: M = num_tokens (--size), K/N chosen per step \u2014 hiddenDim for projection inputs and output (q/k/v/o), intermediate = hiddenDim * ffnExpansionFactor for FFN gate/up N-dim and down K-dim, qkv_out_dim = numHeads * headDim for QKV N-dim. This per-invocation shape emission is the pattern the 4 audit-blocked emitters (dequant/sample/fused_gemv/fused_ffn) will also use.",
        "manifestSteps": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj"
        ]
    },
    {
        "pattern": "attention_tiled",
        "emitter": "emitTiledAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:403)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "attention",
                "paramsShape": {
                    "width": 16,
                    "head_dim": 512,
                    "kv_len": 4096,
                    "q_len": 16
                },
                "cslcParamsString": "width:16,head_dim:512,kv_len:4096,q_len:16"
            }
        ],
        "derivationSource": "width/q_len = num_tokens from --size (1-D per-tile row); head_dim from manifest.modelConfig.headDim; kv_len = manifest.modelConfig.maxSeqLen as the prefill upper bound (4096 for both E2B and 31B \u2014 well under i16). Per the layout-2d-needs audit, attention_tiled stays 1-D.",
        "manifestSteps": [
            "attention"
        ]
    },
    {
        "pattern": "attention_decode",
        "emitter": "emitDecodeAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:379)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "attention_sliding",
                "variant": "sliding",
                "paramsShape": {
                    "width": 16,
                    "head_dim": 512,
                    "kv_chunk": 32
                },
                "cslcParamsString": "width:16,head_dim:512,kv_chunk:32",
                "kvLenBound": 512
            },
            {
                "stepName": "attention_global",
                "variant": "global",
                "paramsShape": {
                    "width": 16,
                    "head_dim": 512,
                    "kv_chunk": 256
                },
                "cslcParamsString": "width:16,head_dim:512,kv_chunk:256",
                "kvLenBound": 4096
            }
        ],
        "derivationSource": "width = num_tokens from --size (1-D per-head-per-chunk); head_dim from manifest.modelConfig.headDim; kv_chunk = kv_len_bound // width with kv_len_bound = slidingWindowSize for the sliding variant and maxSeqLen for the global decode. Both bounds stay well under i16 at Gemma-4 shapes. Per the layout-2d-needs audit, attention_decode stays 1-D.",
        "manifestSteps": [
            "attention_sliding",
            "attention_global"
        ]
    },
    {
        "pattern": "dequant",
        "emitter": "emitDequantLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:305)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 16,
                    "num_blocks": 1
                },
                "cslcParamsString": "width:16,num_blocks:1"
            }
        ],
        "derivationSource": "width = --size smoke arg; num_blocks = 1 fallback (no manifest step drives this). Gemma-4 fuses dequant into fused_gemv_dequant rather than issuing standalone dequant \u2014 this emitter stays live for future models that separate the two.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step"
    },
    {
        "pattern": "fused_ffn",
        "emitter": "emitFusedFfnLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:557)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 16,
                    "in_dim": 1536,
                    "out_dim": 6144,
                    "in_per_pe": 96
                },
                "cslcParamsString": "width:16,in_dim:1536,out_dim:6144,in_per_pe:96"
            }
        ],
        "derivationSource": "width = --size; in_dim = hiddenDim; out_dim = intermediate = hiddenDim*ffnExpansionFactor; in_per_pe = in_dim // width. No manifest step \u2014 Gemma-4 runs the FFN as three separate matmul steps (gate_proj / up_proj / down_proj) rather than fusing into one kernel, so this entry covers emitter presence only.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step"
    },
    {
        "pattern": "sample",
        "emitter": "emitSampleLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:428)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "sample",
                "paramsShape": {
                    "width": 16,
                    "chunk_size": 16384
                },
                "cslcParamsString": "width:16,chunk_size:16384",
                "vocabSize": 262144
            }
        ],
        "derivationSource": "width = --size smoke arg; chunk_size = vocabSize // width (vocabSize from manifest.modelConfig.vocabSize = 262,144 for Gemma-4). Smoke partitions evenly but deployment will pick a chunk_size that balances per-PE SRAM budget against reduce-chain hop count \u2014 that choice lives in the step-1 generator, so this entry is flagged audit_needs_deployment_generator.",
        "manifestSteps": [
            "sample"
        ],
        "status": "audit_needs_deployment_generator"
    },
    {
        "pattern": "fused_gemv_dequant",
        "emitter": "emitFusedGemvLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:448)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "q_proj",
                "paramsShape": {
                    "width": 16,
                    "out_dim": 4096,
                    "in_dim_per_pe": 96,
                    "num_blocks_per_row": 3
                },
                "cslcParamsString": "width:16,out_dim:4096,in_dim_per_pe:96,num_blocks_per_row:3",
                "weightMatrixShape": "M=1 K=1536 N=4096 (decode row-vector)"
            },
            {
                "stepName": "k_proj",
                "paramsShape": {
                    "width": 16,
                    "out_dim": 4096,
                    "in_dim_per_pe": 96,
                    "num_blocks_per_row": 3
                },
                "cslcParamsString": "width:16,out_dim:4096,in_dim_per_pe:96,num_blocks_per_row:3",
                "weightMatrixShape": "M=1 K=1536 N=4096 (decode row-vector)"
            },
            {
                "stepName": "v_proj",
                "paramsShape": {
                    "width": 16,
                    "out_dim": 4096,
                    "in_dim_per_pe": 96,
                    "num_blocks_per_row": 3
                },
                "cslcParamsString": "width:16,out_dim:4096,in_dim_per_pe:96,num_blocks_per_row:3",
                "weightMatrixShape": "M=1 K=1536 N=4096 (decode row-vector)"
            },
            {
                "stepName": "o_proj",
                "paramsShape": {
                    "width": 16,
                    "out_dim": 1536,
                    "in_dim_per_pe": 256,
                    "num_blocks_per_row": 8
                },
                "cslcParamsString": "width:16,out_dim:1536,in_dim_per_pe:256,num_blocks_per_row:8",
                "weightMatrixShape": "M=1 K=4096 N=1536 (decode row-vector)"
            },
            {
                "stepName": "gate_proj",
                "paramsShape": {
                    "width": 16,
                    "out_dim": 6144,
                    "in_dim_per_pe": 96,
                    "num_blocks_per_row": 3
                },
                "cslcParamsString": "width:16,out_dim:6144,in_dim_per_pe:96,num_blocks_per_row:3",
                "weightMatrixShape": "M=1 K=1536 N=6144 (decode row-vector)"
            },
            {
                "stepName": "up_proj",
                "paramsShape": {
                    "width": 16,
                    "out_dim": 6144,
                    "in_dim_per_pe": 96,
                    "num_blocks_per_row": 3
                },
                "cslcParamsString": "width:16,out_dim:6144,in_dim_per_pe:96,num_blocks_per_row:3",
                "weightMatrixShape": "M=1 K=1536 N=6144 (decode row-vector)"
            },
            {
                "stepName": "down_proj",
                "paramsShape": {
                    "width": 16,
                    "out_dim": 1536,
                    "in_dim_per_pe": 384,
                    "num_blocks_per_row": 12
                },
                "cslcParamsString": "width:16,out_dim:1536,in_dim_per_pe:384,num_blocks_per_row:12",
                "weightMatrixShape": "M=1 K=6144 N=1536 (decode row-vector)"
            }
        ],
        "derivationSource": "width = --size smoke arg (deployment picks per-weight-matrix width from memory-plan budgets; the audit flags this pattern as needs2DFor31B=likely pending step-1 generator output). out_dim per step from manifest.modelConfig: hiddenDim, qkv_out_dim = numHeads*headDim, or intermediate = hiddenDim*ffnExpansionFactor. in_dim_per_pe = in_dim // width. num_blocks_per_row = in_dim_per_pe // 32 (Q4K GGML block).",
        "manifestSteps": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj"
        ],
        "status": "audit_needs_deployment_generator"
    },
    {
        "pattern": "attention_streaming",
        "emitter": "emitStreamingAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:357)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 16,
                    "head_dim": 512,
                    "kv_len": 4096
                },
                "cslcParamsString": "width:16,head_dim:512,kv_len:4096"
            }
        ],
        "derivationSource": "width = num_tokens from --size; head_dim from manifest.modelConfig.headDim; kv_len = manifest.modelConfig.maxSeqLen. Pattern is dormant in Gemma-4 \u2014 no manifest step has op=attention_streaming.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step"
    },
    {
        "pattern": "attention_linear",
        "emitter": "emitLinearAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:489)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 16,
                    "head_dim": 512,
                    "kv_len": 4096
                },
                "cslcParamsString": "width:16,head_dim:512,kv_len:4096"
            }
        ],
        "derivationSource": "width = num_tokens from --size; head_dim from manifest.modelConfig.headDim; kv_len = manifest.modelConfig.maxSeqLen. Pattern is dormant in Gemma-4 \u2014 no manifest step has op=attention_linear.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step"
    },
    {
        "pattern": "kv_write",
        "emitter": "emitKvWriteLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:512)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "kv_write",
                "variant": "standard",
                "paramsShape": {
                    "width": 16,
                    "head_dim": 512,
                    "max_seq_len": 4096
                },
                "cslcParamsString": "width:16,head_dim:512,max_seq_len:4096"
            },
            {
                "stepName": "kv_write_shared",
                "variant": "shared",
                "paramsShape": {
                    "width": 16,
                    "head_dim": 512,
                    "max_seq_len": 4096
                },
                "cslcParamsString": "width:16,head_dim:512,max_seq_len:4096"
            }
        ],
        "derivationSource": "width = num_tokens from --size (1-D per-head). head_dim from manifest.modelConfig.headDim; max_seq_len is the KV-cache capacity bound from manifest.modelConfig.maxSeqLen. Shared variant uses the same --params shape; the shared/standard split is surfaced via the invocation's `variant` field for downstream routing.",
        "manifestSteps": [
            "kv_write",
            "kv_write_shared"
        ]
    },
    {
        "pattern": "kv_read",
        "emitter": "emitKvReadLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:535)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 16,
                    "head_dim": 512,
                    "read_len": 16
                },
                "cslcParamsString": "width:16,head_dim:512,read_len:16"
            }
        ],
        "derivationSource": "width = num_tokens from --size; head_dim from manifest.modelConfig.headDim; read_len defaults to num_tokens for the smoke case \u2014 the dormant pattern has no manifest step driving its shape. If a future graph adds an explicit kv_read step, derivation should key on that step's payload.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step"
    },
    {
        "pattern": "reduction",
        "emitter": "emitReductionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:112)",
        "emitterWidened2D": False,
        "paramsShape": {
            "width": 16,
            "hidden_size": 1536
        },
        "cslcParamsString": "width:16",
        "derivationSource": "width = num_tokens from --size (reduction emitter declares only `param width` at layout level; pe_id/num_pes/reduce_color are set per-tile by the layout not via --params). Single-PE mode per emit_csl_reduction.zig: each PE processes one full token \u2014 width <= max_seq_len <= i16, so 1-D stays fine. hidden_size is a PE-program param carried here for the predicted-footprint per-PE element derivation only.",
        "manifestSteps": [
            "ple_norm",
            "input_norm",
            "post_attn_norm",
            "ple_norm",
            "input_norm",
            "post_attn_norm"
        ]
    }
],
        },
        "notes": (
            "GENERATED from bench/tools/generate_e2b_layer_block_runner.py. "
            "First SdkLayout runner emitted from the E2B stream-execution-plan. "
            "The kernel is a stub that combines the 3 plan-named streams into "
            "one activation output; real per-stage kernels (RMSNorm, attention, "
            "MLP) replace the stub in follow-up. The stream contract "
            "(rx_ple_rows + rx_ple_projection + rx_layer_weights -> "
            "tx_activation) stays stable across that swap."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(
        "e2b layer-block smoke (L00): "
        f"compile={compile_elapsed_ms:.1f}ms, run={run_elapsed_ms:.1f}ms, "
        f"run_status={run_status!r}, passed={passed}, "
        f"max_abs_err={max_abs_err:.3e} -> {trace_path}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
