#!/usr/bin/env python3
"""Tests for benchmark IR loading and normalized plan materialization."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bench.lib import benchmark_ir


class BenchmarkIrTests(unittest.TestCase):
    def test_materialize_plan_expands_repeat_and_counts_commands(self) -> None:
        payload = {
            "schemaVersion": 1,
            "kind": "benchmark_ir",
            "description": "test ir",
            "scenarios": [
                {
                    "id": "alpha",
                    "description": "alpha scenario",
                    "irPath": "bench/ir/test.json",
                    "planPath": "bench/plans/generated/alpha.plan.json",
                    "commandsPath": "bench/plans/generated/compat/alpha_commands.json",
                    "commands": [
                        {"kind": "buffer_write", "handle": 1, "bufferSize": 16, "data": [1, 2, 3, 4]},
                        {
                            "kind": "repeat",
                            "count": 2,
                            "commands": [
                                {
                                    "kind": "kernel_dispatch",
                                    "kernel": "rmsnorm.wgsl",
                                    "x": 1,
                                    "y": 1,
                                    "z": 1,
                                    "bindings": [],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory(prefix="doe-benchmark-ir-") as tmpdir:
            ir_path = Path(tmpdir) / "test_ir.json"
            ir_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            plan = benchmark_ir.materialize_plan(ir_path, "alpha")

        self.assertEqual(plan["workloadId"], "alpha")
        self.assertEqual(plan["commandCount"], 3)
        self.assertEqual(plan["bufferWriteCount"], 1)
        self.assertEqual(plan["dispatchCount"], 2)
        self.assertEqual(
            [command["kind"] for command in plan["commands"]],
            ["buffer_write", "kernel_dispatch", "kernel_dispatch"],
        )
        self.assertTrue(plan["planSha256"])
        self.assertTrue(plan["compatibilityCommandsSha256"])

    def test_materialize_plan_injects_deterministic_buffer_loads_for_readonly_weights(self) -> None:
        payload = {
            "schemaVersion": 1,
            "kind": "benchmark_ir",
            "description": "test ir",
            "shared": {
                "syntheticReadonlyBufferPolicy": {
                    "cacheNamespace": "unit_test",
                    "generator": "splitmix64_f32_nonzero_v1",
                    "seed": 7,
                    "scale": 0.125,
                }
            },
            "scenarios": [
                {
                    "id": "alpha",
                    "description": "alpha scenario",
                    "irPath": "bench/ir/test.json",
                    "planPath": "bench/plans/generated/alpha.plan.json",
                    "commandsPath": "bench/plans/generated/compat/alpha_commands.json",
                    "commands": [
                        {"kind": "buffer_write", "handle": 10, "bufferSize": 16, "data": [1, 2, 3, 4]},
                        {
                            "kind": "kernel_dispatch",
                            "kernel": "alpha.wgsl",
                            "x": 1,
                            "y": 1,
                            "z": 1,
                            "bindings": [
                                {"binding": 0, "resource_handle": 10, "buffer_size": 16, "buffer_type": "uniform"},
                                {"binding": 1, "resource_handle": 20, "buffer_size": 64, "buffer_type": "readonly"},
                                {"binding": 2, "resource_handle": 21, "buffer_size": 64, "buffer_type": "storage"},
                            ],
                        },
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory(prefix="doe-benchmark-ir-") as tmpdir:
            ir_path = Path(tmpdir) / "test_ir.json"
            ir_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            plan = benchmark_ir.materialize_plan(ir_path, "alpha")

        self.assertEqual(plan["commandCount"], 3)
        self.assertEqual(plan["bufferWriteCount"], 1)
        self.assertEqual(plan["bufferLoadCount"], 1)
        self.assertEqual(plan["dispatchCount"], 1)
        self.assertEqual(
            [command["kind"] for command in plan["commands"]],
            ["buffer_write", "buffer_load", "kernel_dispatch"],
        )
        buffer_load = plan["commands"][1]
        self.assertEqual(buffer_load["handle"], 20)
        self.assertEqual(buffer_load["bufferSize"], 64)
        self.assertEqual(buffer_load["byteLength"], 64)
        self.assertEqual(buffer_load["cacheNamespace"], "unit_test")
        self.assertEqual(buffer_load["generator"], "splitmix64_f32_nonzero_v1")
        self.assertTrue(buffer_load["cacheKey"])


if __name__ == "__main__":
    unittest.main()
