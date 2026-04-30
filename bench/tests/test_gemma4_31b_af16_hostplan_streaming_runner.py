from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_runner_module():
    name = "gemma4_31b_af16_hostplan_streaming_runner"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name,
        REPO_ROOT
        / "bench/runners/csl-runners/"
        "gemma4_31b_af16_hostplan_streaming_runner.py",
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_session_module():
    name = "gemma4_31b_af16_session_runtime"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name,
        REPO_ROOT
        / "bench/runners/csl-runners/"
        "gemma4_31b_af16_session_runtime.py",
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _materialize_fixture(root: Path) -> dict[str, Path]:
    primary = root / "primary"
    primary.mkdir()
    (primary / "shard_00000.bin").write_bytes(b"0" * 16)
    (primary / "per_layer_inputs.perLayerModelProjection.layer0.f32").write_bytes(
        b"p" * 8
    )
    manifest = root / "af16" / "manifest.json"
    _write_json(
        manifest,
        {
            "modelId": "gemma-4-31b-it-text-q4k-ehf16-af16",
            "artifactIdentity": {
                "weightPackId": "wp",
                "shardSetHash": "sha256:" + "a" * 64,
            },
            "weightsRef": {"artifactRoot": "../primary"},
            "quantizationInfo": {
                "weights": "q4k",
                "embeddings": "f16",
                "lmHead": "q4k",
                "compute": "f16",
                "variantTag": "q4k-ehf16-af16",
            },
            "architecture": {"numLayers": 1, "hiddenSize": 4},
            "shards": [
                {
                    "index": 0,
                    "filename": "shard_00000.bin",
                    "size": 16,
                    "hash": "0" * 64,
                }
            ],
            "tensors": {
                "model.language_model.embed_tokens.weight": {
                    "dtype": "F16",
                    "shape": [8, 4],
                    "shard": 0,
                    "offset": 0,
                    "size": 16,
                    "role": "embedding",
                    "layout": "row_major",
                },
                "model.language_model.layers.0.self_attn.q_proj.weight": {
                    "dtype": "Q4_K_M",
                    "shape": [4, 4],
                    "shard": 0,
                    "offset": 0,
                    "size": 16,
                    "role": "attention_projection",
                    "layout": "q4k_row_major",
                },
                "model.language_model.layers.0.input_layernorm.weight": {
                    "dtype": "F16",
                    "shape": [4],
                    "shard": 0,
                    "offset": 0,
                    "size": 8,
                    "role": "rmsnorm",
                    "layout": "row_major",
                },
                "model.language_model.norm.weight": {
                    "dtype": "F16",
                    "shape": [4],
                    "shard": 0,
                    "offset": 0,
                    "size": 8,
                    "role": "rmsnorm",
                    "layout": "row_major",
                },
            },
        },
    )
    smoke = root / "smoke.json"
    _write_json(
        smoke,
        {
            "modelConfig": {"numLayers": 1},
            "steps": [
                {
                    "name": "embed_tokens",
                    "phase": "prefill",
                    "op": "embed",
                    "kernelKey": "embed",
                    "weightsKey": "embed_tokens",
                },
                {
                    "name": "ple_project",
                    "phase": "prefill",
                    "op": "ple_project",
                    "kernelKey": "ple_proj",
                    "weightsKey": "per_layer_inputs.perLayerModelProjection",
                },
                {
                    "name": "input_norm",
                    "phase": "prefill",
                    "op": "rmsnorm",
                    "kernelKey": "rmsnorm",
                },
                {
                    "name": "final_norm_prefill",
                    "phase": "prefill",
                    "op": "rmsnorm",
                    "kernelKey": "rmsnorm",
                    "weightsKey": "norm",
                },
                {
                    "name": "lm_head_prefill",
                    "phase": "prefill",
                    "op": "matmul",
                    "kernelKey": "lm_head_prefill_stable",
                    "weightsKey": "lm_head",
                },
                {
                    "name": "sample_prefill",
                    "phase": "prefill",
                    "op": "sample",
                    "kernelKey": "sample",
                },
                {
                    "name": "q_proj",
                    "phase": "decode",
                    "op": "matmul_q4k",
                    "kernelKey": "gemv",
                    "weightsKey": "layer.0.self_attn.q_proj",
                },
                {
                    "name": "final_norm",
                    "phase": "decode",
                    "op": "rmsnorm",
                    "kernelKey": "rmsnorm",
                    "weightsKey": "norm",
                },
                {
                    "name": "lm_head",
                    "phase": "decode",
                    "op": "matmul",
                    "kernelKey": "lm_head_prefill_stable",
                    "weightsKey": "lm_head",
                },
                {
                    "name": "sample",
                    "phase": "decode",
                    "op": "sample",
                    "kernelKey": "sample",
                },
            ],
        },
    )
    host_plan = root / "host-plan.json"
    _write_json(
        host_plan,
        {
            "hostPlan": {
                "phases": {
                    "prefill": [
                        {"kernelName": "embed"},
                        {"kernelName": "rmsnorm"},
                        {"kernelName": "lm_head_prefill_stable"},
                        {"kernelName": "sample"},
                    ],
                    "decode": [
                        {"kernelName": "gemv"},
                        {"kernelName": "rmsnorm"},
                        {"kernelName": "lm_head_prefill_stable"},
                        {"kernelName": "sample"},
                    ],
                }
            }
        },
    )
    summary = root / "summary.json"
    _write_json(
        summary,
        {
            "kernels": [
                {
                    "kernel": "sample",
                    "verdict": "blocked",
                    "blocker": "dry_run",
                }
            ],
            "totals": {
                "kernelCount": 1,
                "boundCount": 0,
                "blockedCount": 1,
            },
        },
    )
    simulator_plan = root / "simulator-plan.json"
    _write_json(
        simulator_plan,
        {
            "inputs": {
                "compileTargets": [
                    {
                        "name": "embed",
                        "layout": "embed/layout.csl",
                        "peProgram": "embed/pe.csl",
                        "compileParams": {"width": 1, "height": 1},
                        "metadata": {
                            "bindings": [
                                {
                                    "symbol": "indices",
                                    "elemType": "u32",
                                    "perPeShape": {"elements": "1"},
                                },
                                {
                                    "symbol": "table",
                                    "elemType": "f16",
                                    "perPeShape": {"elements": "1"},
                                },
                                {
                                    "symbol": "output",
                                    "elemType": "f16",
                                    "perPeShape": {"elements": "1"},
                                },
                            ]
                        },
                    },
                    {
                        "name": "sample",
                        "layout": "sample/layout.csl",
                        "peProgram": "sample/pe.csl",
                        "compileParams": {"width": 1, "height": 1},
                        "metadata": {
                            "bindings": [
                                {
                                    "symbol": "logits",
                                    "elemType": "f32",
                                    "perPeShape": {"elements": "1"},
                                },
                                {
                                    "symbol": "tokens",
                                    "elemType": "u32",
                                    "perPeShape": {"elements": "1"},
                                },
                            ]
                        },
                    },
                    {
                        "name": "gemv",
                        "layout": "gemv/layout.csl",
                        "peProgram": "gemv/pe.csl",
                        "compileParams": {"width": 1, "height": 1},
                        "metadata": {
                            "bindings": [
                                {
                                    "symbol": "activation",
                                    "elemType": "f16",
                                    "perPeShape": {"elements": "1"},
                                },
                                {
                                    "symbol": "weight",
                                    "elemType": "u8",
                                    "perPeShape": {"elements": "1"},
                                },
                                {
                                    "symbol": "output",
                                    "elemType": "f16",
                                    "perPeShape": {"elements": "1"},
                                },
                            ]
                        },
                    },
                    {
                        "name": "rmsnorm",
                        "layout": "rmsnorm/layout.csl",
                        "peProgram": "rmsnorm/pe.csl",
                        "compileParams": {"width": 1, "height": 1},
                        "metadata": {
                            "bindings": [
                                {
                                    "symbol": "input",
                                    "elemType": "f16",
                                    "perPeShape": {"elements": "1"},
                                },
                                {
                                    "symbol": "weight",
                                    "elemType": "f16",
                                    "perPeShape": {"elements": "1"},
                                },
                                {
                                    "symbol": "output",
                                    "elemType": "f16",
                                    "perPeShape": {"elements": "1"},
                                },
                            ]
                        },
                    },
                    {
                        "name": "lm_head_prefill_stable",
                        "layout": "lm_head_prefill_stable/layout.csl",
                        "peProgram": "lm_head_prefill_stable/pe.csl",
                        "compileParams": {"width": 1, "height": 1},
                        "metadata": {
                            "bindings": [
                                {
                                    "symbol": "a",
                                    "elemType": "f16",
                                    "perPeShape": {"elements": "1"},
                                },
                                {
                                    "symbol": "b",
                                    "elemType": "f32",
                                    "perPeShape": {"elements": "1"},
                                },
                                {
                                    "symbol": "c",
                                    "elemType": "f32",
                                    "perPeShape": {"elements": "1"},
                                },
                            ]
                        },
                    },
                ]
            }
        },
    )
    runtime_config = root / "runtime-config.json"
    _write_json(
        runtime_config,
        {
            "mode": "compile-only",
            "modelConfig": {
                "hiddenDim": 4,
                "maxSeqLen": 4,
                "numLayers": 1,
                "vocabSize": 8,
            },
            "memoryPlan": {"grid": {"width": 1, "height": 1}},
            "stateBuffers": [
                {"name": "kv_cache", "kind": "kv_cache", "bytesPerPe": 16},
                {"name": "decode_position", "kind": "position", "bytesPerPe": 4},
                {"name": "sliding_window", "kind": "position", "bytesPerPe": 4},
            ],
            "weightMappings": [],
            "hostIoLayout": [],
        },
    )
    for target in ("embed", "gemv", "rmsnorm", "lm_head_prefill_stable", "sample"):
        _write_json(
            root / "compile" / "compiled" / target / "out.json",
            {"params": {"width": 1, "height": 1}},
        )
    return {
        "manifest": manifest,
        "smoke": smoke,
        "host_plan": host_plan,
        "simulator_plan": simulator_plan,
        "runtime_config": runtime_config,
        "summary": summary,
        "compile_root": root / "compile",
        "out": root / "trace.json",
    }


