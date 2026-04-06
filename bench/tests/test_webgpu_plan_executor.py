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
BIN_PATH = RUNTIME_DIR / "zig-out" / "bin" / "webgpu-plan-executor"
PLAN_PATH = REPO_ROOT / "bench" / "plans" / "generated" / "inference_gemma3_270m_prefill_32tok.plan.json"
EXPECTED_PLAN_SHA256 = "47fd52b0ca02a3f3245a80f52143b4230a769b86049f1b1871fe24fde106514b"


def _build_webgpu_plan_executor_or_skip() -> None:
    build = subprocess.run(
        ["zig", "build", "webgpu-plan-executor"],
        cwd=RUNTIME_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if build.returncode == 0:
        return
    if "dawn/webgpu.h" in build.stderr and "file not found" in build.stderr:
        raise unittest.SkipTest(
            "webgpu-plan-executor build prerequisite missing: local Chromium header checkout does not provide dawn/webgpu.h"
        )
    raise AssertionError(build.stderr)


class DawnPlanExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _build_webgpu_plan_executor_or_skip()

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
        with tempfile.TemporaryDirectory(prefix="doe-webgpu-plan-executor-") as tmpdir:
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
            self.assertEqual(meta["backendLane"], "metal_dawn_release")
            self.assertEqual(meta["queueSyncMode"], "per-command")
            self.assertEqual(meta["timingSource"], "doe-execution-total-ns")
            self.assertEqual(meta["timingClass"], "operation")
            self.assertEqual(meta["executionRowCount"], 35)
            self.assertEqual(meta["executionSuccessCount"], 35)
            self.assertEqual(meta["executionDispatchCount"], 18)
            self.assertEqual(meta["hostPlanArtifactHash"], EXPECTED_PLAN_SHA256)
            self.assertEqual(meta["hostPlanArtifactPath"], str(PLAN_PATH))
            self.assertEqual(len(rows), 35)
            self.assertEqual(rows[0]["semanticOpId"], "step-000000")
            self.assertEqual(rows[0]["semanticStage"], "webgpu_plan")
            self.assertEqual(rows[-1]["semanticOpId"], "step-000034")
            self.assertEqual(rows[-1]["executionBackend"], "dawn_direct_metal")

    def test_workload_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-webgpu-plan-executor-") as tmpdir:
            result = self.run_executor(workload="wrong_workload", dry_run=True, tmpdir=Path(tmpdir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WorkloadMismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
