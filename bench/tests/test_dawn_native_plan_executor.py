#!/usr/bin/env python3
"""Regression tests for the standalone direct Dawn plan executor."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = REPO_ROOT / "runtime" / "zig"
EXECUTOR_PATH = BUILD_DIR / "zig-out" / "bin" / "webgpu-plan-executor"
PLAN_PATH = REPO_ROOT / "bench" / "plans" / "generated" / "inference_gemma3_270m_prefill_32tok.plan.json"
DAWN_DELEGATE_BACKEND_PATH = REPO_ROOT / "runtime" / "zig" / "src" / "backend" / "dawn_delegate_backend.zig"


def _build_webgpu_plan_executor_or_skip() -> None:
    build = subprocess.run(
        ["zig", "build", "webgpu-plan-executor"],
        cwd=BUILD_DIR,
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


class DawnDirectPlanExecutorTests(unittest.TestCase):
    def test_dawn_delegate_backend_supports_buffer_write_bytes(self) -> None:
        source = DAWN_DELEGATE_BACKEND_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "return try self.inner.executeBufferWriteBytes(handle, offset, buffer_size, data);",
            source,
        )

    def test_dry_run_emits_trace_artifacts(self) -> None:
        _build_webgpu_plan_executor_or_skip()

        with tempfile.TemporaryDirectory(prefix="doe-dawn-direct-plan-") as tmpdir:
            tmp = Path(tmpdir)
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"

            result = subprocess.run(
                [
                    str(EXECUTOR_PATH),
                    "--plan",
                    str(PLAN_PATH),
                    "--trace-meta",
                    str(meta_path),
                    "--trace-jsonl",
                    str(trace_path),
                    "--workload",
                    "inference_gemma3_270m_prefill_32tok",
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            rows = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertEqual(meta["executionBackend"], "dawn_direct_metal")
            self.assertEqual(meta["timingSource"], "doe-execution-total-ns")
            self.assertEqual(meta["timingClass"], "operation")
            self.assertEqual(meta["queueSyncMode"], "per-command")
            self.assertEqual(meta["executionDispatchCount"], 18)
            self.assertEqual(meta["executionSuccessCount"], 35)
            self.assertEqual(len(rows), 35)
            self.assertEqual(rows[0]["command"], "buffer_write")
            self.assertEqual(rows[-1]["command"], "kernel_dispatch")


if __name__ == "__main__":
    unittest.main()
