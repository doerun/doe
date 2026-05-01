from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / "bench" / "runners" / "csl-runners"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

spec = importlib.util.spec_from_file_location(
    "int4ple_compile_target_sim_runner",
    RUNNER_DIR / "int4ple_compile_target_sim_runner.py",
)
assert spec is not None
assert spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def _load_launch_step_adapter_module():
    name = "int4ple_launch_step_adapter_for_tests"
    if name in sys.modules:
        return sys.modules[name]
    fake = types.ModuleType("sdkruntimepybind")

    class _MemcpyDataType:
        MEMCPY_32BIT = "MEMCPY_32BIT"
        MEMCPY_16BIT = "MEMCPY_16BIT"

    class _MemcpyOrder:
        ROW_MAJOR = "ROW_MAJOR"

    class _SdkRuntime:
        pass

    fake.MemcpyDataType = _MemcpyDataType
    fake.MemcpyOrder = _MemcpyOrder
    fake.SdkRuntime = _SdkRuntime
    sys.modules.setdefault("cerebras", types.ModuleType("cerebras"))
    sys.modules.setdefault("cerebras.sdk", types.ModuleType("cerebras.sdk"))
    sys.modules.setdefault(
        "cerebras.sdk.runtime",
        types.ModuleType("cerebras.sdk.runtime"),
    )
    sys.modules["cerebras.sdk.runtime.sdkruntimepybind"] = fake
    adapter_spec = importlib.util.spec_from_file_location(
        name,
        RUNNER_DIR / "int4ple_launch_step_adapter.py",
    )
    assert adapter_spec is not None
    assert adapter_spec.loader is not None
    mod = importlib.util.module_from_spec(adapter_spec)
    sys.modules[name] = mod
    adapter_spec.loader.exec_module(mod)
    return mod


class LaunchStepAdapterMemcpyPackingTest(unittest.TestCase):
    def test_f16_h2d_uses_writeable_mmap_payload_when_layout_matches(self) -> None:
        adapter = _load_launch_step_adapter_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            source = np.lib.format.open_memmap(
                path,
                mode="w+",
                dtype=np.float16,
                shape=(4,),
            )
            source[:] = [1.0, 2.0, 3.0, 4.0]
            source.flush()
            del source
            payload, memcpy_dtype, memcpy_elements_per_pe = (
                adapter._memcpy_payload_for_h2d(
                    path=path,
                    dtype="f16",
                    elements_per_pe=2,
                    total_elements=4,
                )
            )
        self.assertIsInstance(payload, np.memmap)
        self.assertEqual(payload.dtype, np.uint32)
        self.assertTrue(payload.flags.writeable)
        self.assertEqual(
            memcpy_dtype,
            adapter.MemcpyDataType.MEMCPY_32BIT,
        )
        self.assertEqual(memcpy_elements_per_pe, 1)
        self.assertEqual(payload.view(np.float16).tolist(), [1.0, 2.0, 3.0, 4.0])

    def test_f16_h2d_copies_read_only_payload(self) -> None:
        adapter = _load_launch_step_adapter_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            np.save(path, np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float16))
            with mock.patch.object(
                adapter,
                "_load_writeable_mmap_or_copy",
                return_value=np.load(path, mmap_mode="r").ravel(),
            ):
                payload, memcpy_dtype, memcpy_elements_per_pe = (
                    adapter._memcpy_payload_for_h2d(
                        path=path,
                        dtype="f16",
                        elements_per_pe=2,
                        total_elements=4,
                    )
                )
        self.assertEqual(payload.dtype, np.uint32)
        self.assertTrue(payload.flags.writeable)
        self.assertEqual(
            memcpy_dtype,
            adapter.MemcpyDataType.MEMCPY_32BIT,
        )
        self.assertEqual(memcpy_elements_per_pe, 1)
        self.assertEqual(payload.view(np.float16).tolist(), [1.0, 2.0, 3.0, 4.0])

    def test_dense_gemv_transform_accepts_sink_column_copyback(self) -> None:
        adapter = _load_launch_step_adapter_module()
        import numpy as np

        transform = {
            "kind": "dense_gemv_row_shards_to_logits",
            "width": 4,
            "height": 3,
            "outDim": 20,
            "outDimPerPe": 8,
        }
        compact = np.arange(24, dtype=np.float32)
        logits = adapter._dense_gemv_row_shards_to_logits(compact, transform)
        self.assertEqual(logits.tolist(), list(np.arange(20, dtype=np.float32)))

    def test_dense_gemv_output_uses_sink_column_region(self) -> None:
        adapter = _load_launch_step_adapter_module()

        region = adapter._d2h_region_for_output(
            output_transform={
                "kind": "dense_gemv_row_shards_to_logits",
                "width": 4,
                "height": 3,
                "outDim": 20,
                "outDimPerPe": 8,
            },
            width=4,
            height=3,
        )

        self.assertEqual(region, {
            "x": 3,
            "y": 0,
            "width": 1,
            "height": 3,
        })

    def test_summa_output_uses_compact_logical_region(self) -> None:
        adapter = _load_launch_step_adapter_module()

        region = adapter._d2h_region_for_output(
            output_transform={
                "kind": "summa_tiles_to_logical_matrix",
                "rows": 19,
                "cols": 4,
                "gridHeight": 16,
                "gridWidth": 16,
                "tileRows": 16,
                "tileCols": 16,
            },
            width=16,
            height=16,
        )

        self.assertEqual(region, {
            "x": 0,
            "y": 0,
            "width": 1,
            "height": 2,
        })

    def test_summa_output_splits_multi_row_copyback(self) -> None:
        adapter = _load_launch_step_adapter_module()

        regions = adapter._d2h_regions_for_output(
            output_transform={
                "kind": "summa_tiles_to_logical_matrix",
                "rows": 19,
                "cols": 4,
                "gridHeight": 16,
                "gridWidth": 16,
                "tileRows": 16,
                "tileCols": 16,
            },
            width=16,
            height=16,
        )

        self.assertEqual(regions, [
            {
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
            },
            {
                "x": 0,
                "y": 1,
                "width": 1,
                "height": 1,
            },
        ])

    def test_summa_transform_accepts_compact_region_copyback(self) -> None:
        adapter = _load_launch_step_adapter_module()
        import numpy as np

        transform = {
            "kind": "summa_tiles_to_logical_matrix",
            "rows": 19,
            "cols": 4,
            "paddedRows": 256,
            "paddedCols": 256,
            "gridHeight": 16,
            "gridWidth": 16,
            "tileRows": 16,
            "tileCols": 16,
        }
        region = {
            "x": 0,
            "y": 0,
            "width": 1,
            "height": 2,
        }
        host = np.arange(2 * 1 * 16 * 16, dtype=np.float32)
        logical = adapter._summa_c_tiles_to_logical(
            host,
            transform,
            region=region,
        )

        expected = host.reshape(2, 1, 16, 16).transpose(0, 3, 1, 2).reshape(32, 16)
        self.assertEqual(logical.tolist(), expected[:19, :4].reshape(-1).tolist())


