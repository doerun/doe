#!/usr/bin/env python3
"""Regression tests for the standalone Node WebGPU plan executor."""

from __future__ import annotations

import json
import os
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
        "executorId": "node_webgpu_package",
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


def write_buffer_load_command_plan(path: Path) -> None:
    plan = {
        "schemaVersion": 1,
        "planKind": "benchmark_ir",
        "workloadId": "buffer_load_roundtrip",
        "irPath": "bench/ir/test.json",
        "irScenario": "buffer_load_roundtrip",
        "commandCount": 2,
        "bufferWriteCount": 0,
        "bufferLoadCount": 1,
        "dispatchCount": 1,
        "sourceIrSha256": "abc",
        "compatibilityCommandsSha256": "def",
        "planSha256": "ghi",
        "commands": [
            {
                "kind": "buffer_load",
                "handle": 2001,
                "bufferSize": 64,
                "byteLength": 64,
                "cacheNamespace": "unit_test",
                "cacheKey": "alpha",
                "assetKey": "buffer_load_roundtrip:handle-2001",
                "generator": "splitmix64_f32_nonzero_v1",
                "seed": 7,
                "scale": 0.125,
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
                        "resource_handle": 2001,
                        "buffer_size": 64,
                        "buffer_type": "readonly",
                    },
                    {
                        "binding": 1,
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
  unsupportedCode: 'provider_execution_unavailable',
  unsupportedDetail: 'node-webgpu execution unavailable for provider node-webgpu on this Apple host',
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
        self.assertEqual(meta["unsupportedCode"], "provider_execution_unavailable")
        self.assertEqual(
            meta["unsupportedDetail"],
            "node-webgpu execution unavailable for provider node-webgpu on this Apple host",
        )
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
    executorId: 'node_webgpu_package',
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
    provider: 'node-webgpu',
    providerName: 'webgpu',
    executionBackend: 'node_webgpu_package',
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

    def test_command_plan_roundtrip_preserves_capture_semantics_and_determinism(self) -> None:
        script = f"""
import {{ normalizePlan }} from {json.dumps((REPO_ROOT / "bench" / "executors" / "node-webgpu" / "plan.js").resolve().as_uri())};
const plan = {{
  schemaVersion: 1,
  planKind: 'benchmark_ir',
  workloadId: 'sample_capture_roundtrip',
  planSha256: 'sample-capture-roundtrip',
  compatibilityCommandsSha256: 'sample-capture-roundtrip',
  determinism: {{
    mode: 'stable-token',
    semanticTokenIndex: 0,
    providerBoundary: 'doe',
    topCandidates: 4,
  }},
  commands: [
    {{
      kind: 'buffer_write',
      handle: 1010,
      bufferSize: 16,
      data: [1, 0, 0, 0],
    }},
    {{
      kind: 'buffer_write',
      handle: 2227,
      bufferSize: 16,
      data: [0, 0, 0, 0],
      semanticOpId: 'decode.final_logits',
      semanticStage: 'sample_only',
      semanticPhase: 'final_logits',
      semanticTokenIndex: 0,
      semanticExecutionPlanHash: 'abc123',
      captureBufferHandle: 2227,
      captureSize: 16,
    }},
    {{
      kind: 'kernel_dispatch',
      kernel: 'sample.wgsl',
      x: 1,
      y: 1,
      z: 1,
      bindings: [
        {{
          binding: 0,
          resource_handle: 1010,
          buffer_size: 16,
          buffer_type: 'uniform',
        }},
        {{
          binding: 1,
          resource_handle: 2227,
          buffer_size: 16,
          buffer_type: 'readonly',
        }},
        {{
          binding: 2,
          resource_handle: 2228,
          buffer_size: 4,
          buffer_type: 'storage',
        }},
      ],
      semanticOpId: 'sample.output_token',
      semanticStage: 'sample_only',
      semanticPhase: 'output_token',
      semanticTokenIndex: 0,
      semanticExecutionPlanHash: 'abc123',
      captureBufferHandle: 2228,
      captureSize: 4,
    }},
  ],
}};
const normalized = normalizePlan(plan);
console.log(JSON.stringify(normalized));
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
        self.assertEqual(payload["determinism"]["mode"], "stable-token")
        self.assertEqual(payload["determinism"]["providerBoundary"], "doe")
        self.assertEqual(payload["executionShape"]["readBufferCount"], 2)
        self.assertEqual(payload["executionShape"]["copyBufferToBufferCount"], 2)
        read_steps = [step for step in payload["steps"] if step["kind"] == "readBuffer"]
        self.assertEqual(read_steps[0]["semanticPhase"], "final_logits")
        self.assertEqual(read_steps[1]["semanticPhase"], "output_token")
        self.assertEqual(read_steps[0]["captureSourceBufferId"], "buffer_2227")
        self.assertEqual(read_steps[1]["captureSourceBufferId"], "buffer_2228")

    def test_evaluate_execution_determinism_uses_host_byte_policy(self) -> None:
        script = f"""
import {{ evaluateExecutionDeterminism }} from {json.dumps((REPO_ROOT / "bench" / "executors" / "node-webgpu" / "determinism.js").resolve().as_uri())};
const logits = new Uint8Array(new Float32Array([1, 7, 7, 2]).buffer);
const token = new Uint8Array(new Uint32Array([2]).buffer);
const result = await evaluateExecutionDeterminism({{
  determinismConfig: {{
    mode: 'stable-token',
    semanticTokenIndex: 0,
    providerBoundary: 'doe',
    topCandidates: 4,
  }},
  provider: 'doe',
  captureRows: new Map([
    ['0:final_logits', {{ bytes: logits, semanticPhase: 'final_logits', semanticTokenIndex: 0 }}],
    ['0:output_token', {{ bytes: token, semanticPhase: 'output_token', semanticTokenIndex: 0 }}],
  ]),
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
        self.assertEqual(payload["rawToken"], 2)
        self.assertEqual(payload["receipt"]["token"], 1)
        self.assertEqual(payload["determinism"]["mode"], "stable-token")
        self.assertEqual(payload["determinism"]["selectedBy"], "stable-token-policy")

    def test_lookup_unsupported_package_execution_entry_matches_host_specific_lane(self) -> None:
        script = f"""
import {{ lookupUnsupportedPackageExecutionEntry }} from {json.dumps(EXECUTOR_MODULE_URL)};
const policy = {{
  schemaVersion: 1,
  unsupportedExecutions: [
    {{
      id: 'apple-node-node-webgpu-gemma1b-mac-lan',
      runtimeHost: 'node',
      provider: 'node-webgpu',
      workloadId: 'inference_gemma3_1b_prefill_64tok_decode_64tok',
      host: {{
        platform: 'darwin',
        arch: 'arm64',
        hostname: 'mac.lan',
        osRelease: '25.3.0',
      }},
      unsupportedCode: 'provider_execution_unavailable',
      message: 'node-webgpu execution unavailable for provider node-webgpu on this Apple host',
      detail: 'diagnostic detail',
    }},
  ],
}};
const matched = lookupUnsupportedPackageExecutionEntry(policy, {{
  runtimeHost: 'node',
  provider: 'node-webgpu',
  workloadId: 'inference_gemma3_1b_prefill_64tok_decode_64tok',
  platform: 'darwin',
  arch: 'arm64',
  hostname: 'mac.lan',
  osRelease: '25.3.0',
}});
const missed = lookupUnsupportedPackageExecutionEntry(policy, {{
  runtimeHost: 'node',
  provider: 'node-webgpu',
  workloadId: 'inference_gemma3_1b_prefill_64tok_decode_64tok',
  platform: 'darwin',
  arch: 'arm64',
  hostname: 'other-host',
  osRelease: '25.3.0',
}});
console.log(JSON.stringify({{ matched, missed }}));
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
        self.assertEqual(payload["matched"]["unsupportedCode"], "provider_execution_unavailable")
        self.assertIsNone(payload["missed"])

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
        self.assertEqual(totals["hostArtifactFinalizeTotalNs"], 0)

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
                    "node-webgpu",
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

            self.assertEqual(meta["executionBackend"], "node_webgpu_package")
            self.assertEqual(meta["executionProvider"], "node-webgpu")
            self.assertEqual(meta["executionProviderName"], "node-webgpu")
            self.assertEqual(meta["timingSource"], "doe-execution-total-ns")
            self.assertEqual(meta["timingClass"], "operation")
            self.assertEqual(meta["executionQueueSyncMode"], "per-command")
            self.assertEqual(meta["executionQueueWaitMode"], "sync-readback.mapAsync")
            self.assertEqual(meta["executionRowCount"], 4)
            self.assertEqual(meta["executionSuccessCount"], 4)
            self.assertEqual(meta["executionDispatchCount"], 1)
            self.assertEqual(meta["provider"], "node-webgpu")
            self.assertEqual(meta["hostInputReadTotalNs"], 0)
            self.assertEqual(meta["hostExecutorInitTotalNs"], 0)
            self.assertFalse(meta["packagePreparedSession"])
            self.assertTrue(meta["packageSetupIncludedInSelectedTiming"])
            self.assertEqual(meta["packageSetupTotalNs"], 0)
            self.assertEqual(len(rows), 4)
            self.assertEqual([row["stepKind"] for row in rows], ["writeBuffer", "dispatch", "copyBufferToBuffer", "readBuffer"])
            self.assertTrue(all(row["executionBackend"] == "node_webgpu_package" for row in rows))
            self.assertTrue(all(row["executionProvider"] == "node-webgpu" for row in rows))
            self.assertTrue(all(row["executionProviderName"] == "node-webgpu" for row in rows))

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
                    "node-webgpu",
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
                    "node-webgpu",
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
                    "node-webgpu",
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
                    "node-webgpu",
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
                    "node-webgpu",
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
            self.assertEqual(meta["executionBackend"], "node_webgpu_package")
            self.assertEqual(meta["executionRowCount"], 2)
            self.assertEqual(meta["executionDispatchCount"], 1)

    def test_generated_buffer_load_command_plan_is_accepted_in_dry_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-node-webgpu-executor-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "command-plan.json"
            meta_path = tmp / "trace-meta.json"
            trace_path = tmp / "trace.jsonl"
            write_buffer_load_command_plan(plan_path)

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
                    "buffer_load_roundtrip",
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["executionBackend"], "doe_node_webgpu")
            self.assertEqual(meta["executionRowCount"], 2)
            self.assertEqual(meta["executionDispatchCount"], 1)

    def test_materialize_buffer_data_reads_cache_backed_file_descriptor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-node-webgpu-assets-") as tmpdir:
            cache_dir = Path(tmpdir)
            asset_dir = cache_dir / "unit_test"
            asset_dir.mkdir(parents=True, exist_ok=True)
            (asset_dir / "alpha.bin").write_bytes(bytes([1, 2, 3, 4]))
            script = f"""
import {{ materializeBufferData }} from {json.dumps((REPO_ROOT / "bench" / "executors" / "node-webgpu" / "plan.js").resolve().as_uri())};
const payload = materializeBufferData({{
  kind: 'file',
  cacheNamespace: 'unit_test',
  cacheKey: 'alpha',
  sizeBytes: 4,
}});
console.log(JSON.stringify(Array.from(payload)));
"""
            env = dict(os.environ)
            env["DOE_BENCH_ASSET_CACHE_DIR"] = str(cache_dir)
            result = subprocess.run(
                ["node", "--input-type=module", "-e", script],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
