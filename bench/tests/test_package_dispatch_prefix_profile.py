#!/usr/bin/env python3
"""Tests for package dispatch-prefix profiling tooling."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "bench" / "tools" / "package_dispatch_prefix_profile.mjs"
SCHEMA_PATH = REPO_ROOT / "config" / "package-dispatch-prefix-profile.schema.json"
PLAN_MODULE_URL = (
    REPO_ROOT / "bench" / "executors" / "node-webgpu" / "plan.js"
).resolve().as_uri()
RUNNER_CORE_MODULE_URL = (
    REPO_ROOT / "bench" / "executors" / "package-webgpu" / "runner-core.js"
).resolve().as_uri()


def write_plan(path: Path) -> None:
    plan = {
        "schemaVersion": 1,
        "planId": "two_dispatch_roundtrip",
        "executorId": "node_webgpu_package",
        "workloadId": "two_dispatch_roundtrip",
        "domain": "compute",
        "comparable": True,
        "timing": {
            "iterations": 1,
            "warmup": 0,
            "timingSource": "doe-execution-total-ns",
            "timingClass": "operation",
        },
        "adapter": {"powerPreference": "high-performance"},
        "buffers": [
            {"id": "input", "size": 16, "usage": ["storage", "copy_dst"]},
            {"id": "output", "size": 16, "usage": ["storage", "copy_src"]},
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
                        "  if (i < arrayLength(&input)) { output[i] = input[i] * 2.0; }\n"
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
                "data": {"kind": "f32", "values": [1.0, 2.0, 3.0, 4.0]},
            },
            {
                "id": "first-dispatch",
                "kind": "dispatch",
                "moduleId": "multiply",
                "bindings": [
                    {"binding": 0, "bufferId": "input", "bufferType": "read-only-storage"},
                    {"binding": 1, "bufferId": "output", "bufferType": "storage"},
                ],
                "workgroups": [1, 1, 1],
                "semanticPhase": "first_kernel",
            },
            {
                "id": "second-dispatch",
                "kind": "dispatch",
                "moduleId": "multiply",
                "bindings": [
                    {"binding": 0, "bufferId": "input", "bufferType": "read-only-storage"},
                    {"binding": 1, "bufferId": "output", "bufferType": "storage"},
                ],
                "workgroups": [2, 1, 1],
                "semanticPhase": "second_kernel",
            },
        ],
    }
    path.write_text(json.dumps(plan), encoding="utf-8")


class PackageDispatchPrefixProfileTests(unittest.TestCase):
    def test_prefix_profile_samples_carry_package_fast_path_stats(self) -> None:
        source = TOOL_PATH.read_text(encoding="utf-8")
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertIn("function packageFastPathStatsFromMeta(meta)", source)
        self.assertIn("packageFastPathStatsFromMeta(meta)", source)
        self.assertIn("function packageNativeFastPathsFromMeta(meta)", source)
        self.assertIn("packageNativeFastPathsFromMeta(meta)", source)
        self.assertIn("p95ToMedianPermille", source)
        self.assertIn("maxToMedianPermille", source)
        self.assertIn("function buildStabilityDiagnostics({ dispatches, fullPlan })", source)
        self.assertIn("packageReadbackMode", source)
        self.assertIn("packageFastPathStats", schema["$defs"])
        self.assertIn("packageNativeFastPaths", schema["$defs"])
        self.assertIn(
            "packageFastPathStats",
            schema["$defs"]["sample"]["properties"],
        )
        self.assertIn(
            "packageNativeFastPaths",
            schema["$defs"]["sample"]["properties"],
        )
        self.assertIn(
            "packageReadbackMode",
            schema["$defs"]["sample"]["properties"],
        )
        self.assertIn(
            "maxToMedianPermille",
            schema["$defs"]["nsSummary"]["properties"],
        )
        self.assertIn("stabilityDiagnostics", schema["properties"])
        self.assertIn("stabilityDiagnostics", schema["$defs"])

    def test_prefix_profile_emits_dry_run_dispatch_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-package-prefix-profile-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "plan.json"
            out_path = tmp / "profile.json"
            trace_dir = tmp / "traces"
            write_plan(plan_path)

            result = subprocess.run(
                [
                    "node",
                    str(TOOL_PATH),
                    "--plan",
                    str(plan_path),
                    "--workload",
                    "two_dispatch_roundtrip",
                    "--provider",
                    "doe",
                    "--runtime-host",
                    "node",
                    "--out",
                    str(out_path),
                    "--trace-dir",
                    str(trace_dir),
                    "--sample-count",
                    "1",
                    "--executor-dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["kind"], "package_dispatch_prefix_profile")
            self.assertEqual(payload["profileMode"], "dispatch-prefix-terminal-wait")
            self.assertEqual(payload["deltaMethod"], "adjacent-prefix-subtraction-diagnostic")
            self.assertTrue(payload["executorDryRun"])
            self.assertFalse(payload["includeFullPlan"])
            self.assertEqual(payload["fullPlanCommandRepeat"], 1)
            self.assertEqual(payload["dispatchCount"], 2)
            self.assertEqual(
                [entry["stepId"] for entry in payload["dispatches"]],
                ["first-dispatch", "second-dispatch"],
            )
            self.assertEqual(
                [entry["stepLimit"] for entry in payload["dispatches"]],
                [2, 3],
            )
            self.assertEqual(
                [entry["semanticPhase"] for entry in payload["dispatches"]],
                ["first_kernel", "second_kernel"],
            )
            self.assertEqual(payload["dispatches"][0]["sampleCount"], 1)
            self.assertEqual(payload["dispatches"][0]["executionTotalNs"]["count"], 1)
            self.assertEqual(payload["dispatches"][0]["executionTotalNs"]["range"], 0)
            self.assertEqual(
                payload["dispatches"][0]["executionTotalNs"]["maxToMedianPermille"],
                0,
            )
            self.assertEqual(payload["dispatches"][0]["readbackTotalNs"]["count"], 1)
            self.assertEqual(
                payload["dispatches"][0]["phaseBreakdownNs"]["dispatchEncodeApiTotalNs"]["count"],
                1,
            )
            self.assertEqual(payload["adjacentDeltaRankingLimit"], 8)
            self.assertEqual(
                payload["adjacentDeltaRankings"]["executionTotalNs"][0]["metric"],
                "executionTotalNs",
            )
            self.assertIn(
                payload["adjacentDeltaRankings"]["readbackTotalNs"][0]["dispatchOrdinal"],
                [1, 2],
            )
            self.assertEqual(payload["dispatches"][0]["samples"][0]["executionDispatchCount"], 1)
            self.assertEqual(
                payload["dispatches"][0]["samples"][0]["phaseBreakdownNs"]["dispatchEncodeApiTotalNs"],
                0,
            )
            self.assertEqual(payload["dispatches"][0]["samples"][0]["readbackCaptureCount"], 0)
            self.assertEqual(payload["dispatches"][1]["samples"][0]["executionDispatchCount"], 2)
            self.assertEqual(
                payload["stabilityDiagnostics"]["overallStatus"],
                "insufficient-samples",
            )
            self.assertEqual(payload["stabilityDiagnostics"]["minSampleCount"], 3)
            self.assertGreater(payload["stabilityDiagnostics"]["metricCount"], 0)

    def test_prefix_profile_can_include_full_plan_samples(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-package-prefix-profile-") as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "plan.json"
            out_path = tmp / "profile.json"
            trace_dir = tmp / "traces"
            write_plan(plan_path)

            result = subprocess.run(
                [
                    "node",
                    str(TOOL_PATH),
                    "--plan",
                    str(plan_path),
                    "--workload",
                    "two_dispatch_roundtrip",
                    "--provider",
                    "doe",
                    "--runtime-host",
                    "node",
                    "--out",
                    str(out_path),
                    "--trace-dir",
                    str(trace_dir),
                    "--sample-count",
                    "1",
                    "--command-repeat",
                    "3",
                    "--full-plan-command-repeat",
                    "1",
                    "--executor-dry-run",
                    "--include-full-plan",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertTrue(payload["includeFullPlan"])
            self.assertEqual(payload["commandRepeat"], 3)
            self.assertEqual(payload["fullPlanCommandRepeat"], 1)
            self.assertEqual(payload["fullPlan"]["sampleCount"], 1)
            self.assertEqual(payload["fullPlan"]["readbackTotalNs"]["count"], 1)
            self.assertEqual(payload["fullPlan"]["readbackTotalNs"]["range"], 0)
            self.assertEqual(payload["fullPlan"]["samples"][0]["executionDispatchCount"], 2)
            self.assertEqual(
                payload["fullPlanResidualNs"]["basis"],
                "full-plan-median-minus-last-dispatch-prefix-median",
            )
            self.assertEqual(
                payload["fullPlanResidualNs"]["metrics"]["executionTotalNs"]["positiveMeansFullPlanHasExtraCost"],
                True,
            )
            self.assertEqual(
                payload["fullPlanPhaseResidualRanking"]["basis"],
                "full-plan-phase-median-minus-last-dispatch-prefix-phase-median",
            )
            self.assertIn(
                "phase",
                payload["fullPlanPhaseResidualRanking"]["phases"][0],
            )
            self.assertEqual(payload["fullPlan"]["phaseBreakdownNs"]["submitAddonFlushTotalNs"]["count"], 1)
            self.assertEqual(
                payload["fullPlan"]["samples"][0]["phaseBreakdownNs"]["submitAddonFlushTotalNs"],
                0,
            )
            self.assertEqual(payload["fullPlan"]["samples"][0]["readbackCaptureCount"], 0)
            self.assertTrue(
                any(
                    record["scope"] == "fullPlan" and record["metric"] == "executionTotalNs"
                    for record in payload["stabilityDiagnostics"]["records"]
                )
            )

    def test_command_plan_dispatch_metadata_survives_normalization(self) -> None:
        script = f"""
