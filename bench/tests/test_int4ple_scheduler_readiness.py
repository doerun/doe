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
            "blocked_missing_full_model_runtime_execution",
        )
        self.assertTrue(readiness["readiness"]["launchesCarrySymbolDataflow"])
        self.assertTrue(readiness["readiness"]["activationRoutingBound"])
        self.assertTrue(readiness["readiness"]["kvReadWriteScheduleBound"])
        self.assertTrue(readiness["readiness"]["transcriptEmittersBound"])
        self.assertFalse(readiness["readiness"]["fullModelRuntimeExecutorBound"])
        self.assertEqual(
            readiness["blockers"],
            ["full_model_prefill_decode_runtime_executor_missing"],
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


if __name__ == "__main__":
    unittest.main()
