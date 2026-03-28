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
EXECUTOR_MODULE_URL = (REPO_ROOT / "bench" / "executors" / "node-webgpu" / "executor.js").resolve().as_uri()


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
    def test_classify_bringup_unsupported_recognizes_unavailable_errors(self) -> None:
        script = f"""
import {{ classifyBringupUnsupported }} from {json.dumps(EXECUTOR_MODULE_URL)};
const classified = classifyBringupUnsupported('requestDevice', {{
  code: 'DOE_REQUEST_DEVICE_ERROR',
  message: 'requestDevice failed (status=3, detail=vulkan runtime init failed)',
}});
console.log(JSON.stringify(classified));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        classified = json.loads(result.stdout)
        self.assertEqual(classified["unsupportedCode"], "device_unavailable")
        self.assertIn("vulkan runtime init failed", classified["detail"])

    def test_build_unsupported_execution_result_preserves_prepared_session_boundary(self) -> None:
        script = f"""
import {{ buildUnsupportedExecutionResult }} from {json.dumps(EXECUTOR_MODULE_URL)};
const result = buildUnsupportedExecutionResult({{
  normalizedPlan: {{
    workloadId: 'alpha',
    planId: 'alpha-plan',
    planHash: 'alpha-hash',
    executionShape: {{
      stepCount: 4,
      dispatchCount: 2,
      bufferCount: 2,
      moduleCount: 1,
      writeBufferCount: 1,
      copyBufferToBufferCount: 0,
      readBufferCount: 0,
    }},
    buffers: [],
    modules: [],
    steps: [],
  }},
  spec: {{
    provider: 'doe',
    providerName: 'doe-gpu',
    executionBackend: 'doe_node_webgpu',
  }},
  preparedSession: true,
  hostInputReadTotalNs: 11,
  hostInputParseTotalNs: 12,
  hostWorkloadPrepareTotalNs: 13,
  hostExecutorInitTotalNs: 14,
  processWallMs: 1.5,
}});
console.log(JSON.stringify(result));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        meta = payload["meta"]
        self.assertEqual(meta["executionRowCount"], 0)
        self.assertEqual(meta["executionSuccessCount"], 0)
        self.assertEqual(meta["executionUnsupportedCount"], 1)
        self.assertEqual(meta["hostInputReadTotalNs"], 0)
        self.assertEqual(meta["hostInputParseTotalNs"], 0)
        self.assertEqual(meta["hostWorkloadPrepareTotalNs"], 0)
        self.assertEqual(meta["hostExecutorInitTotalNs"], 0)
        self.assertTrue(meta["packagePreparedSession"])
        self.assertEqual(meta["workloadUnitWallSource"], "trace-meta-process-wall")
        self.assertEqual(payload["rows"], [])

    def test_build_error_execution_result_marks_error_count(self) -> None:
        script = f"""
import {{ buildErrorExecutionResult }} from {json.dumps(EXECUTOR_MODULE_URL)};
const result = buildErrorExecutionResult({{
  normalizedPlan: {{
    schemaVersion: 1,
    executorId: 'dawn_node_webgpu',
    workloadId: 'alpha',
    planId: 'alpha-plan',
    planHash: 'alpha-hash',
    domain: 'compute',
    comparable: true,
    timing: {{ iterations: 1, warmup: 0, timingSource: 'doe-execution-total-ns', timingClass: 'operation' }},
    executionShape: {{
      stepCount: 4,
      dispatchCount: 2,
      bufferCount: 2,
      moduleCount: 1,
      writeBufferCount: 1,
      copyBufferToBufferCount: 0,
      readBufferCount: 0,
    }},
  }},
  spec: {{
    provider: 'dawn',
    providerName: 'webgpu',
    executionBackend: 'dawn_node_webgpu',
  }},
  preparedSession: false,
  hostInputReadTotalNs: 11,
  hostInputParseTotalNs: 12,
  hostWorkloadPrepareTotalNs: 13,
  hostExecutorInitTotalNs: 14,
  processWallMs: 2.5,
}});
console.log(JSON.stringify(result));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        meta = payload["meta"]
        self.assertEqual(meta["executionErrorCount"], 1)
        self.assertEqual(meta["executionUnsupportedCount"], 0)
        self.assertEqual(meta["executionSuccessCount"], 0)
        self.assertFalse(meta["packagePreparedSession"])
        self.assertEqual(payload["rows"], [])

    def test_build_error_execution_result_zeroes_prepared_session_pre_boundary_totals(self) -> None:
        script = f"""