import {{ normalizePlan }} from {json.dumps(PLAN_MODULE_URL)};
const plan = normalizePlan({{
  schemaVersion: 1,
  planKind: 'benchmark_ir',
  workloadId: 'semantic_dispatch_roundtrip',
  planSha256: 'plan',
  compatibilityCommandsSha256: 'compat',
  adapter: {{
    power_preference: 'high-performance',
    required_features: ['subgroups'],
    required_limits: {{ maxStorageBuffersPerShaderStage: 8 }},
  }},
  commands: [
    {{
      kind: 'kernel_dispatch',
      kernel: 'sample.wgsl',
      entry_point: 'main_vec4',
      x: 1,
      y: 1,
      z: 1,
      semantic_phase: 'decode_sample_token',
      semantic_op_id: 'sample-op',
      captureBufferHandle: 1,
      captureSize: 4,
      captureExpectedU32Le: 47,
      bindings: [
        {{ binding: 0, resource_handle: 1, buffer_size: 16, buffer_type: 'storage' }}
      ]
    }}
  ]
}});
console.log(JSON.stringify({{ adapter: plan.adapter, dispatch: plan.steps[0], readback: plan.steps[2] }}));
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
        self.assertEqual(payload["adapter"]["requiredFeatures"], ["subgroups"])
        self.assertEqual(payload["adapter"]["requiredLimits"]["maxStorageBuffersPerShaderStage"], 8)
        self.assertEqual(payload["dispatch"]["id"], "step-0")
        self.assertEqual(payload["dispatch"]["moduleId"], "sample")
        self.assertEqual(payload["dispatch"]["entryPoint"], "main_vec4")
        self.assertEqual(payload["dispatch"]["semanticPhase"], "decode_sample_token")
        self.assertEqual(payload["dispatch"]["semanticOpId"], "sample-op")
        self.assertEqual(payload["readback"]["validate"], {"kind": "u32PrefixEquals", "values": [47]})

    def test_successful_stderr_filter_allows_debug_and_rejects_validation_noise(self) -> None:
        script = f"""
import {{ successfulRunUnexpectedStderr }} from {json.dumps(RUNNER_CORE_MODULE_URL)};
console.log(JSON.stringify({{
  debug: successfulRunUnexpectedStderr('{{"kind":"package_webgpu_debug","phase":"start"}}\\n'),
  dawnLimits: successfulRunUnexpectedStderr('Warning: maxDynamicUniformBuffersPerPipelineLayout artificially reduced from 500000 to 16 to fit dynamic offset allocation limit.\\nWarning: maxDynamicStorageBuffersPerPipelineLayout artificially reduced from 500000 to 16 to fit dynamic offset allocation limit.\\n'),
  validation: successfulRunUnexpectedStderr('extension \\'subgroups\\' is not allowed in the current environment\\n'),
}}));
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
        self.assertEqual(payload["debug"], [])
        self.assertEqual(payload["dawnLimits"], [])
        self.assertEqual(
            payload["validation"],
            ["extension 'subgroups' is not allowed in the current environment"],
        )


if __name__ == "__main__":
    unittest.main()
