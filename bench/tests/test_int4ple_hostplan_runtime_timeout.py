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


class HostPlanRuntimeTimeout(unittest.TestCase):
    def test_launch_step_timeout_is_typed_and_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            progress_path = tmp / "progress.jsonl"
            trace_path = tmp / "trace.json"
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
                output_path = runtime_dir / "buffers" / "output.npy"
                return [], [
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

            phases = [
                json.loads(line)["phase"]
                for line in progress_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("hostplan_launch_timeout", phases)


if __name__ == "__main__":
    unittest.main()
