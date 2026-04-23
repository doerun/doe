from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RUNNER_DIR = REPO_ROOT / "bench" / "runners" / "csl-runners"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from bench.tools.run_doe_csl_int4ple_transcript import (  # noqa: E402
    program_bundle_logits_digests,
)
from bench.tools.int4ple_manifest_compile_params import (  # noqa: E402
    apply_manifest_compile_params,
)
from int4ple_hostplan_execution_plan import (  # noqa: E402
    build_hostplan_execution_plan,
)
from int4ple_hostplan_executor_validator import (  # noqa: E402
    validate_hostplan_executor,
)

spec = importlib.util.spec_from_file_location(
    "int4ple_compile_target_sim_runner",
    RUNNER_DIR / "int4ple_compile_target_sim_runner.py",
)
assert spec is not None
assert spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_layout(path: Path, *, exports: list[tuple[str, str]]) -> None:
    lines = [
        "layout {",
        "    @set_rectangle(1, 1);",
    ]
    for name, export_type in exports:
        lines.append(f'    @export_name("{name}", {export_type});')
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clone_json(value: object) -> object:
    return json.loads(json.dumps(value))


def make_valid_executor_validator_fixture(
    root: Path,
) -> tuple[Path, dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    compile_root = root / "compile"
    write_json(compile_root / "compiled" / "sample" / "out.json", {})
    plan = {
        "inputs": {
            "compileTargets": [
                {
                    "name": "sample",
                    "layout": "sample/layout.csl",
                    "peProgram": "sample/pe_program.csl",
                }
            ]
        }
    }
    runtime_config = {
        "stateBuffers": [{"kind": "kv_cache", "name": "kv_cache"}],
    }
    scheduler = {
        "runtimeScheduler": {
            "status": "bound",
            "activationRouting": {"status": "bound"},
            "launches": [
                {
                    "launchIndex": 0,
                    "kernelName": "sample",
                    "symbolDataflowPresent": True,
                    "symbols": {
                        "prompt": {
                            "buffer": "input:prompt_token_ids",
                            "role": "tokenized_prompt",
                            "access": "read",
                        },
                        "logits": {
                            "buffer": "logits:decode:0000:sample",
                            "role": "logits",
                            "access": "write",
                        },
                        "tokens": {
                            "buffer": "tokens:decode:0000",
                            "role": "generated_tokens",
                            "access": "write",
                        },
                    },
                    "inputs": [
                        {
                            "symbol": "prompt",
                            "buffer": "input:prompt_token_ids",
                            "role": "tokenized_prompt",
                            "access": "read",
                        }
                    ],
                    "outputs": [
                        {
                            "symbol": "logits",
                            "buffer": "logits:decode:0000:sample",
                            "role": "logits",
                            "access": "write",
                        },
                        {
                            "symbol": "tokens",
                            "buffer": "tokens:decode:0000",
                            "role": "generated_tokens",
                            "access": "write",
                        },
                    ],
                }
            ],
            "kvCacheSchedule": {
                "status": "bound",
                "cacheWriteCount": 1,
                "cacheReadCount": 1,
                "layerCoverage": {
                    "layerCount": 1,
                    "coveredLayerCount": 1,
                    "coveredLayers": [0],
                },
                "operations": [
                    {
                        "launchIndex": 0,
                        "read": {
                            "keyBuffer": "state:kv_cache:key",
                            "valueBuffer": "state:kv_cache:value",
                            "cacheBuffer": "state:kv_cache",
                            "slidingWindowSource": "prefill_full_context",
                        },
                        "write": {
                            "keyBuffer": "state:kv_cache:key",
                            "valueBuffer": "state:kv_cache:value",
                            "cacheBuffer": "state:kv_cache",
                            "positionSource": "decode_position",
                        },
                    }
                ],
            },
            "transcriptCaptureSchedule": {
                "status": "bound",
                "expectedActualDecodeSteps": 1,
                "emitters": [
                    {
                        "kind": "logits_digest",
                        "launchIndex": 0,
                        "buffer": "logits:decode:0000:sample",
                    },
                    {
                        "kind": "generated_token",
                        "launchIndex": 0,
                        "buffer": "tokens:decode:0000",
                        "logitsBuffer": "logits:decode:0000:sample",
                    },
                ],
            },
        }
    }
    manifest_preflight = {"status": "passed"}
    return compile_root, plan, runtime_config, scheduler, manifest_preflight


class Int4PleSchedulerReadinessTests(unittest.TestCase):
    def test_program_bundle_logits_projection_preserves_step_digests(self) -> None:
        digests = program_bundle_logits_digests(
            {
                "logits": {
                    "steps": [
                        {
                            "index": 0,
                            "tokenId": 818,
                            "inputTokenCount": 15,
                            "dtype": "f32",
                            "elementCount": 262144,
                            "digest": (
                                "sha256:"
                                "9ef010995a3d04c88631f2e23444ebb5925bd383cf58910a483c5d89aea25066"
                            ),
                        }
                    ]
                }
            }
        )

        self.assertEqual(len(digests), 1)
        self.assertEqual(digests[0]["phase"], "decode")
        self.assertEqual(digests[0]["contextTokenCount"], 15)
        self.assertEqual(digests[0]["selectedTokenId"], 818)
        self.assertEqual(digests[0]["shape"], [262144])
        self.assertEqual(digests[0]["byteLength"], 262144 * 4)
        self.assertEqual(
            digests[0]["sha256"],
            "9ef010995a3d04c88631f2e23444ebb5925bd383cf58910a483c5d89aea25066",
        )

    def test_scheduler_readiness_blocks_without_symbol_dataflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            compile_root = root / "compile"
            for target in ("residual", "sample"):
                (compile_root / target).mkdir(parents=True)
                (compile_root / target / "layout.csl").write_text("", encoding="utf-8")
                (compile_root / target / "pe_program.csl").write_text("", encoding="utf-8")
                (compile_root / "compiled" / target).mkdir(parents=True)
                (compile_root / "compiled" / target / "out.json").write_text(
                    "{}\n",
                    encoding="utf-8",
                )

            plan_path = root / "simulator-plan.json"
            plan = {
                "inputs": {
                    "compileTargets": [
                        {
                            "name": "residual",
                            "layout": "residual/layout.csl",
                            "peProgram": "residual/pe_program.csl",
                        },
                        {
                            "name": "sample",
                            "layout": "sample/layout.csl",
                            "peProgram": "sample/pe_program.csl",
                        },
                    ]
                },
                "runtime": {
                    "prefillLaunchCount": 2,
                    "decodeLaunchCount": 2,
                    "maxDecodeTokens": 8,
                    "weightMappingCount": 1,
                    "stateBufferCount": 1,
                },
            }
            write_json(plan_path, plan)
            write_json(
                root / "host-plan.json",
                {
                    "hostPlan": {
                        "phases": {
                            "prefill": [{"kernelName": "residual", "repeat": 1}],
                            "decode": [{"kernelName": "sample", "repeat": 1}],
                        },
                        "kernels": [
                            {"name": "residual", "pattern": "element_wise", "count": 1},
                            {"name": "sample", "pattern": "sample", "count": 1},
                        ],
                    }
                },
            )
            transcript_path = root / "reference-transcript.json"
            write_json(transcript_path, {"kvCache": {"mode": "digest", "layerDigestCount": 35}})
            runtime_config = {
                "weightIdentity": {"requiredWeightCount": 1, "missingWeightCount": 0},
                "weightMappings": [{"weightKey": "layer.0.self_attn.q_proj"}],
                "stateBuffers": [{"kind": "kv_cache", "name": "kv_cache"}],
                "hostIoLayout": [
                    {"bufferRole": "weight", "sourceIdentity": {"synthetic": False}},
                    {"bufferRole": "state"},
                ],
            }
            export = {
                "inputSetComponents": {"tokenCount": 15},
                "decodeTranscript": {
                    "status": "output_ready",
                    "requestedDecodeSteps": 1,
                    "actualDecodeSteps": 1,
                    "stopReason": "decode_steps_exhausted",
                    "transcript": {
                        "path": str(transcript_path),
                        "sha256": "unused",
                    },
                    "generatedTokenIds": {"tokenCount": 1},
                    "logitsDigests": [
                        {
                            "stepIndex": 0,
                            "phase": "decode",
                            "selectedTokenId": 7,
                            "shape": [262144],
                            "sha256": "abc",
                        }
                    ],
                },
            }

            readiness = runner.scheduler_readiness(
                plan_path=plan_path,
                plan=plan,
                runtime_config=runtime_config,
                export=export,
                reference_export_path=root / "reference-export.json",
                compile_root=compile_root,
            )

        self.assertEqual(readiness["status"], "blocked_missing_runtime_scheduler")
        self.assertTrue(readiness["readiness"]["compileTargetsReady"])
        self.assertTrue(readiness["readiness"]["weightMappingsReady"])
        self.assertTrue(readiness["readiness"]["referenceTranscriptReady"])
        self.assertTrue(readiness["readiness"]["kvReferenceReady"])
        self.assertFalse(readiness["readiness"]["launchesCarrySymbolDataflow"])
        schedule = readiness["hostPlan"]["launchSchedule"]
        self.assertEqual(schedule["status"], "blocked_missing_symbol_dataflow")
        self.assertEqual(schedule["launchDescriptorCount"], 2)
        self.assertEqual(schedule["scheduledInvocationCount"], 2)
        self.assertEqual(schedule["phaseDescriptorCounts"], {"decode": 1, "prefill": 1})
        self.assertEqual(schedule["kernelDescriptorCounts"], {"residual": 1, "sample": 1})
        self.assertEqual(schedule["launches"][0]["phase"], "prefill")
        self.assertEqual(schedule["launches"][1]["phase"], "decode")
        self.assertFalse(schedule["allLaunchesCarrySymbolDataflow"])
        self.assertIn(
            "hostplan_launches_lack_symbol_dataflow_bindings",
            readiness["blockers"],
        )

    def test_scheduler_readiness_binds_dataflow_from_normalized_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            compile_root = root / "compile"
            targets = (
                "embed",
                "gemv",
                "attn_decode",
                "lm_head_gemv_stable",
                "sample",
            )
            for target in targets:
                (compile_root / target).mkdir(parents=True)
                (compile_root / target / "layout.csl").write_text("", encoding="utf-8")
                (compile_root / target / "pe_program.csl").write_text("", encoding="utf-8")
                (compile_root / "compiled" / target).mkdir(parents=True)
                (compile_root / "compiled" / target / "out.json").write_text(
                    "{}\n",
                    encoding="utf-8",
                )

            plan_path = root / "simulator-plan.json"
            plan = {
                "inputs": {
                    "compileTargets": [
                        {
                            "name": target,
                            "layout": f"{target}/layout.csl",
                            "peProgram": f"{target}/pe_program.csl",
                        }
                        for target in targets
                    ]
                },
                "runtime": {
                    "prefillLaunchCount": 1,
                    "decodeLaunchCount": 21,
                    "maxDecodeTokens": 3,
                    "weightMappingCount": 6,
                    "stateBufferCount": 3,
                },
            }
            write_json(plan_path, plan)
            write_json(
                root / "host-plan.json",
                {
                    "hostPlan": {
                        "phases": {
                            "prefill": [{"kernelName": "embed", "repeat": 1}],
                            "decode": [
                                {"kernelName": "gemv", "repeat": 1},
                                {"kernelName": "gemv", "repeat": 1},
                                {"kernelName": "gemv", "repeat": 1},
                                {
                                    "kernelName": "attn_decode",
                                    "repeat": 1,
                                    "attentionType": "sliding",
                                    "slidingWindowSize": 8,
                                    "currentPosSource": "decode_position",
                                },
                                {"kernelName": "gemv", "repeat": 1},
                                {"kernelName": "lm_head_gemv_stable", "repeat": 1},
                                {"kernelName": "sample", "repeat": 1},
                            ],
                        },
                        "kernels": [
                            {"name": "embed", "pattern": "gather", "count": 1},
                            {"name": "gemv", "pattern": "fused_gemv_dequant", "count": 4},
                            {
                                "name": "attn_decode",
                                "pattern": "attention_decode",
                                "count": 1,
                            },
                            {
                                "name": "lm_head_gemv_stable",
                                "pattern": "fused_gemv_dequant",
                                "count": 1,
                            },
                            {"name": "sample", "pattern": "sample", "count": 1},
                        ],
                    }
                },
            )
            write_json(
                root / "normalized-execution-v1.json",
                {
                    "modelConfig": {"numLayers": 1},
                    "steps": [
                        {
                            "kernelKey": "embed",
                            "name": "embed",
                            "op": "embed",
                            "phase": "prefill",
                            "weightsKey": "embed_tokens",
                        },
                        {
                            "kernelKey": "gemv",
                            "name": "q_proj",
                            "op": "matmul_q4k",
                            "phase": "decode",
                            "weightsKey": "layer.0.self_attn.q_proj",
                        },
                        {
                            "kernelKey": "gemv",
                            "name": "k_proj",
                            "op": "matmul_q4k",
                            "phase": "decode",
                            "weightsKey": "layer.0.self_attn.k_proj",
                        },
                        {
                            "kernelKey": "gemv",
                            "name": "v_proj",
                            "op": "matmul_q4k",
                            "phase": "decode",
                            "weightsKey": "layer.0.self_attn.v_proj",
                        },
                        {
                            "kernelKey": "attn_decode",
                            "name": "attention",
                            "op": "attention_decode",
                            "phase": "decode",
                        },
                        {
                            "kernelKey": "gemv",
                            "name": "o_proj",
                            "op": "matmul_q4k",
                            "phase": "decode",
                            "weightsKey": "layer.0.self_attn.o_proj",
                        },
                        {
                            "kernelKey": "lm_head_gemv_stable",
                            "name": "lm_head",
                            "op": "matmul_q4k",
                            "phase": "decode",
                            "weightsKey": "lm_head",
                        },
                        {
                            "kernelKey": "sample",
                            "name": "sample",
                            "op": "sample",
                            "phase": "decode",
                        },
                    ],
                },
            )
            transcript_path = root / "reference-transcript.json"
            write_json(transcript_path, {"kvCache": {"mode": "digest", "layerDigestCount": 1}})
            weight_keys = [
                "embed_tokens",
                "layer.0.self_attn.q_proj",
                "layer.0.self_attn.k_proj",
                "layer.0.self_attn.v_proj",
                "layer.0.self_attn.o_proj",
                "lm_head",
            ]
            runtime_config = {
                "modelConfig": {"numLayers": 1},
                "weightIdentity": {"requiredWeightCount": 6, "missingWeightCount": 0},
                "weightMappings": [
                    {
                        "weightKey": key,
                        "tensor": key,
                        "dtype": "u8_q4k",
                        "shape": [1],
                        "byteSize": 1,
                        "sha256": "0" * 64,
                    }
                    for key in weight_keys
                ],
                "stateBuffers": [
                    {"kind": "kv_cache", "name": "kv_cache"},
                    {"kind": "position", "name": "decode_position"},
                    {"kind": "position", "name": "sliding_window"},
                ],
                "hostIoLayout": [
                    {"bufferRole": "weight", "sourceIdentity": {"synthetic": False}},
                    {"bufferRole": "state"},
                ],
            }
            export = {
                "inputSetComponents": {"tokenCount": 4},
                "decodeTranscript": {
                    "status": "output_ready",
                    "requestedDecodeSteps": 3,
                    "actualDecodeSteps": 3,
                    "stopReason": "decode_steps_exhausted",
                    "transcript": {
                        "path": str(transcript_path),
                        "sha256": "unused",
                    },
                    "generatedTokenIds": {"tokenCount": 3},
                    "logitsDigests": [
                        {
                            "stepIndex": step_index,
                            "phase": "decode",
                            "selectedTokenId": 7,
                            "shape": [16],
                            "sha256": "abc",
                        }
                        for step_index in range(3)
                    ],
                },
            }

            readiness = runner.scheduler_readiness(
                plan_path=plan_path,
                plan=plan,
                runtime_config=runtime_config,
                export=export,
                reference_export_path=root / "reference-export.json",
                compile_root=compile_root,
            )

        self.assertEqual(
            readiness["status"],
            "blocked_missing_runtime_scheduler",
        )
        self.assertTrue(readiness["readiness"]["launchesCarrySymbolDataflow"])
        self.assertTrue(readiness["readiness"]["activationRoutingBound"])
        self.assertTrue(readiness["readiness"]["kvReadWriteScheduleBound"])
        self.assertTrue(readiness["readiness"]["transcriptEmittersBound"])
        self.assertFalse(readiness["readiness"]["hostPlanExecutorValidatorPassed"])
        self.assertFalse(readiness["readiness"]["hostPlanExecutionPlanReady"])
        self.assertFalse(readiness["readiness"]["fullModelRuntimeExecutorBound"])
        self.assertEqual(
            readiness["blockers"],
            ["hostplan_executor_validator_not_passed"],
        )
        scheduler = readiness["hostPlan"]["runtimeScheduler"]
        self.assertEqual(scheduler["status"], "bound")
        self.assertEqual(scheduler["runtimeExpansion"]["decodeIterationCount"], 3)
        self.assertEqual(scheduler["runtimeExpansion"]["runtimeLaunchCount"], 22)
        self.assertEqual(
            scheduler["transcriptCaptureSchedule"]["tokenEmitterCount"],
            3,
        )
        self.assertEqual(
            scheduler["transcriptCaptureSchedule"]["logitsEmitterCount"],
            3,
        )
        self.assertEqual(
            scheduler["kvCacheSchedule"]["layerCoverage"]["coveredLayerCount"],
            1,
        )
        validator = readiness["hostPlanExecutor"]["executorValidator"]
        self.assertEqual(validator["status"], "blocked")
        self.assertIn(
            "manifest_shape_preflight_not_passed:not_evaluated",
            validator["blockers"],
        )
        execution_plan = readiness["hostPlanExecutor"]["executionPlan"]
        self.assertEqual(execution_plan["status"], "blocked")
        self.assertIn(
            "executor_validator_not_passed:blocked",
            execution_plan["blockers"],
        )

    def test_executor_validator_passes_complete_symbol_dataflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            compile_root = root / "compile"
            target_params = {
                "embed": {
                    "width": "130",
                    "height": "127",
                    "hidden_size": "1536",
                    "num_tokens": "23",
                    "rows_per_pe": "16",
                },
                "tiled": {"P": "96", "Mt": "16", "Kt": "16", "Nt": "16"},
                "attn_head256": {
                    "block_size": "15",
                    "head_dim": "256",
                    "kv_len": "15",
                    "q_len": "15",
                },
                "attn_head512": {
                    "block_size": "15",
                    "head_dim": "512",
                    "kv_len": "15",
                    "q_len": "15",
                },
                "lm_head_gemv_stable": {
                    "width": "130",
                    "out_dim": "2017",
                    "in_dim_per_pe": "512",
                    "num_blocks_per_row": "2",
                },
                "sample": {"width": "130", "chunk_size": "2017"},
            }
            targets = tuple(target_params.keys())
            layout_exports = {
                "embed": [
                    ("indices", "[*]u32, true"),
                    ("table", "[*]f32, true"),
                    ("output", "[*]f32, true"),
                    ("compute", "fn()void"),
                ],
                "tiled": [
                    ("A", "[*]f32, true"),
                    ("B", "[*]u8, true"),
                    ("C", "[*]f32, true"),
                    ("compute", "fn()void"),
                ],
                "attn_head256": [
                    ("query", "[*]f32, true"),
                    ("key", "[*]f32, true"),
                    ("val", "[*]f32, true"),
                    ("output", "[*]f32, true"),
                    ("compute", "fn()void"),
                ],
                "attn_head512": [
                    ("query", "[*]f32, true"),
                    ("key", "[*]f32, true"),
                    ("val", "[*]f32, true"),
                    ("output", "[*]f32, true"),
                    ("compute", "fn()void"),
                ],
                "lm_head_gemv_stable": [
                    ("activation", "[*]f32, true"),
                    ("weight", "[*]u8, true"),
                    ("output", "[*]f32, true"),
                    ("compute", "fn()void"),
                ],
                "sample": [
                    ("logits", "[*]f32, true"),
                    ("tokens", "[*]u32, true"),
                    ("compute", "fn()void"),
                ],
            }
            for target, params in target_params.items():
                (compile_root / target).mkdir(parents=True)
                write_layout(
                    compile_root / target / "layout.csl",
                    exports=layout_exports[target],
                )
                (compile_root / target / "pe_program.csl").write_text("", encoding="utf-8")
                write_json(compile_root / "compiled" / target / "out.json", {"params": params})

            plan_path = root / "simulator-plan.json"
            plan = {
                "inputs": {
                    "compileTargets": [
                        {
                            "name": target,
                            "layout": f"{target}/layout.csl",
                            "peProgram": f"{target}/pe_program.csl",
                        }
                        for target in targets
                    ]
                },
                "runtime": {
                    "prefillLaunchCount": 1,
                    "decodeLaunchCount": 6,
                    "maxDecodeTokens": 1,
                    "weightMappingCount": 4,
                    "stateBufferCount": 1,
                },
            }
            write_json(plan_path, plan)
            write_json(
                root / "host-plan.json",
                {
                    "hostPlan": {
                        "phases": {
                            "prefill": [{"kernelName": "embed", "repeat": 1}],
                            "decode": [
                                {"kernelName": "embed", "repeat": 1},
                                {"kernelName": "tiled", "repeat": 1},
                                {"kernelName": "attn_head256", "repeat": 1},
                                {"kernelName": "tiled", "repeat": 1},
                                {"kernelName": "lm_head_gemv_stable", "repeat": 1},
                                {"kernelName": "sample", "repeat": 1},
                            ],
                        },
                        "kernels": [
                            {"name": "embed", "pattern": "gather", "count": 1},
                            {"name": "tiled", "pattern": "tiled_matmul", "count": 1},
                            {
                                "name": "attn_head256",
                                "pattern": "attention_tiled",
                                "count": 1,
                            },
                            {
                                "name": "lm_head_gemv_stable",
                                "pattern": "fused_gemv_dequant",
                                "count": 1,
                            },
                            {"name": "sample", "pattern": "sample", "count": 1},
                        ],
                    }
                },
            )
            write_json(
                root / "normalized-execution-v1.json",
                {
                    "modelConfig": {"numLayers": 1},
                    "steps": [
                        {
                            "kernelKey": "embed",
                            "name": "embed",
                            "op": "embed",
                            "phase": "prefill",
                            "weightsKey": "embed_tokens",
                        },
                        {
                            "kernelKey": "embed",
                            "name": "embed",
                            "op": "embed",
                            "phase": "decode",
                            "weightsKey": "embed_tokens",
                        },
                        {
                            "kernelKey": "tiled",
                            "name": "q_proj",
                            "op": "matmul_q4k",
                            "phase": "decode",
                            "weightsKey": "layer.0.self_attn.q_proj",
                        },
                        {
                            "kernelKey": "attn_head256",
                            "name": "attention",
                            "op": "attention_prefill",
                            "phase": "decode",
                        },
                        {
                            "kernelKey": "tiled",
                            "name": "o_proj",
                            "op": "matmul_q4k",
                            "phase": "decode",
                            "weightsKey": "layer.0.self_attn.o_proj",
                        },
                        {
                            "kernelKey": "lm_head_gemv_stable",
                            "name": "lm_head",
                            "op": "matmul_q4k",
                            "phase": "decode",
                            "weightsKey": "lm_head",
                        },
                        {
                            "kernelKey": "sample",
                            "name": "sample",
                            "op": "sample",
                            "phase": "decode",
                        },
                    ],
                },
            )
            transcript_path = root / "reference-transcript.json"
            write_json(transcript_path, {"kvCache": {"mode": "digest", "layerDigestCount": 1}})
            runtime_config = {
                "memoryPlan": {"grid": {"width": 130, "height": 127}},
                "modelConfig": {
                    "hiddenDim": 1536,
                    "headDim": 256,
                    "globalHeadDim": 512,
                    "maxSeqLen": 23,
                    "numLayers": 1,
                    "pleVocabSize": 262144,
                    "vocabSize": 262144,
                },
                "weightIdentity": {"requiredWeightCount": 4, "missingWeightCount": 0},
                "weightMappings": [
                    {
                        "weightKey": key,
                        "tensor": key,
                        "dtype": "u8_q4k",
                        "shape": [1],
                        "byteSize": 1,
                        "sha256": "0" * 64,
                    }
                    for key in (
                        "embed_tokens",
                        "layer.0.self_attn.q_proj",
                        "layer.0.self_attn.o_proj",
                        "lm_head",
                    )
                ],
                "stateBuffers": [{"kind": "kv_cache", "name": "kv_cache"}],
                "hostIoLayout": [
                    {"bufferRole": "weight", "sourceIdentity": {"synthetic": False}},
                    {"bufferRole": "state"},
                ],
            }
            export = {
                "inputSetComponents": {"tokenCount": 15},
                "decodeTranscript": {
                    "status": "output_ready",
                    "requestedDecodeSteps": 1,
                    "actualDecodeSteps": 1,
                    "stopReason": "decode_steps_exhausted",
                    "transcript": {
                        "path": str(transcript_path),
                        "sha256": "unused",
                    },
                    "generatedTokenIds": {"tokenCount": 1},
                    "logitsDigests": [
                        {
                            "stepIndex": 0,
                            "phase": "decode",
                            "selectedTokenId": 7,
                            "shape": [262144],
                            "sha256": "abc",
                        }
                    ],
                },
            }

            readiness = runner.scheduler_readiness(
                plan_path=plan_path,
                plan=plan,
                runtime_config=runtime_config,
                export=export,
                reference_export_path=root / "reference-export.json",
                compile_root=compile_root,
            )

        validator = readiness["hostPlanExecutor"]["executorValidator"]
        self.assertEqual(validator["status"], "passed", validator["blockers"])
        self.assertEqual(validator["blockers"], [])
        self.assertTrue(readiness["readiness"]["hostPlanExecutorValidatorPassed"])
        self.assertTrue(readiness["readiness"]["hostPlanExecutionPlanReady"])
        self.assertEqual(validator["launchCount"], 7)
        self.assertEqual(validator["kvCacheSchedule"]["cacheWriteCount"], 1)
        self.assertEqual(
            validator["transcriptCaptureSchedule"]["tokenEmitterCount"],
            1,
        )
        execution_plan = readiness["hostPlanExecutor"]["executionPlan"]
        self.assertEqual(execution_plan["status"], "planned", execution_plan["blockers"])
        self.assertEqual(execution_plan["targetSessionCount"], 5)
        self.assertEqual(execution_plan["launchCount"], 7)
        self.assertEqual(
            execution_plan["targetSessions"][0]["launchFunction"],
            "compute",
        )
        self.assertEqual(
            execution_plan["bufferPlan"]["producedBufferCount"],
            validator["producedBufferCount"],
        )
        self.assertEqual(
            execution_plan["bufferPlan"]["declaredStateRoots"],
            ["kv_cache"],
        )
        buffer_plan = execution_plan["bufferPlan"]
        buffers = {item["buffer"]: item for item in buffer_plan["buffers"]}
        self.assertEqual(
            buffers["activation:prefill:0000:global:embed"]["plannedElementCount"],
            1536,
        )
        self.assertEqual(
            buffers["logits:decode:0005:lm_head"]["plannedElementCount"],
            262144,
        )
        self.assertEqual(
            buffers["tokens:decode:0006"]["dtype"],
            "u32",
        )

    def test_execution_plan_blocks_on_unexported_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            compile_root = root / "compile"
            (compile_root / "embed").mkdir(parents=True)
            write_layout(
                compile_root / "embed" / "layout.csl",
                exports=[
                    ("indices", "[*]u32, true"),
                    ("output", "[*]f32, true"),
                    ("compute", "fn()void"),
                ],
            )
            write_json(compile_root / "compiled" / "embed" / "out.json", {"params": {}})

            execution_plan = build_hostplan_execution_plan(
                plan={
                    "inputs": {
                        "compileTargets": [
                            {
                                "name": "embed",
                                "layout": "embed/layout.csl",
                                "peProgram": "embed/pe_program.csl",
                            }
                        ]
                    }
                },
                compile_root=compile_root,
                runtime_config={"stateBuffers": [{"kind": "kv_cache", "name": "kv_cache"}]},
                scheduler={
                    "hostPlan": {
                        "runtimeScheduler": {
                            "status": "bound",
                            "launches": [
                                {
                                    "launchIndex": 0,
                                    "kernelName": "embed",
                                    "phase": "prefill",
                                    "inputs": [
                                        {
                                            "symbol": "indices",
                                            "buffer": "input:prompt_token_ids",
                                            "role": "tokenized_prompt",
                                            "access": "read",
                                        },
                                        {
                                            "symbol": "table",
                                            "buffer": "weight:embed_tokens",
                                            "role": "weight",
                                            "access": "read",
                                        },
                                    ],
                                    "outputs": [
                                        {
                                            "symbol": "output",
                                            "buffer": "activation:prefill:0000:global:embed",
                                            "role": "activation",
                                            "access": "write",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                },
                executor_validator={
                    "status": "passed",
                    "producedBufferCount": 2,
                },
            )

        self.assertEqual(execution_plan["status"], "blocked")
        self.assertIn(
            "launch[0].input_symbol_not_exported:embed.table",
            execution_plan["blockers"],
        )

    def test_executor_runtime_bootstrap_resolves_planned_launches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "progress.jsonl"
            execution_plan = {
                "status": "planned",
                "bufferPlan": {"bufferCount": 3},
                "targetSessions": [
                    {
                        "targetName": "embed",
                        "compileDir": "/tmp/embed",
                        "launchFunction": "compute",
                        "requiredInputSymbols": ["indices", "table"],
                        "requiredOutputSymbols": ["output"],
                    },
                    {
                        "targetName": "sample",
                        "compileDir": "/tmp/sample",
                        "launchFunction": "compute",
                        "requiredInputSymbols": ["logits"],
                        "requiredOutputSymbols": ["tokens"],
                    },
                ],
                "launches": [
                    {
                        "launchIndex": 0,
                        "targetName": "embed",
                        "launchFunction": "compute",
                        "phase": "prefill",
                        "inputBindings": [
                            {
                                "symbol": "indices",
                                "buffer": "input:prompt_token_ids",
                                "role": "tokenized_prompt",
                                "access": "read",
                            },
                            {
                                "symbol": "table",
                                "buffer": "weight:embed_tokens",
                                "role": "weight",
                                "access": "read",
                            },
                        ],
                        "outputBindings": [
                            {
                                "symbol": "output",
                                "buffer": "activation:prefill:0000:global:embed",
                                "role": "activation",
                                "access": "write",
                            }
                        ],
                        "runtimeActions": [{"kind": "launch", "functionName": "compute"}],
                    },
                    {
                        "launchIndex": 1,
                        "targetName": "sample",
                        "launchFunction": "compute",
                        "phase": "decode",
                        "decodeStepIndex": 0,
                        "inputBindings": [
                            {
                                "symbol": "logits",
                                "buffer": "logits:decode:0005:lm_head",
                                "role": "logits",
                                "access": "read",
                            }
                        ],
                        "outputBindings": [
                            {
                                "symbol": "tokens",
                                "buffer": "tokens:decode:0006",
                                "role": "generated_tokens",
                                "access": "write",
                            }
                        ],
                        "runtimeActions": [{"kind": "launch", "functionName": "compute"}],
                    },
                ],
            }

            def fake_probe_session(
                *,
                target_session: dict[str, object],
                progress_path: Path,
                cmaddr: str | None,
            ) -> dict[str, object]:
                del progress_path, cmaddr
                symbols = (
                    list(target_session["requiredInputSymbols"])
                    + list(target_session["requiredOutputSymbols"])
                )
                return {
                    "status": "resolved",
                    "targetName": target_session["targetName"],
                    "compileDir": target_session["compileDir"],
                    "launchFunction": target_session["launchFunction"],
                    "resolvedSymbols": {
                        str(symbol): index + 1 for index, symbol in enumerate(symbols)
                    },
                    "blockers": [],
                }

            bootstrap = runner.execute_hostplan_runtime_bootstrap(
                execution_plan=execution_plan,
                progress_path=progress_path,
                cmaddr=None,
                probe_session=fake_probe_session,
            )

        self.assertEqual(bootstrap["status"], "ready_for_tensor_movement")
        self.assertEqual(bootstrap["targetSessionsLoadedCount"], 2)
        self.assertEqual(bootstrap["resolvedLaunchCount"], 2)
        self.assertEqual(
            bootstrap["launches"][0]["resolvedInputs"][0]["symbolId"],
            1,
        )
        self.assertEqual(
            bootstrap["launches"][1]["resolvedOutputs"][0]["symbolId"],
            2,
        )

    def test_executor_runtime_bootstrap_blocks_on_missing_symbol_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "progress.jsonl"
            execution_plan = {
                "status": "planned",
                "bufferPlan": {"bufferCount": 1},
                "targetSessions": [
                    {
                        "targetName": "embed",
                        "compileDir": "/tmp/embed",
                        "launchFunction": "compute",
                        "requiredInputSymbols": ["indices"],
                        "requiredOutputSymbols": ["output"],
                    }
                ],
                "launches": [
                    {
                        "launchIndex": 0,
                        "targetName": "embed",
                        "launchFunction": "compute",
                        "phase": "prefill",
                        "inputBindings": [
                            {
                                "symbol": "indices",
                                "buffer": "input:prompt_token_ids",
                                "role": "tokenized_prompt",
                                "access": "read",
                            }
                        ],
                        "outputBindings": [
                            {
                                "symbol": "output",
                                "buffer": "activation:prefill:0000:global:embed",
                                "role": "activation",
                                "access": "write",
                            }
                        ],
                        "runtimeActions": [{"kind": "launch", "functionName": "compute"}],
                    }
                ],
            }

            def fake_probe_session(
                *,
                target_session: dict[str, object],
                progress_path: Path,
                cmaddr: str | None,
            ) -> dict[str, object]:
                del target_session, progress_path, cmaddr
                return {
                    "status": "resolved",
                    "targetName": "embed",
                    "compileDir": "/tmp/embed",
                    "launchFunction": "compute",
                    "resolvedSymbols": {"indices": 7},
                    "blockers": [],
                }

            bootstrap = runner.execute_hostplan_runtime_bootstrap(
                execution_plan=execution_plan,
                progress_path=progress_path,
                cmaddr=None,
                probe_session=fake_probe_session,
            )

        self.assertEqual(bootstrap["status"], "blocked")
        self.assertIn(
            "launch[0].output_symbol_id_missing:embed.output",
            bootstrap["blockers"],
        )

    def test_validator_blocks_on_unresolved_binding_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (
                compile_root,
                plan,
                runtime_config,
                scheduler,
                manifest_preflight,
            ) = make_valid_executor_validator_fixture(Path(tmpdir))
            launch = scheduler["runtimeScheduler"]["launches"][0]
            launch["inputs"][0]["symbol"] = "prompt_typo"

            validator = validate_hostplan_executor(
                plan=plan,
                compile_root=compile_root,
                runtime_config=runtime_config,
                scheduler=scheduler,
                manifest_preflight=manifest_preflight,
            )

        self.assertEqual(validator["status"], "blocked")
        self.assertIn(
            "launch[0].inputs[0].symbol_unresolved:prompt_typo",
            validator["blockers"],
        )

    def test_validator_blocks_duplicate_launch_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (
                compile_root,
                plan,
                runtime_config,
                scheduler,
                manifest_preflight,
            ) = make_valid_executor_validator_fixture(Path(tmpdir))
            duplicate = clone_json(scheduler["runtimeScheduler"]["launches"][0])
            scheduler["runtimeScheduler"]["launches"].append(duplicate)

            validator = validate_hostplan_executor(
                plan=plan,
                compile_root=compile_root,
                runtime_config=runtime_config,
                scheduler=scheduler,
                manifest_preflight=manifest_preflight,
            )

        self.assertEqual(validator["status"], "blocked")
        self.assertIn(
            "launch[1].launchIndex_duplicate:0",
            validator["blockers"],
        )

    def test_validator_blocks_missing_transcript_and_kv_buffers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (
                compile_root,
                plan,
                runtime_config,
                scheduler,
                manifest_preflight,
            ) = make_valid_executor_validator_fixture(Path(tmpdir))
            emitters = scheduler["runtimeScheduler"]["transcriptCaptureSchedule"]["emitters"]
            emitters[1]["buffer"] = ""
            emitters[1]["logitsBuffer"] = ""
            kv_op = scheduler["runtimeScheduler"]["kvCacheSchedule"]["operations"][0]
            kv_op["read"]["cacheBuffer"] = ""
            kv_op["write"]["positionSource"] = ""

            validator = validate_hostplan_executor(
                plan=plan,
                compile_root=compile_root,
                runtime_config=runtime_config,
                scheduler=scheduler,
                manifest_preflight=manifest_preflight,
            )

        self.assertEqual(validator["status"], "blocked")
        self.assertIn(
            "transcript.emitter[1].buffer_missing",
            validator["blockers"],
        )
        self.assertIn(
            "transcript.emitter[1].logitsBuffer_missing",
            validator["blockers"],
        )
        self.assertIn(
            "kv_cache.operations[0].read.cacheBuffer_missing",
            validator["blockers"],
        )
        self.assertIn(
            "kv_cache.operations[0].write.positionSource_missing",
            validator["blockers"],
        )

    def test_executor_preflight_rejects_smoke_shape_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            compile_root = root / "compile"
            target_params = {
                "embed": {
                    "width": "130",
                    "height": "1",
                    "hidden_size": "256",
                    "num_tokens": "23",
                    "rows_per_pe": "1",
                },
                "tiled": {
                    "width": "130",
                    "height": "127",
                    "Mt": "8",
                    "Kt": "8",
                    "Nt": "8",
                    "P": "2",
                },
                "lm_head_gemv_stable": {
                    "width": "130",
                    "height": "127",
                    "out_dim": "64",
                    "in_dim_per_pe": "512",
                    "num_blocks_per_row": "2",
                },
                "attn_head256": {
                    "width": "130",
                    "height": "127",
                    "head_dim": "256",
                    "q_len": "1",
                    "kv_len": "1",
                },
                "attn_head512": {
                    "width": "130",
                    "height": "127",
                    "head_dim": "512",
                    "q_len": "1",
                    "kv_len": "1",
                },
                "sample": {
                    "width": "130",
                    "height": "127",
                    "chunk_size": "2017",
                },
            }
            for target, params in target_params.items():
                out_json = compile_root / "compiled" / target / "out.json"
                write_json(out_json, {"params": params})

            preflight = runner.host_plan_executor_preflight(
                compile_root=compile_root,
                runtime_config={
                    "memoryPlan": {"grid": {"width": 130, "height": 127}},
                    "modelConfig": {
                        "hiddenDim": 1536,
                        "headDim": 256,
                        "globalHeadDim": 512,
                        "maxSeqLen": 23,
                        "pleVocabSize": 262144,
                        "vocabSize": 262144,
                    }
                },
                reference={"promptTokenCount": 15},
            )

        self.assertEqual(preflight["status"], "failed")
        self.assertIn(
            "embed_vocab_row_coverage:130<262144",
            preflight["blockers"],
        )
        self.assertIn(
            "attn_head256_prefill_q_len_coverage:1<15",
            preflight["blockers"],
        )
        self.assertIn(
            "lm_head_vocab_logit_coverage:8320<262144",
            preflight["blockers"],
        )
        self.assertTrue(
            any(
                check["id"] == "sample_vocab_logit_coverage"
                and check["passed"] is True
                for check in preflight["checks"]
            )
        )
        projection = preflight["manifestCompileParamProjection"]
        self.assertEqual(projection["status"], "projected")
        self.assertEqual(projection["params"]["embed"]["rows_per_pe"], 16)
        self.assertEqual(projection["params"]["tiled"], {"P": 96, "Mt": 16, "Kt": 16, "Nt": 16})
        self.assertEqual(projection["params"]["attn_head256"]["q_len"], 15)
        self.assertGreaterEqual(projection["coverage"]["lmHeadLogits"], 262144)

    def test_manifest_compile_param_patch_updates_simulator_plan_targets(self) -> None:
        simulator_plan = {
            "inputs": {
                "compileTargets": [
                    {
                        "name": "embed",
                        "layout": "embed/layout.csl",
                        "peProgram": "embed/pe_program.csl",
                        "compileParams": {
                            "height": 1,
                            "hidden_size": 256,
                            "num_tokens": 23,
                            "rows_per_pe": 1,
                        },
                    },
                    {
                        "name": "tiled",
                        "layout": "tiled/layout.csl",
                        "peProgram": "tiled/pe_program.csl",
                        "compileParams": {"P": 2, "Mt": 8, "Kt": 8, "Nt": 8},
                    },
                    {
                        "name": "attn_head256",
                        "layout": "attn_head256/layout.csl",
                        "peProgram": "attn_head256/pe_program.csl",
                        "compileParams": {
                            "block_size": 1,
                            "head_dim": 256,
                            "kv_len": 1,
                            "q_len": 1,
                        },
                    },
                    {
                        "name": "lm_head_gemv_stable",
                        "layout": "lm_head_gemv_stable/layout.csl",
                        "peProgram": "lm_head_gemv_stable/pe_program.csl",
                        "compileParams": {
                            "out_dim": 64,
                            "in_dim_per_pe": 512,
                            "num_blocks_per_row": 2,
                        },
                    },
                    {
                        "name": "sample",
                        "layout": "sample/layout.csl",
                        "peProgram": "sample/pe_program.csl",
                        "compileParams": {"chunk_size": 2017},
                    },
                ],
            },
        }

        result = apply_manifest_compile_params(
            simulator_plan=simulator_plan,
            runtime_config={
                "memoryPlan": {"grid": {"width": 130, "height": 127}},
                "modelConfig": {
                    "hiddenDim": 1536,
                    "headDim": 256,
                    "globalHeadDim": 512,
                    "maxSeqLen": 23,
                    "pleVocabSize": 262144,
                    "vocabSize": 262144,
                },
            },
            reference={"promptTokenCount": 15},
        )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["patchedTargetCount"], 5)
        self.assertEqual(result["unprojectedTargetNames"], [])
        targets = {
            target["name"]: target["compileParams"]
            for target in simulator_plan["inputs"]["compileTargets"]
        }
        self.assertEqual(
            targets["embed"],
            {
                "height": 127,
                "hidden_size": 1536,
                "num_tokens": 23,
                "rows_per_pe": 16,
            },
        )
        self.assertEqual(targets["tiled"], {"P": 96, "Mt": 16, "Kt": 16, "Nt": 16})
        self.assertEqual(targets["attn_head256"]["q_len"], 15)
        self.assertEqual(targets["lm_head_gemv_stable"]["out_dim"], 2017)
        self.assertEqual(targets["sample"]["chunk_size"], 2017)

    def test_manifest_compile_param_patch_holds_unsafe_targets_at_diagnostic(self) -> None:
        simulator_plan = {
            "inputs": {
                "compileTargets": [
                    {
                        "name": "embed",
                        "layout": "embed/layout.csl",
                        "peProgram": "embed/pe_program.csl",
                        "compileParams": {
                            "height": 1,
                            "hidden_size": 256,
                            "num_tokens": 23,
                            "rows_per_pe": 1,
                        },
                    },
                    {
                        "name": "tiled",
                        "layout": "tiled/layout.csl",
                        "peProgram": "tiled/pe_program.csl",
                        "compileParams": {"P": 2, "Mt": 8, "Kt": 8, "Nt": 8},
                    },
                ],
            },
        }

        result = apply_manifest_compile_params(
            simulator_plan=simulator_plan,
            runtime_config={
                "memoryPlan": {"grid": {"width": 130, "height": 127}},
                "modelConfig": {
                    "hiddenDim": 1536,
                    "headDim": 256,
                    "globalHeadDim": 512,
                    "maxSeqLen": 23,
                    "pleVocabSize": 262144,
                    "vocabSize": 262144,
                },
            },
            reference={"promptTokenCount": 15},
            manifest_unsafe_targets={
                "embed": "per_pe_table_and_output_exceed_pe_memory_budget",
            },
        )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["patchedTargetCount"], 1)
        held = result["heldDiagnosticTargets"]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["name"], "embed")
        self.assertEqual(
            held[0]["reason"], "per_pe_table_and_output_exceed_pe_memory_budget"
        )
        self.assertEqual(
            held[0]["retained"],
            {
                "height": 1,
                "hidden_size": 256,
                "num_tokens": 23,
                "rows_per_pe": 1,
            },
        )
        self.assertEqual(
            held[0]["projected"],
            {
                "height": 127,
                "hidden_size": 1536,
                "num_tokens": 23,
                "rows_per_pe": 16,
            },
        )
        targets = {
            target["name"]: target["compileParams"]
            for target in simulator_plan["inputs"]["compileTargets"]
        }
        # embed stays at diagnostic shape when held_unsafe
        self.assertEqual(
            targets["embed"],
            {
                "height": 1,
                "hidden_size": 256,
                "num_tokens": 23,
                "rows_per_pe": 1,
            },
        )
        # tiled still gets promoted
        self.assertEqual(targets["tiled"], {"P": 96, "Mt": 16, "Kt": 16, "Nt": 16})

    def test_manifest_compile_param_patch_surfaces_unprojected_targets(self) -> None:
        simulator_plan = {
            "inputs": {
                "compileTargets": [
                    {
                        "name": "embed",
                        "layout": "embed/layout.csl",
                        "peProgram": "embed/pe_program.csl",
                        "compileParams": {
                            "height": 1,
                            "hidden_size": 256,
                            "num_tokens": 23,
                            "rows_per_pe": 1,
                        },
                    },
                    {
                        "name": "lm_head_prefill_stable",
                        "layout": "lm_head_prefill_stable/layout.csl",
                        "peProgram": "lm_head_prefill_stable/pe_program.csl",
                        "compileParams": {"P": 2, "Mt": 8, "Kt": 8, "Nt": 8},
                    },
                    {
                        "name": "residual",
                        "layout": "residual/layout.csl",
                        "peProgram": "residual/pe_program.csl",
                    },
                ],
            },
        }

        result = apply_manifest_compile_params(
            simulator_plan=simulator_plan,
            runtime_config={
                "memoryPlan": {"grid": {"width": 130, "height": 127}},
                "modelConfig": {
                    "hiddenDim": 1536,
                    "headDim": 256,
                    "globalHeadDim": 512,
                    "maxSeqLen": 23,
                    "pleVocabSize": 262144,
                    "vocabSize": 262144,
                },
            },
            reference={"promptTokenCount": 15},
        )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["patchedTargetCount"], 1)
        self.assertEqual(
            result["unprojectedTargetNames"],
            ["lm_head_prefill_stable", "residual"],
        )


if __name__ == "__main__":
    unittest.main()
