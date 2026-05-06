from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class QwenHardwarePathTests(unittest.TestCase):
    def test_wrapper_dry_run_assembles_full_prompt_command(self) -> None:
        proc = subprocess.run(
            [
                "bash",
                "bench/tools/run_qwen3_6_27b_af16_hardware_path.sh",
                "--dry-run",
                "--skip-archive-verify",
                "--skip-fetch",
                "--skip-sdk-compile",
                "--cmaddr",
                "test-endpoint",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("qwen3_6_27b_af16_hostplan_streaming_runner.py", proc.stdout)
        self.assertIn("models/qwen-3-6-27b-q4k-eaf16/manifest.json", proc.stdout)
        self.assertIn("--prefill-token-count", proc.stdout)
        self.assertIn("248045", proc.stdout)
        self.assertIn("qwen3-6-27b-af16-trace.json", proc.stdout)

    def test_bundled_hostplan_fixture_has_operator_files(self) -> None:
        root = REPO_ROOT / "bench/fixtures/cerebras-hostplans/qwen3-6-27b-af16"
        for name in (
            "host-plan.json",
            "simulator-plan.json",
            "runtime-config.json",
            "memory-plan.json",
            "source-graph-inventory.json",
            "compile/targets.metadata.json",
        ):
            self.assertTrue((root / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
