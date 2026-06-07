#!/usr/bin/env python3
"""Regression tests for the standalone Dawn plan executor."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from bench.tests._plan_executor_support import (
    EXPECTED_PLAN_SHA256,
    PLAN_PATH,
    build_target_or_skip_on_missing_dawn_header,
    executor_bin,
    read_trace_artifacts,
    run_plan_executor,
)


class DawnPlanExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build_target_or_skip_on_missing_dawn_header("webgpu-plan-executor")

    def _run(self, *, workload: str, tmpdir: Path) -> subprocess.CompletedProcess[str]:
        return run_plan_executor(
            executor_bin("webgpu-plan-executor"),
            tmpdir=tmpdir,
            workload=workload,
        )

    def test_dry_run_emits_compare_ready_trace_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-webgpu-plan-executor-") as tmpdir:
            tmp = Path(tmpdir)
            result = self._run(workload="inference_gemma3_270m_prefill_32tok", tmpdir=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")

            meta, rows = read_trace_artifacts(tmp)

            self.assertEqual(meta["executionBackend"], "dawn_direct_metal")
            self.assertEqual(meta["backendId"], "dawn_direct_metal")
            self.assertEqual(meta["backendLane"], "metal_dawn_release")
            self.assertEqual(meta["queueSyncMode"], "per-command")
            self.assertEqual(meta["timingSource"], "doe-execution-total-ns")
            self.assertEqual(meta["timingClass"], "operation")
            self.assertEqual(meta["executionRowCount"], 35)
            self.assertEqual(meta["executionSuccessCount"], 35)
            self.assertEqual(meta["executionDispatchCount"], 18)
            self.assertEqual(meta["executionSubmitCount"], 0)
            self.assertEqual(meta["hostPlanArtifactHash"], EXPECTED_PLAN_SHA256)
            self.assertEqual(meta["hostPlanArtifactPath"], str(PLAN_PATH))
            self.assertEqual(len(rows), 35)
            self.assertEqual(rows[0]["semanticOpId"], "step-000000")
            self.assertEqual(rows[0]["semanticStage"], "webgpu_plan")
            self.assertEqual(rows[-1]["semanticOpId"], "step-000034")
            self.assertEqual(rows[-1]["executionBackend"], "dawn_direct_metal")
            self.assertEqual(rows[-1]["executionSubmitCount"], 0)

    def test_workload_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-webgpu-plan-executor-") as tmpdir:
            result = self._run(workload="wrong_workload", tmpdir=Path(tmpdir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WorkloadMismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
