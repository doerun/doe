#!/usr/bin/env python3
"""Regression tests for the standalone Doe direct plan executor."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from bench.tests._plan_executor_support import (
    EXPECTED_PLAN_SHA256,
    PLAN_PATH,
    RUNTIME_DIR,
    build_target,
    executor_bin,
    read_trace_artifacts,
    run_plan_executor,
)


_DOE_BACKEND_ARGS = (
    "--vendor", "apple",
    "--api", "metal",
    "--family", "m3",
    "--driver", "1.0.0",
    "--backend-lane", "metal_doe_comparable",
)


class DoeDirectPlanExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = build_target("doe-plan-executor")
        if result.returncode != 0:
            raise AssertionError(result.stderr)

    def _run(self, *, workload: str, tmpdir: Path) -> subprocess.CompletedProcess[str]:
        return run_plan_executor(
            executor_bin("doe-plan-executor"),
            tmpdir=tmpdir,
            workload=workload,
            extra_args=_DOE_BACKEND_ARGS,
        )

    def test_dry_run_emits_compare_ready_trace_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-direct-plan-executor-") as tmpdir:
            tmp = Path(tmpdir)
            result = self._run(workload="inference_gemma3_270m_prefill_32tok", tmpdir=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")

            meta, rows = read_trace_artifacts(tmp)

            self.assertEqual(meta["module"], "doe-plan-executor")
            self.assertEqual(meta["queueSyncMode"], "per-command")
            self.assertEqual(meta["backendLane"], "metal_doe_comparable")
            self.assertEqual(meta["executionRowCount"], 35)
            self.assertEqual(meta["executionSuccessCount"], 35)
            self.assertEqual(meta["executionDispatchCount"], 18)
            self.assertEqual(meta["hostPlanArtifactHash"], EXPECTED_PLAN_SHA256)
            self.assertEqual(meta["hostPlanArtifactPath"], str(PLAN_PATH))
            self.assertEqual(len(rows), 35)
            self.assertEqual(rows[0]["semanticStage"], "runtime_plan")
            self.assertEqual(rows[0]["semanticOpId"], "step-000000")
            self.assertEqual(rows[-1]["semanticOpId"], "step-000034")
            self.assertEqual(rows[0]["executionStatusCode"], "dry_run")
            self.assertNotIn("matched", rows[0])
            self.assertNotIn("executionHostPlanArtifactPath", rows[0])
            self.assertNotIn("executionSelectionPolicyHash", rows[0])

    def test_workload_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-direct-plan-executor-") as tmpdir:
            result = self._run(workload="wrong_workload", tmpdir=Path(tmpdir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WorkloadMismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
