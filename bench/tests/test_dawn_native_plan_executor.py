#!/usr/bin/env python3
"""Regression tests for the standalone direct Dawn plan executor."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bench.tests._plan_executor_support import (
    REPO_ROOT,
    build_target_or_skip_on_missing_dawn_header,
    executor_bin,
    read_trace_artifacts,
    run_plan_executor,
)

DAWN_DELEGATE_BACKEND_PATH = (
    REPO_ROOT / "runtime" / "zig" / "src" / "backend" / "dawn_delegate_backend.zig"
)


class DawnDirectPlanExecutorTests(unittest.TestCase):
    def test_dawn_delegate_backend_supports_buffer_write_bytes(self) -> None:
        source = DAWN_DELEGATE_BACKEND_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "return try self.inner.executeBufferWriteBytes(handle, offset, buffer_size, data);",
            source,
        )

    def test_dry_run_emits_trace_artifacts(self) -> None:
        build_target_or_skip_on_missing_dawn_header("webgpu-plan-executor")

        with tempfile.TemporaryDirectory(prefix="doe-dawn-direct-plan-") as tmpdir:
            tmp = Path(tmpdir)
            result = run_plan_executor(executor_bin("webgpu-plan-executor"), tmpdir=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)

            meta, rows = read_trace_artifacts(tmp)

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
