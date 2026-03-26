#!/usr/bin/env python3
"""Tests for explicit compare executor ids."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.native_compare_modules.executor_registry import (
    resolve_executor_boundary,
    resolve_executor_command_template,
)


class ExecutorRegistryTests(unittest.TestCase):
    def test_resolves_doe_direct_executor(self) -> None:
        template = resolve_executor_command_template("doe_direct_metal")
        self.assertIn("doe-zig-runtime", template)
        self.assertIn("--backend-lane metal_doe_comparable", template)
        self.assertEqual(resolve_executor_boundary("doe_direct_metal"), "commands")

    def test_resolves_doe_direct_plan_executor(self) -> None:
        template = resolve_executor_command_template("doe_direct_plan_metal")
        self.assertIn("doe-plan-executor", template)
        self.assertIn("--plan {plan}", template)
        self.assertIn("--backend-lane metal_doe_comparable", template)
        self.assertEqual(resolve_executor_boundary("doe_direct_plan_metal"), "plan")

    def test_resolves_node_webgpu_executor(self) -> None:
        template = resolve_executor_command_template("dawn_node_webgpu")
        self.assertIn("run-node-webgpu-plan.js", template)
        self.assertIn("--plan {plan}", template)
        self.assertIn("--provider dawn", template)
        self.assertEqual(resolve_executor_boundary("dawn_node_webgpu"), "plan")

    def test_resolves_doe_node_webgpu_executor(self) -> None:
        template = resolve_executor_command_template("doe_node_webgpu")
        self.assertIn("run-node-webgpu-plan.js", template)
        self.assertIn("--plan {plan}", template)
        self.assertIn("--provider doe", template)
        self.assertEqual(resolve_executor_boundary("doe_node_webgpu"), "plan")

    def test_resolves_direct_dawn_executor(self) -> None:
        template = resolve_executor_command_template("dawn_direct_metal")
        self.assertIn("dawn-plan-executor", template)
        self.assertIn("--plan {plan}", template)
        self.assertIn("--trace-meta {trace_meta}", template)
        self.assertEqual(resolve_executor_boundary("dawn_direct_metal"), "plan")

    def test_rejects_unknown_executor(self) -> None:
        with self.assertRaises(ValueError):
            resolve_executor_command_template("unknown_executor")


if __name__ == "__main__":
    unittest.main()