import {{ buildErrorExecutionResult }} from {json.dumps(EXECUTOR_MODULE_URL)};
const result = buildErrorExecutionResult({{
  normalizedPlan: null,
  workloadId: 'prepared_error_alpha',
  planPath: '/tmp/prepared_error_alpha.json',
  spec: {{
    provider: 'doe',
    providerName: 'doe-gpu',
    executionBackend: 'doe_node_webgpu',
  }},
  preparedSession: true,
  hostInputReadTotalNs: 11,
  hostInputParseTotalNs: 12,
  hostWorkloadPrepareTotalNs: 13,
  hostExecutorInitTotalNs: 14,
  processWallMs: 2.5,
}});
console.log(JSON.stringify(result));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        meta = payload["meta"]
        self.assertEqual(meta["executionErrorCount"], 1)
        self.assertTrue(meta["packagePreparedSession"])
        self.assertEqual(meta["hostInputReadTotalNs"], 0)
        self.assertEqual(meta["hostInputParseTotalNs"], 0)
        self.assertEqual(meta["hostWorkloadPrepareTotalNs"], 0)
        self.assertEqual(meta["hostExecutorInitTotalNs"], 0)
        self.assertEqual(meta["workloadUnitWallSource"], "trace-meta-process-wall")

    def test_build_dispatch_binding_cache_key_reuses_identical_bindings(self) -> None:
        script = f"""
import {{ buildDispatchBindingCacheKey }} from {json.dumps(EXECUTOR_MODULE_URL)};
const a = buildDispatchBindingCacheKey({{
  bindings: [
    {{ binding: 0, bufferId: 'buf_a', bufferType: 'read-only-storage', offset: 0 }},
    {{ binding: 1, bufferId: 'buf_b', bufferType: 'storage', offset: 16, size: 64 }},
  ],
}});
const b = buildDispatchBindingCacheKey({{
  bindings: [
    {{ binding: 0, bufferId: 'buf_a', bufferType: 'read-only-storage', offset: 0 }},
    {{ binding: 1, bufferId: 'buf_b', bufferType: 'storage', offset: 16, size: 64 }},
  ],
}});
const c = buildDispatchBindingCacheKey({{
  bindings: [
    {{ binding: 0, bufferId: 'buf_a', bufferType: 'read-only-storage', offset: 0 }},
    {{ binding: 1, bufferId: 'buf_c', bufferType: 'storage', offset: 16, size: 64 }},
  ],
}});
console.log(JSON.stringify({{ a, b, c }}));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["a"], payload["b"])
        self.assertNotEqual(payload["a"], payload["c"])

    def test_build_request_device_descriptor_omits_empty_fields(self) -> None:
        script = f"""
