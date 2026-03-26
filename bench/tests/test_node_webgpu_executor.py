#!/usr/bin/env python3
"""Regression tests for the standalone Node WebGPU plan executor."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPO_ROOT / "bench" / "executors" / "run-node-webgpu-plan.js"


def write_plan(path: Path, *, valid: bool = True) -> None:
    plan = {
        "schemaVersion": 1,
        "planId": "simple_compute_roundtrip",
        "executorId": "node-webgpu",
        "workloadId": "simple_compute_roundtrip",
        "domain": "compute",
        "comparable": True,
        "timing": {
            "iterations": 1,
            "warmup": 0,
            "timingSource": "doe-execution-total-ns",
            "timingClass": "operation",
        },
        "adapter": {
            "powerPreference": "high-performance",
        },
        "buffers": [
            {
                "id": "input",
                "size": 16,
                "usage": ["storage", "copy_dst"],
            },
            {
                "id": "output",
                "size": 16,
                "usage": ["storage", "copy_src"],
            },
            {
                "id": "readback",
                "size": 16,
                "usage": ["map_read", "copy_dst"],
            },
        ],
        "modules": [
            {
                "id": "multiply",
                "kind": "compute",
                "entryPoint": "main",
                "source": {
                    "kind": "inline",
                    "code": (
                        "@group(0) @binding(0) var<storage, read> input: array<f32>;\n"
                        "@group(0) @binding(1) var<storage, read_write> output: array<f32>;\n"
                        "@compute @workgroup_size(64)\n"
                        "fn main(@builtin(global_invocation_id) gid: vec3u) {\n"
                        "  let i = gid.x;\n"
                        "  if (i < arrayLength(&input)) {\n"
                        "    output[i] = input[i] * 2.0;\n"
                        "  }\n"
                        "}\n"
                    ),
                },
            }
        ],
        "steps": [
            {
                "kind": "writeBuffer",
                "bufferId": "input",
                "offset": 0,
                "data": {
                    "kind": "f32",
                    "values": [1.0, 2.0, 3.0, 4.0],
                },
            },
            {
                "kind": "dispatch",
                "moduleId": "multiply",
                "bindings": [
                    {
                        "binding": 0,
                        "bufferId": "input",
                        "bufferType": "read-only-storage",
                    },
                    {
                        "binding": 1,
                        "bufferId": "output",
                        "bufferType": "storage",
                    },
                ],
                "workgroups": [1, 1, 1],
            },
            {
                "kind": "copyBufferToBuffer",
                "srcBufferId": "output",
                "dstBufferId": "readback",
                "sizeBytes": 16,
            },
            {
                "kind": "readBuffer",
                "bufferId": "readback",
                "validate": {
                    "kind": "f32PrefixEquals",
                    "values": [2.0, 4.0, 6.0, 8.0],
                },
            },
        ],
    }

    if not valid:
        plan["buffers"][0]["usage"] = ["storage"]

    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")


def write_command_plan(path: Path) -> None:
    plan = {
        "schemaVersion": 1,
        "planKind": "benchmark_ir",
        "workloadId": "command_plan_roundtrip",
        "irPath": "bench/ir/test.json",
        "irScenario": "command_plan_roundtrip",
        "commandCount": 2,
        "bufferWriteCount": 1,
        "dispatchCount": 1,
        "sourceIrSha256": "abc",
        "compatibilityCommandsSha256": "def",
        "planSha256": "ghi",
        "commands": [
            {
                "kind": "buffer_write",
                "handle": 1001,
                "bufferSize": 16,
                "data": [1, 2, 3, 4],
            },
            {
                "kind": "kernel_dispatch",
                "kernel": "rmsnorm.wgsl",
                "x": 1,
                "y": 1,
                "z": 1,
                "bindings": [
                    {
                        "binding": 0,
                        "resource_handle": 1001,
                        "buffer_size": 16,
                        "buffer_type": "uniform",
                    },
                    {
                        "binding": 1,
                        "resource_handle": 2001,
                        "buffer_size": 64,
                        "buffer_type": "readonly",
                    },
                    {
                        "binding": 2,
                        "resource_handle": 2002,
                        "buffer_size": 64,
                        "buffer_type": "storage",
                    },
                ],
            },
        ],
    }
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")


class NodeWebGPUExecutorTests(unittest.TestCase):
    def test_dry_run_emits_trace_meta_and_jsonl(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-node-webgpu-executor-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "plan.json"
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"
            write_plan(plan_path)

            result = subprocess.run(
                [
                    "node",
                    str(CLI_PATH),
                    "--provider",
                    "dawn",
                    "--plan",
                    str(plan_path),
                    "--trace-meta",
                    str(meta_path),
                    "--trace-jsonl",
                    str(trace_path),
                    "--workload",
                    "simple_compute_roundtrip",
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(meta["executionBackend"], "dawn_node_webgpu")
            self.assertEqual(meta["executionProvider"], "dawn")
            self.assertEqual(meta["executionProviderName"], "webgpu")
            self.assertEqual(meta["timingSource"], "doe-execution-total-ns")
            self.assertEqual(meta["timingClass"], "operation")
            self.assertEqual(meta["executionQueueSyncMode"], "per-command")
            self.assertEqual(meta["executionQueueWaitMode"], "queue.onSubmittedWorkDone")
            self.assertEqual(meta["executionRowCount"], 4)
            self.assertEqual(meta["executionSuccessCount"], 4)
            self.assertEqual(meta["executionDispatchCount"], 1)
            self.assertEqual(meta["provider"], "dawn")
            self.assertEqual(len(rows), 4)
            self.assertEqual([row["stepKind"] for row in rows], ["writeBuffer", "dispatch", "copyBufferToBuffer", "readBuffer"])
            self.assertTrue(all(row["executionBackend"] == "dawn_node_webgpu" for row in rows))
            self.assertTrue(all(row["executionProvider"] == "dawn" for row in rows))
            self.assertTrue(all(row["executionProviderName"] == "webgpu" for row in rows))

    def test_dry_run_supports_doe_provider_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-node-webgpu-executor-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "plan.json"
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"
            write_plan(plan_path)

            result = subprocess.run(
                [
                    "node",
                    str(CLI_PATH),
                    "--provider",
                    "doe",
                    "--plan",
                    str(plan_path),
                    "--trace-meta",
                    str(meta_path),
                    "--trace-jsonl",
                    str(trace_path),
                    "--workload",
                    "simple_compute_roundtrip",
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(meta["executionBackend"], "doe_node_webgpu")
            self.assertEqual(meta["executionProvider"], "doe")
            self.assertEqual(meta["executionProviderName"], "doe-gpu")
            self.assertEqual(meta["provider"], "doe")
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(row["executionBackend"] == "doe_node_webgpu" for row in rows))
            self.assertTrue(all(row["executionProvider"] == "doe" for row in rows))
            self.assertTrue(all(row["executionProviderName"] == "doe-gpu" for row in rows))

    def test_invalid_plan_is_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-node-webgpu-executor-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "plan.json"
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"
            write_plan(plan_path, valid=False)

            result = subprocess.run(
                [
                    "node",
                    str(CLI_PATH),
                    "--provider",
                    "dawn",
                    "--plan",
                    str(plan_path),
                    "--trace-meta",
                    str(meta_path),
                    "--trace-jsonl",
                    str(trace_path),
                    "--workload",
                    "simple_compute_roundtrip",
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("writeBuffer target input requires copy_dst usage", result.stderr)
            self.assertFalse(meta_path.exists())
            self.assertFalse(trace_path.exists())

    def test_generated_command_plan_is_accepted_in_dry_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-node-webgpu-executor-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "command-plan.json"
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"
            write_command_plan(plan_path)

            result = subprocess.run(
                [
                    "node",
                    str(CLI_PATH),
                    "--provider",
                    "dawn",
                    "--plan",
                    str(plan_path),
                    "--trace-meta",
                    str(meta_path),
                    "--trace-jsonl",
                    str(trace_path),
                    "--workload",
                    "command_plan_roundtrip",
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["executionBackend"], "dawn_node_webgpu")
            self.assertEqual(meta["executionRowCount"], 2)
            self.assertEqual(meta["executionDispatchCount"], 1)


if __name__ == "__main__":
    unittest.main()