class HostPlanRuntimeTimeout(unittest.TestCase):
    def test_compact_ple_proj_mode_only_intercepts_ple_proj(self) -> None:
        self.assertTrue(
            runner._is_compact_ple_proj_launch(
                {"targetName": "ple_proj"},
                "compact_summa_session",
            )
        )
        self.assertFalse(
            runner._is_compact_ple_proj_launch(
                {"targetName": "ple_proj"},
                "monolithic_summa",
            )
        )
        self.assertFalse(
            runner._is_compact_ple_proj_launch(
                {"targetName": "tiled"},
                "compact_summa_session",
            )
        )

    def test_compact_ple_proj_transforms_match_compiled_shape(self) -> None:
        a_transform = runner._compact_ple_proj_source_transform(
            matrix_role="a",
            source_cols=256,
        )
        b_transform = runner._compact_ple_proj_source_transform(
            matrix_role="b",
            source_cols=256,
            source_rows=4,
        )
        output_transform = runner._compact_ple_proj_output_transform(
            rows=19,
            cols=4,
        )

        self.assertEqual(a_transform["gridWidth"], 2)
        self.assertEqual(a_transform["gridHeight"], 2)
        self.assertEqual(a_transform["tileRows"], 16)
        self.assertEqual(a_transform["tileReduction"], 128)
        self.assertEqual(b_transform["paddedCols"], 32)
        self.assertEqual(b_transform["tileCols"], 16)
        self.assertEqual(output_transform["paddedRows"], 32)
        self.assertEqual(output_transform["paddedCols"], 32)

    def test_session_lm_head_tiled_mode_intercepts_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            progress_path = tmp / "progress.jsonl"
            trace_path = tmp / "trace.json"
            output_path = tmp / "hostplan-runtime" / "buffers" / "logits.npy"
            bootstrap = {
                "launches": [
                    {
                        "launchIndex": 4,
                        "targetName": "lm_head_prefill_stable",
                        "launchFunction": "compute",
                        "compileDir": str(tmp / "compile" / "compiled" / "lm_head_prefill_stable"),
                        "compileParams": {
                            "width": 160,
                            "height": 512,
                            "out_dim": 262144,
                            "out_dim_per_pe": 512,
                            "in_dim_per_pe": 32,
                        },
                        "targetGeometry": {"width": 160, "height": 512},
                    }
                ],
                "targetSessions": [],
            }

            def fake_stage_launch_arrays(**_kwargs: object) -> tuple[list[dict], list[dict]]:
                return [
                    {
                        "symbol": "activation",
                        "buffer": "activation:prefill:0003:global:final_norm",
                        "path": str(tmp / "activation.npy"),
                        "dtype": "f16",
                        "elemType": "f16",
                        "elementsPerPe": 32,
                    },
                    {
                        "symbol": "weight",
                        "buffer": "weight:lm_head",
                        "path": str(tmp / "weight.npy"),
                        "dtype": "f16",
                        "elemType": "f16",
                        "elementsPerPe": 16384,
                    },
                ], [
                    {
                        "symbol": "output",
                        "buffer": "activation:prefill:0004:global:lm_head",
                        "path": str(output_path),
                        "dtype": "f32",
                        "elemType": "f32",
                        "elementsPerPe": 512,
                    }
                ]

            def fake_session_tiled_launch(**_kwargs: object) -> dict:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"NUMPY")
                return {
                    "schemaVersion": 1,
                    "artifactKind": "int4ple_launch_step_receipt",
                    "status": "succeeded",
                    "blockers": [],
                    "launchIndex": 4,
                    "targetName": "lm_head_prefill_stable",
                    "dispatchMode": "dense_gemv_width_tiled_session",
                    "outputs": [
                        {
                            "symbol": "output",
                            "buffer": "activation:prefill:0004:global:lm_head",
                            "path": str(output_path),
                        }
                    ],
                }

            with (
                mock.patch.object(
                    runner,
                    "_stage_launch_arrays",
                    side_effect=fake_stage_launch_arrays,
                ),
                mock.patch.object(
                    runner,
                    "_execute_dense_gemv_tiled_session_launch",
                    side_effect=fake_session_tiled_launch,
                ) as tiled_mock,
                mock.patch.object(runner.subprocess, "run") as run_mock,
            ):
                result = runner.execute_hostplan_runtime(
                    bootstrap=bootstrap,
                    export={},
                    progress_path=progress_path,
                    cmaddr=None,
                    trace_path=trace_path,
                    session_lm_head_dispatch_mode="dense_gemv_width_tiled_session",
                )

            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["executedLaunchCount"], 1)
            self.assertEqual(
                result["launches"][0]["dispatchMode"],
                "dense_gemv_width_tiled_session",
            )
            self.assertEqual(
                result["sessionLmHeadDispatch"]["mode"],
                "dense_gemv_width_tiled_session",
            )
            receipt_path = (
                trace_path.parent
                / "hostplan-runtime"
                / "launch-receipts"
                / "launch-0004.json"
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(
                receipt["dispatchMode"],
                "dense_gemv_width_tiled_session",
            )
            self.assertEqual(tiled_mock.call_count, 1)
            run_mock.assert_not_called()

    def test_independent_embed_roi_launches_can_run_as_parallel_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            progress_path = tmp / "progress.jsonl"
            trace_path = tmp / "trace.json"
            checkpoint_dir = tmp / "checkpoints"
            runner._init_checkpoint(checkpoint_dir, {"test": "identity"})

            def launch(idx: int) -> dict:
                return {
                    "launchIndex": idx,
                    "targetName": "ple_embed",
                    "compileParams": {
                        "rows_per_pe": 1,
                        "hidden_size": 2,
                        "hidden_per_pe": 1,
                        "tokens_per_chunk": 1,
                    },
                    "inputBindings": [
                        {
                            "role": "tokenized_prompt",
                            "buffer": "input:prompt_token_ids",
                        },
                        {
                            "role": "weight",
                            "buffer": f"weight:layer{idx}",
                        },
                    ],
                    "resolvedOutputs": [
                        {
                            "symbol": "output",
                            "buffer": f"activation:prefill:{idx:04d}:layer{idx}",
                        }
                    ],
                }

            bootstrap = {"launches": [launch(0), launch(1)], "targetSessions": []}

            def fake_embed_roi_launch(**kwargs: object) -> dict:
                launch_spec = kwargs["launch"]
                runtime_dir = Path(str(kwargs["runtime_dir"]))
                buffer_files = kwargs["buffer_files"]
                idx = int(launch_spec["launchIndex"])
                output_buffer = launch_spec["resolvedOutputs"][0]["buffer"]
                output_path = runtime_dir / "buffers" / f"out-{idx}.bin"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(f"out-{idx}".encode("utf-8"))
                buffer_files[output_buffer] = output_path
                return {
                    "schemaVersion": 1,
                    "artifactKind": "int4ple_embed_roi_launch_receipt",
                    "status": "succeeded",
                    "blockers": [],
                    "launchIndex": idx,
                    "targetName": "ple_embed",
                    "output": {
                        "buffer": output_buffer,
                        "path": str(output_path),
                        "dtype": "f32",
                        "shape": [1, 2],
                    },
                }

            with mock.patch.object(
                runner,
                "_execute_embed_roi_launch",
                side_effect=fake_embed_roi_launch,
            ) as embed_mock:
                result = runner.execute_hostplan_runtime(
                    bootstrap=bootstrap,
                    export={},
                    progress_path=progress_path,
                    cmaddr=None,
                    trace_path=trace_path,
                    checkpoint_dir=checkpoint_dir,
                    session_embed_roi_jobs=2,
                )

            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["executedLaunchCount"], 2)
            self.assertEqual(result["sessionEmbedRoi"]["jobs"], 2)
            self.assertEqual(embed_mock.call_count, 2)

            manifest = json.loads(
                (checkpoint_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [entry["launchIndex"] for entry in manifest["completedLaunches"]],
                [0, 1],
            )

            phases = [
                json.loads(line)["phase"]
                for line in progress_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("hostplan_embed_roi_parallel_group_start", phases)
            self.assertIn("hostplan_embed_roi_parallel_group_complete", phases)

    def test_launch_step_timeout_is_typed_and_writes_receipt(self) -> None:
        import numpy as np

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            progress_path = tmp / "progress.jsonl"
            trace_path = tmp / "trace.json"
            input_path = tmp / "hostplan-runtime" / "buffers" / "input.npy"
            bootstrap = {
                "launches": [
                    {
                        "launchIndex": 0,
                        "targetName": "ple_embed",
                        "launchFunction": "compute",
                        "compileDir": str(tmp / "compiled"),
                        "targetGeometry": {"width": 1, "height": 1},
                    }
                ],
                "targetSessions": [],
            }

            def fake_stage_launch_arrays(**kwargs: object) -> tuple[list[dict], list[dict]]:
                runtime_dir = Path(str(kwargs["runtime_dir"]))
                input_path.parent.mkdir(parents=True, exist_ok=True)
                np.save(input_path, np.array([1.0, 2.0], dtype=np.float32))
                output_path = runtime_dir / "buffers" / "output.npy"
                return [
                    {
                        "symbol": "activation",
                        "buffer": "activation:prefill:0000:global:embed_tokens",
                        "role": "activation",
                        "path": str(input_path),
                        "dtype": "f32",
                        "elemType": "f32",
                        "elementsPerPe": 2,
                    }
                ], [
                    {
                        "symbol": "output",
                        "buffer": "activation:prefill:0000:global:ple_embed",
                        "path": str(output_path),
                        "dtype": "f16",
                    }
                ]

            timeout = subprocess.TimeoutExpired(
                cmd=["cs_python", "int4ple_launch_step_adapter.py"],
                timeout=7,
                output="stdout tail\n",
                stderr="stderr tail\n",
            )
            with (
                mock.patch.object(
                    runner,
                    "_stage_launch_arrays",
                    side_effect=fake_stage_launch_arrays,
                ),
                mock.patch.object(runner, "cs_python_executable", return_value=sys.executable),
                mock.patch.object(runner.subprocess, "run", side_effect=timeout) as run_mock,
            ):
                result = runner.execute_hostplan_runtime(
                    bootstrap=bootstrap,
                    export={},
                    progress_path=progress_path,
                    cmaddr=None,
                    trace_path=trace_path,
                    launch_timeout_seconds=7,
                )

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(
                result["blockers"],
                ["launch[0]_blocked:launch_step_timeout"],
            )
            self.assertEqual(result["launchTimeoutSeconds"], 7)
            self.assertEqual(result["launches"][0]["status"], "blocked")
            self.assertEqual(result["launches"][0]["blockers"], ["launch_step_timeout"])
            self.assertEqual(result["launches"][0]["stdoutTail"], ["stdout tail"])
            self.assertEqual(result["launches"][0]["stderrTail"], ["stderr tail"])
            self.assertEqual(run_mock.call_args.kwargs["timeout"], 7)

            receipt_path = (
                trace_path.parent
                / "hostplan-runtime"
                / "launch-receipts"
                / "launch-0000.json"
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["blockers"], ["launch_step_timeout"])
            self.assertEqual(
                receipt["inputBuffers"][0]["name"],
                "activation:prefill:0000:global:embed_tokens",
            )
            self.assertEqual(receipt["inputBuffers"][0]["role"], "activation")
            self.assertEqual(receipt["inputBuffers"][0]["totalElements"], 2)

            phases = [
                json.loads(line)["phase"]
                for line in progress_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("hostplan_launch_timeout", phases)


if __name__ == "__main__":
    unittest.main()
