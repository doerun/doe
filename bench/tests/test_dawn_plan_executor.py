#!/usr/bin/env python3
"""Regression tests for the standalone Dawn plan executor."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / "runtime" / "zig"
BIN_PATH = RUNTIME_DIR / "zig-out" / "bin" / "dawn-plan-executor"
PLAN_PATH = REPO_ROOT / "bench" / "plans" / "generated" / "inference_gemma3_270m_prefill_32tok.plan.json"
EXPECTED_PLAN_SHA256 = "b9a68954e24aa8c4c133ed33a6521a26e452688562eab454b9f8732825de8139"


class DawnPlanExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            ["zig", "build", "dawn-plan-executor"],
            cwd=RUNTIME_DIR,
            capture_output=True,
            text=True,
            check=True,
        )

    def run_executor(self, *, workload: str, dry_run: bool = True, tmpdir: Path) -> subprocess.CompletedProcess[str]:
        meta_path = tmpdir / "trace-meta.json"
        trace_path = tmpdir / "trace.jsonl"
        args = [
            str(BIN_PATH),
            "--plan",
            str(PLAN_PATH),
            "--trace-meta",
            str(meta_path),
            "--trace-jsonl",
            str(trace_path),
            "--workload",
            workload,
        ]
        if dry_run:
            args.append("--dry-run")
        return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, check=False)

    def test_dry_run_emits_compare_ready_trace_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-dawn-plan-executor-") as tmpdir:
            tmp = Path(tmpdir)
            result = self.run_executor(workload="inference_gemma3_270m_prefill_32tok", dry_run=True, tmpdir=tmp)
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(meta["executionBackend"], "dawn_direct_metal")
            self.assertEqual(meta["backendId"], "dawn_direct_metal")
            self.assertEqual(meta["backendLane"], "dawn_direct_metal")
            self.assertEqual(meta["queueSyncMode"], "per-command")
            self.assertEqual(meta["timingSource"], "doe-execution-total-ns")
            self.assertEqual(meta["timingClass"], "operation")
            self.assertEqual(meta["executionRowCount"], 25)
            self.assertEqual(meta["executionSuccessCount"], 25)
            self.assertEqual(meta["executionDispatchCount"], 18)
            self.assertEqual(meta["hostPlanArtifactHash"], EXPECTED_PLAN_SHA256)
            self.assertEqual(meta["hostPlanArtifactPath"], str(PLAN_PATH))
            self.assertEqual(len(rows), 25)
            self.assertEqual(rows[0]["semanticOpId"], "step-000000")
            self.assertEqual(rows[0]["semanticStage"], "dawn_plan")
            self.assertEqual(rows[-1]["semanticOpId"], "step-000024")
            self.assertEqual(rows[-1]["executionBackend"], "dawn_direct_metal")

    def test_workload_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-dawn-plan-executor-") as tmpdir:
            result = self.run_executor(workload="wrong_workload", dry_run=True, tmpdir=Path(tmpdir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WorkloadMismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