class Gemma431BAf16HostPlanStreamingRunnerTest(unittest.TestCase):
    def test_weight_staging_resolves_weights_ref_and_sidecar(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            paths = _materialize_fixture(Path(tmp))
            plan = runner.build_weight_staging_plan(
                manifest_path=paths["manifest"],
                smoke_config_path=paths["smoke"],
            )
            self.assertTrue(plan["weightRootPresent"])
            self.assertEqual(plan["presentShardCount"], 1)
            self.assertEqual(plan["missingShards"], [])
            self.assertEqual(plan["sizeMismatches"], [])
            self.assertEqual(plan["unresolvedWeightKeys"], [])
            self.assertEqual(plan["resolvedWeightCount"], plan["requiredWeightCount"])
            self.assertEqual(
                plan["cslDtypeContract"]["fallbackPolicy"],
                "forbid_implicit_af32",
            )
            self.assertEqual(
                plan["cslDtypeContract"]["hostPlanActivationDtype"],
                "f16",
            )
            lm_head = next(
                item for item in plan["requiredWeights"]
                if item["weightKey"] == "lm_head"
            )
            self.assertEqual(lm_head["resolutionKind"], "manifest_tied_dense_lm_head")
            self.assertEqual(
                lm_head["matchedTensor"],
                "model.language_model.embed_tokens.weight",
            )

    def test_weight_staging_rejects_q4k_lm_head_against_tied_f16(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            paths = _materialize_fixture(Path(tmp))
            smoke = json.loads(paths["smoke"].read_text(encoding="utf-8"))
            for step in smoke["steps"]:
                if step.get("name") in {"lm_head", "lm_head_prefill"}:
                    step["op"] = "matmul_q4k"
                    step["kernelKey"] = "lm_head_gemv_stable"
            paths["smoke"].write_text(
                json.dumps(smoke, indent=2) + "\n",
                encoding="utf-8",
            )
            plan = runner.build_weight_staging_plan(
                manifest_path=paths["manifest"],
                smoke_config_path=paths["smoke"],
            )
            self.assertIn("lm_head", plan["unresolvedWeightKeys"])
            lm_head = next(
                item for item in plan["requiredWeights"]
                if item["weightKey"] == "lm_head"
            )
            self.assertEqual(
                lm_head["resolutionKind"],
                "invalid_lm_head_dtype_selection",
            )
            self.assertEqual(lm_head["actualDtype"], "F16")

    def test_dispatch_plan_expands_prefill_and_decode_steps(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            paths = _materialize_fixture(Path(tmp))
            plan = runner.build_dispatch_plan(
                smoke_config_path=paths["smoke"],
                host_plan_path=paths["host_plan"],
                prefill_token_count=2,
                decode_token_count=2,
            )
            self.assertEqual(plan["prefillTokenCount"], 2)
            self.assertEqual(plan["decodeTokenCount"], 2)
            self.assertGreater(plan["prefillStepCount"], 0)
            self.assertGreater(plan["decodeStepCount"], 0)
            self.assertEqual(plan["prefillSteps"][-2]["name"], "lm_head_prefill")
            self.assertEqual(plan["prefillSteps"][-1]["name"], "sample_prefill")
            self.assertEqual(plan["decodeByToken"][0]["tokenIndex"], 1)

    def test_session_scheduler_routes_ple_layers_by_layer_state(self) -> None:
        session = _load_session_module()
        dispatch_plan = {
            "decodeTokenCount": 0,
            "prefillSteps": [
                {
                    "phase": "prefill",
                    "layer": 0,
                    "name": "ple_gather",
                    "kernelKey": "ple_embed",
                    "weightKey": "per_layer_inputs.embedTokensPerLayer.layer0",
                },
                {
                    "phase": "prefill",
                    "layer": 1,
                    "name": "ple_gather",
                    "kernelKey": "ple_embed",
                    "weightKey": "per_layer_inputs.embedTokensPerLayer.layer1",
                },
                {
                    "phase": "prefill",
                    "layer": 0,
                    "name": "ple_project",
                    "kernelKey": "ple_proj",
                    "weightKey": (
                        "per_layer_inputs.perLayerModelProjection.layer0"
                    ),
                },
                {
                    "phase": "prefill",
                    "layer": 1,
                    "name": "ple_project",
                    "kernelKey": "ple_proj",
                    "weightKey": (
                        "per_layer_inputs.perLayerModelProjection.layer1"
                    ),
                },
                {
                    "phase": "prefill",
                    "layer": 0,
                    "name": "ple_norm",
                    "kernelKey": "ple_rmsnorm",
                    "weightKey": (
                        "per_layer_inputs.perLayerProjectionNorm.layer0"
                    ),
                },
                {
                    "phase": "prefill",
                    "layer": 1,
                    "name": "ple_norm",
                    "kernelKey": "ple_rmsnorm",
                    "weightKey": (
                        "per_layer_inputs.perLayerProjectionNorm.layer1"
                    ),
                },
            ],
            "decodeByToken": [],
        }
        runtime_config = {
            "modelConfig": {"numLayers": 2, "pleWidth": 256},
            "weightMappings": [
                {
                    "weightKey": (
                        "per_layer_inputs.perLayerModelProjection.layer0"
                    ),
                    "shape": [4, 256],
                },
                {
                    "weightKey": (
                        "per_layer_inputs.perLayerModelProjection.layer1"
                    ),
                    "shape": [4, 256],
                },
            ],
        }
        scheduler = session.build_real_session_scheduler(
            dispatch_plan=dispatch_plan,
            runtime_config=runtime_config,
        )
        launches = scheduler["launches"]
        self.assertEqual(
            launches[2]["inputs"][0]["buffer"],
            launches[0]["outputs"][0]["buffer"],
        )
        self.assertEqual(
            launches[3]["inputs"][0]["buffer"],
            launches[1]["outputs"][0]["buffer"],
        )
        self.assertEqual(launches[2]["inputs"][0]["matrixCols"], 256)
        self.assertEqual(launches[2]["outputs"][0]["matrixCols"], 4)
        self.assertEqual(
            launches[4]["inputs"][0]["buffer"],
            launches[2]["outputs"][0]["buffer"],
        )
        self.assertEqual(
            launches[5]["inputs"][0]["buffer"],
            launches[3]["outputs"][0]["buffer"],
        )

    def test_trace_records_current_blockers_without_refresh(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            paths = _materialize_fixture(Path(tmp))
            args = SimpleNamespace(
                source_doppler_manifest=paths["manifest"],
                smoke_config=paths["smoke"],
                host_plan=paths["host_plan"],
                simulator_plan=paths["simulator_plan"],
                runtime_config=paths["runtime_config"],
                compile_root=paths["compile_root"],
                per_kernel_summary=paths["summary"],
                prefill_token_count=2,
                decode_token_count=2,
                prompt_token_id=[],
                cmaddr="",
                execute=False,
                session_out_dir=Path(tmp) / "session",
                stop_after_launch=-1,
                refresh_per_kernel=False,
                refresh_jobs=1,
                refresh_resume=False,
                refresh_schedule="host-plan",
                refresh_timeout_seconds=600,
                refresh_out_dir=Path(tmp) / "per-kernel",
                out=paths["out"],
            )
            trace = runner.build_trace(args)
            blocker_classes = {b["class"] for b in trace["blockers"]}
            self.assertIn("manifest_kernel_dispatch_not_bound", blocker_classes)
            self.assertIn("execution_not_requested", blocker_classes)
            self.assertEqual(trace["perKernelRefresh"]["status"], "not_requested")
            self.assertEqual(
                trace["cslDtypeContract"]["fallbackPolicy"],
                "forbid_implicit_af32",
            )
            self.assertEqual(trace["realSessionRuntime"]["status"], "blocked")
            self.assertGreater(trace["realSessionRuntime"]["hostIoLayoutCount"], 0)
            scheduler = json.loads(
                Path(trace["realSessionRuntime"]["runtimeSchedulerPath"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(scheduler["status"], "bound")
            self.assertEqual(
                scheduler["transcriptCaptureSchedule"]["status"],
                "bound",
            )
            self.assertEqual(
                scheduler["transcriptCaptureSchedule"]["logitsEmitterCount"],
                2,
            )
            self.assertEqual(
                scheduler["transcriptCaptureSchedule"]["tokenEmitterCount"],
                2,
            )

    def test_refresh_records_sdk_preflight_blocker(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            paths = _materialize_fixture(Path(tmp))
            args = SimpleNamespace(
                source_doppler_manifest=paths["manifest"],
                smoke_config=paths["smoke"],
                host_plan=paths["host_plan"],
                simulator_plan=paths["simulator_plan"],
                runtime_config=paths["runtime_config"],
                compile_root=paths["compile_root"],
                per_kernel_summary=paths["summary"],
                prefill_token_count=2,
                decode_token_count=2,
                prompt_token_id=[],
                cmaddr="",
                execute=False,
                session_out_dir=Path(tmp) / "session",
                stop_after_launch=-1,
                refresh_per_kernel=True,
                refresh_jobs=4,
                refresh_resume=True,
                refresh_schedule="heavy-first",
                refresh_timeout_seconds=123,
                refresh_out_dir=Path(tmp) / "per-kernel",
                out=paths["out"],
            )
            original = runner.sdk_preflight
            runner.sdk_preflight = lambda: {
                "status": "blocked",
                "class": "sdk_python_import_failed",
            }
            try:
                trace = runner.build_trace(args)
            finally:
                runner.sdk_preflight = original
            self.assertEqual(trace["perKernelRefresh"]["status"], "blocked")
            self.assertIn("--jobs", trace["perKernelRefresh"]["command"])
            self.assertIn("4", trace["perKernelRefresh"]["command"])
            self.assertIn("--resume", trace["perKernelRefresh"]["command"])
            self.assertIn("heavy-first", trace["perKernelRefresh"]["command"])
            self.assertIn("--timeout-seconds", trace["perKernelRefresh"]["command"])
            self.assertIn("123", trace["perKernelRefresh"]["command"])
            self.assertEqual(
                trace["perKernelRefresh"]["blocker"]["class"],
                "sdk_python_import_failed",
            )
            blocker_classes = {b["class"] for b in trace["blockers"]}
            self.assertIn("sdk_python_import_failed", blocker_classes)
            self.assertNotIn(
                "manifest_kernel_dispatch_not_bound",
                blocker_classes,
            )

    def test_checkpoint_stop_is_not_reported_as_runtime_failure(self) -> None:
        runner = _load_runner_module()
        blockers = runner.build_blockers(
            weight_plan={
                "weightRootPresent": True,
                "missingShards": [],
                "sizeMismatches": [],
                "unresolvedWeightKeys": [],
            },
            per_kernel={"blockedKernels": [], "staleDryRunOnly": False},
            refresh={"requested": False, "status": "not_requested"},
            real_session={
                "status": "checkpoint_stopped",
                "blockers": ["execution_stopped_at_checkpoint"],
            },
            execute=True,
        )
        blocker_classes = {blocker["class"] for blocker in blockers}
        self.assertIn("execution_stopped_at_checkpoint", blocker_classes)
        self.assertNotIn("real_session_runtime_blocked", blocker_classes)


if __name__ == "__main__":
    unittest.main()
