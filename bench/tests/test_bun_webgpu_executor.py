#!/usr/bin/env python3
"""Regression tests for the standalone Bun WebGPU plan executor."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPO_ROOT / "bench" / "executors" / "run-bun-webgpu-plan.js"
BUN_FFI_PATH = REPO_ROOT / "packages" / "doe-gpu" / "src" / "vendor" / "webgpu" / "bun-ffi.js"
BUN = shutil.which("bun")


def write_plan(path: Path) -> None:
    plan = {
        "schemaVersion": 1,
        "planId": "simple_compute_roundtrip",
        "executorId": "bun-webgpu",
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
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")


@unittest.skipUnless(BUN, "bun is required for Bun executor tests")
class BunWebGPUExecutorTests(unittest.TestCase):
    def test_bun_adapter_request_device_keeps_capability_queries_lazy(self) -> None:
        source = BUN_FFI_PATH.read_text(encoding="utf-8")
        start = source.index("adapterRequestDevice(adapter, _descriptor, classes) {")
        end = source.index("\n    },\n    adapterDestroy(native) {", start)
        block = source[start:end]

        self.assertIn("const device = new classes.DoeGPUDevice(native, adapter._instance);", block)
        self.assertIn("device._adapter = adapter;", block)
        self.assertNotIn("device.limits = deviceLimits(native);", block)
        self.assertNotIn("device.features = deviceFeatures(native);", block)
        self.assertNotIn("device._adapterInfo = adapter.info;", block)

    def test_bun_encoder_backend_elides_duplicate_pipeline_and_bind_group_sets(self) -> None:
        source = BUN_FFI_PATH.read_text(encoding="utf-8")

        self.assertIn("function updatePassPipelineState(pass, pipelineNative)", source)
        self.assertIn("function updatePassBindGroupState(pass, index, bindGroupNative)", source)
        self.assertIn("if (!updatePassPipelineState(pass, pipelineNative)) {", source)
        self.assertIn("if (!updatePassBindGroupState(pass, index, bindGroupNative)) {", source)

    def test_dry_run_emits_bun_webgpu_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-bun-webgpu-executor-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "plan.json"
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"
            write_plan(plan_path)

            result = subprocess.run(
                [
                    str(BUN),
                    str(CLI_PATH),
                    "--provider",
                    "bun-webgpu",
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

            self.assertEqual(meta["executionBackend"], "bun_webgpu_package")
            self.assertEqual(meta["executionProvider"], "bun-webgpu")
            self.assertEqual(meta["executionProviderName"], "bun-webgpu")
            self.assertFalse(meta["packagePreparedSession"])
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(row["executionBackend"] == "bun_webgpu_package" for row in rows))

    def test_dry_run_emits_prepared_doe_bun_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-bun-webgpu-executor-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "plan.json"
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"
            write_plan(plan_path)

            result = subprocess.run(
                [
                    str(BUN),
                    str(CLI_PATH),
                    "--provider",
                    "doe",
                    "--prepared-session",
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
            self.assertEqual(meta["executionBackend"], "doe_bun_package")
            self.assertEqual(meta["executionProvider"], "doe")
            self.assertEqual(meta["executionProviderName"], "doe-gpu")
            self.assertTrue(meta["packagePreparedSession"])
            self.assertEqual(meta["workloadUnitWallSource"], "trace-meta-process-wall")


if __name__ == "__main__":
    unittest.main()