import {{ buildRequestDeviceDescriptor }} from {json.dumps(EXECUTOR_MODULE_URL)};
const empty = buildRequestDeviceDescriptor({{
  requiredFeatures: [],
  requiredLimits: {{}},
}});
const populated = buildRequestDeviceDescriptor({{
  requiredFeatures: ['shader-f16'],
  requiredLimits: {{ maxStorageBuffersPerShaderStage: 8 }},
}});
console.log(JSON.stringify({{ empty, populated }}));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["empty"], {})
        self.assertEqual(payload["populated"]["requiredFeatures"], ["shader-f16"])
        self.assertEqual(
            payload["populated"]["requiredLimits"]["maxStorageBuffersPerShaderStage"],
            8,
        )

    def test_prepared_session_boundary_scopes_pre_boundary_host_totals(self) -> None:
        script = f"""
import {{ boundaryScopedHostTotals }} from {json.dumps(EXECUTOR_MODULE_URL)};
console.log(JSON.stringify(boundaryScopedHostTotals({{
  preparedSession: true,
  hostInputReadTotalNs: 11,
  hostInputParseTotalNs: 12,
  hostWorkloadPrepareTotalNs: 13,
  hostExecutorInitTotalNs: 14,
  hostUploadPrewarmTotalNs: 15,
  hostKernelPrewarmTotalNs: 16,
  hostCommandOrchestrationTotalNs: 17,
  hostArtifactFinalizeTotalNs: 18,
}})));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        totals = json.loads(result.stdout)
        self.assertEqual(totals["hostInputReadTotalNs"], 0)
        self.assertEqual(totals["hostInputParseTotalNs"], 0)
        self.assertEqual(totals["hostWorkloadPrepareTotalNs"], 0)
        self.assertEqual(totals["hostExecutorInitTotalNs"], 0)
        self.assertEqual(totals["hostUploadPrewarmTotalNs"], 15)
        self.assertEqual(totals["hostKernelPrewarmTotalNs"], 16)
        self.assertEqual(totals["hostCommandOrchestrationTotalNs"], 17)
        self.assertEqual(totals["hostArtifactFinalizeTotalNs"], 18)

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
            self.assertEqual(meta["hostInputReadTotalNs"], 0)
            self.assertEqual(meta["hostExecutorInitTotalNs"], 0)
            self.assertFalse(meta["packagePreparedSession"])
            self.assertTrue(meta["packageSetupIncludedInSelectedTiming"])
            self.assertEqual(meta["packageSetupTotalNs"], 0)
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
            self.assertFalse(meta["packagePreparedSession"])
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(row["executionBackend"] == "doe_node_webgpu" for row in rows))
            self.assertTrue(all(row["executionProvider"] == "doe" for row in rows))
            self.assertTrue(all(row["executionProviderName"] == "doe-gpu" for row in rows))

    def test_dry_run_supports_prepared_session_metadata(self) -> None:
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
            self.assertTrue(meta["packagePreparedSession"])
            self.assertFalse(meta["packageSetupIncludedInSelectedTiming"])
            self.assertEqual(meta["workloadUnitWallSource"], "trace-meta-process-wall")

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
            self.assertTrue(meta_path.exists())
            self.assertTrue(trace_path.exists())
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["executionErrorCount"], 1)
            self.assertEqual(meta["workload"], "simple_compute_roundtrip")
            self.assertEqual(trace_path.read_text(encoding="utf-8"), "")

    def test_unparseable_plan_still_emits_terminal_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-node-webgpu-executor-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "bad-plan.json"
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"
            plan_path.write_text("{ not valid json", encoding="utf-8")

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
                    "bad_plan_workload",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(meta_path.exists())
            self.assertTrue(trace_path.exists())
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["executionErrorCount"], 1)
            self.assertEqual(meta["workload"], "bad_plan_workload")
            self.assertEqual(meta["executionShape"]["stepCount"], 0)
            self.assertEqual(trace_path.read_text(encoding="utf-8"), "")

    def test_cli_writes_error_meta_when_workload_id_mismatch(self) -> None:
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
                    "wrong_workload_id",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(meta_path.exists())
            self.assertTrue(trace_path.exists())

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["executionErrorCount"], 1)
            self.assertEqual(meta["executionUnsupportedCount"], 0)
            self.assertEqual(meta["executionRowCount"], 0)
            self.assertEqual(trace_path.read_text(encoding="utf-8"), "")

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
