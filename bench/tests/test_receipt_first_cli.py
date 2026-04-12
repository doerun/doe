#!/usr/bin/env python3
"""Tests for receipt-first benchmark CLI behavior."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench import cli as cli_mod  # noqa: E402
from bench.native_compare_modules import run_receipts_from_config as run_config_mod  # noqa: E402


class ReceiptFirstCliTests(unittest.TestCase):
    def test_run_config_emits_one_side_receipt_without_execution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-run-config-") as tmpdir:
            tmp = Path(tmpdir)
            workspace = tmp / "workspace"
            report_out = tmp / "unused.compare.json"
            rc = run_config_mod.main(
                [
                    "--config",
                    "bench/native-compare/compare.config.amd.vulkan.gemma270m.node-package.ir.json",
                    "--side",
                    "baseline",
                    "--emit-shell",
                    "--workspace",
                    str(workspace),
                    "--out",
                    str(report_out),
                    "--no-timestamp-output",
                ]
            )
            self.assertEqual(rc, 0)
            artifacts = sorted(
                (workspace / "run-artifacts" / "doe_gpu_node_package").glob("*.run.json")
            )
            self.assertEqual(len(artifacts), 1)

    def test_compare_config_shortcut_is_rejected(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            [
                "bench/cli.py",
                "compare",
                "--config",
                "bench/native-compare/compare.config.example.json",
            ],
        ):
            with redirect_stderr(stderr):
                rc = cli_mod.main()
        self.assertEqual(rc, 1)
        message = stderr.getvalue()
        self.assertIn("config-backed inline compare has been removed", message)
        self.assertIn("run-config --config", message)


if __name__ == "__main__":
    unittest.main()
