from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
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
