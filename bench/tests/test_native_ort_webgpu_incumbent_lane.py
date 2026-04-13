#!/usr/bin/env python3
"""Regression tests for the native incumbent ORT WebGPU smoke bench surface."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.native_compare_modules import config_support


RUNNER_PATH = REPO_ROOT / "bench" / "executors" / "run-native-ort-incumbent-bench.py"
WORKLOADS_PATH = REPO_ROOT / "bench" / "workloads" / "workloads.native.ort-webgpu-provider-compare.basic-ops.json"
COMPARE_CONFIG_PATH = REPO_ROOT / "bench" / "native-compare" / "compare.config.native.ort-webgpu-provider.basic-ops.json"
WORKLOAD_ID = "inference_ort_native_compare_add_relu_float32_exactshape"
MATMUL_ADD_RELU_WORKLOAD_ID = "inference_ort_native_compare_matmul_add_relu_float32_rank2_exactshape"
SCENARIO_PATH = REPO_ROOT / "bench" / "vendor-native" / "ort_native_compare_add_relu_commands.json"
MATMUL_ADD_RELU_SCENARIO_PATH = REPO_ROOT / "bench" / "vendor-native" / "ort_native_compare_matmul_add_relu_commands.json"


def _write_fake_smoke(path: Path, *, success: bool) -> None:
    exit_code = 0 if success else 1
    payload = {
        "success": success,
        "failureReason": "" if success else "incumbent Add -> Relu smoke failed",
        "ortLibraryPath": "/tmp/libonnxruntime.so.1",
        "providerName": "WebGpuExecutionProvider",
        "ortRuntimeVersion": "1.23.2",
        "ortHeaderApiVersion": 26,
        "ortApiVersionRequested": 23,
        "availableProviders": ["WebGpuExecutionProvider", "CPUExecutionProvider"],
        "operations": {
            "createEnv": {"ok": True, "code": "ORT_OK", "message": ""},
            "createSessionOptions": {"ok": True, "code": "ORT_OK", "message": ""},
            "appendProvider": {"ok": True, "code": "ORT_OK", "message": ""},
        },
        "cases": [
            {
                "caseName": "add_relu",
                "modelKind": "Add->Relu",
                "success": success,
                "failureReason": "" if success else "incumbent Add -> Relu smoke failed",
                "outputsMatch": success,
                "expectedOutputShape": [1, 4],
                "actualOutputShape": [1, 4],
                "expectedOutput": [0, 0, 3, 6],
                "actualOutput": [0, 0, 3, 6] if success else [0, 0, 0, 0],
                "operations": {
                    "createModel": {"ok": True, "code": "ORT_OK", "message": ""},
                    "createSessionFromModel": {"ok": True, "code": "ORT_OK", "message": ""},
                    "run": {"ok": success, "code": "ORT_OK" if success else "ORT_FAIL", "message": ""},
                },
            }
        ],
    }
    script = textwrap.dedent(
        f"""\
        #!/usr/bin/env python3
        import json
        import sys
        from pathlib import Path

        args = sys.argv[1:]
        output = None
        for index, value in enumerate(args):
            if value == "--output":
                output = args[index + 1]
                break
        if output is None:
            raise SystemExit("missing --output")
        payload = {payload!r}
        Path(output).write_text(json.dumps(payload), encoding="utf-8")
        print(json.dumps(payload))
        raise SystemExit({exit_code})
        """
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


class NativeOrtWebGpuIncumbentLaneTests(unittest.TestCase):
    def test_workload_manifest_loads_strict_native_compare_lane(self) -> None:
        workloads = config_support.load_workloads(
            WORKLOADS_PATH,
            "",
            include_noncomparable=True,
            include_extended=False,
            workload_cohort="all",
            selector={"ids": [WORKLOAD_ID]},
        )
        self.assertEqual(len(workloads), 1)
        workload = workloads[0]
        self.assertEqual(workload.id, WORKLOAD_ID)
        self.assertTrue(workload.comparable)
        self.assertEqual(workload.benchmark_class, "comparable")
        self.assertTrue(workload.claim_eligible)
        self.assertEqual(
            workload.commands_path,
            "bench/vendor-native/ort_native_compare_add_relu_commands.json",
        )
        self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_matmul_add_relu_workload_manifest_loads_strict_native_compare_lane(self) -> None:
        workloads = config_support.load_workloads(
            WORKLOADS_PATH,
            "",
            include_noncomparable=True,
            include_extended=False,
            workload_cohort="all",
            selector={"ids": [MATMUL_ADD_RELU_WORKLOAD_ID]},
        )
        self.assertEqual(len(workloads), 1)
        workload = workloads[0]
        self.assertEqual(workload.id, MATMUL_ADD_RELU_WORKLOAD_ID)
        self.assertTrue(workload.comparable)
        self.assertEqual(workload.benchmark_class, "comparable")
        self.assertTrue(workload.claim_eligible)
        self.assertEqual(
            workload.commands_path,
            "bench/vendor-native/ort_native_compare_matmul_add_relu_commands.json",
        )
        self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_compare_config_is_strict_process_wall_local_claimable(self) -> None:
        payload = json.loads(COMPARE_CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["baseline"]["executorId"], "ort_native_doe_ep")
        self.assertEqual(payload["comparison"]["executorId"], "ort_native_webgpu_incumbent")
        self.assertEqual(payload["comparability"]["mode"], "strict")
        self.assertEqual(payload["comparability"]["requireTimingClass"], "process-wall")
        self.assertEqual(payload["claimability"]["mode"], "local")
        self.assertEqual(payload["claimability"]["minTimedSamples"], 3)
        self.assertEqual(
            payload["selector"]["ids"],
            [
                "inference_ort_native_compare_add_float32_exactshape",
                "inference_ort_native_compare_relu_float32_exactshape",
                "inference_ort_native_compare_matmul_float32_rank2_exactshape",
                "inference_ort_native_compare_matmul_add_float32_rank2_exactshape",
                "inference_ort_native_compare_matmul_add_relu_float32_rank2_exactshape",
                "inference_ort_native_compare_add_relu_float32_exactshape",
            ],
        )

    def test_scenario_payload_matches_incumbent_compare_contract(self) -> None:
        payload = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 1)
        scenario = payload[0]
        self.assertEqual(scenario["kind"], "vendor-native-benchmark-scenario")
        self.assertEqual(scenario["schemaVersion"], 1)
        self.assertEqual(scenario["scenarioId"], WORKLOAD_ID)
        self.assertEqual(scenario["caseName"], "add_relu")
        self.assertEqual(scenario["providerName"], "WebGPU")
        self.assertTrue(str(scenario["ortLibPath"]).endswith("libonnxruntime.so.1"))

    def test_matmul_add_relu_scenario_payload_matches_incumbent_compare_contract(self) -> None:
        payload = json.loads(MATMUL_ADD_RELU_SCENARIO_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 1)
        scenario = payload[0]
        self.assertEqual(scenario["kind"], "vendor-native-benchmark-scenario")
        self.assertEqual(scenario["schemaVersion"], 1)
        self.assertEqual(scenario["scenarioId"], MATMUL_ADD_RELU_WORKLOAD_ID)
        self.assertEqual(scenario["caseName"], "matmul_add_relu")
        self.assertEqual(scenario["providerName"], "WebGPU")
        self.assertTrue(str(scenario["ortLibPath"]).endswith("libonnxruntime.so.1"))

    def test_runner_emits_success_trace_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-native-ort-incumbent-success-") as tmpdir:
            tmp = Path(tmpdir)
            fake_smoke = tmp / "fake-smoke.py"
            _write_fake_smoke(fake_smoke, success=True)
            scenario_path = tmp / "scenario.json"
            trace_meta = tmp / "trace.meta.json"
            trace_jsonl = tmp / "trace.jsonl"
            scenario_payload = [
                {
                    "kind": "vendor-native-benchmark-scenario",
                    "schemaVersion": 1,
                    "scenarioId": WORKLOAD_ID,
                    "caseName": "add_relu",
                    "providerName": "WebGPU",
                    "ortLibPath": "/tmp/libonnxruntime.so.1",
                    "smokeBinaryPath": str(fake_smoke),
                }
            ]
            scenario_path.write_text(json.dumps(scenario_payload), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--scenario",
                    str(scenario_path),
                    "--trace-meta",
                    str(trace_meta),
                    "--trace-jsonl",
                    str(trace_jsonl),
                    "--workload",
                    WORKLOAD_ID,
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = json.loads(trace_meta.read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in trace_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(meta["benchmarkLane"], "native-ort-webgpu-incumbent-smoke")
        self.assertEqual(meta["executionBackend"], "ort_native_webgpu_incumbent")
        self.assertEqual(meta["executionProviderName"], "WebGpuExecutionProvider")
        self.assertEqual(meta["nativeOrtProviderName"], "WebGpuExecutionProvider")
        self.assertEqual(meta["nativeOrtAvailableProviders"], ["WebGpuExecutionProvider", "CPUExecutionProvider"])
        self.assertEqual(meta["executionSuccessCount"], 1)
        self.assertEqual(rows[0]["status"], "success")
        self.assertTrue(rows[0]["outputsMatch"])

    def test_runner_emits_failure_trace_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-native-ort-incumbent-failure-") as tmpdir:
            tmp = Path(tmpdir)
            fake_smoke = tmp / "fake-smoke.py"
            _write_fake_smoke(fake_smoke, success=False)
            scenario_path = tmp / "scenario.json"
            trace_meta = tmp / "trace.meta.json"
            trace_jsonl = tmp / "trace.jsonl"
            scenario_payload = [
                {
                    "kind": "vendor-native-benchmark-scenario",
                    "schemaVersion": 1,
                    "scenarioId": WORKLOAD_ID,
                    "caseName": "add_relu",
                    "providerName": "WebGPU",
                    "ortLibPath": "/tmp/libonnxruntime.so.1",
                    "smokeBinaryPath": str(fake_smoke),
                }
            ]
            scenario_path.write_text(json.dumps(scenario_payload), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--scenario",
                    str(scenario_path),
                    "--trace-meta",
                    str(trace_meta),
                    "--trace-jsonl",
                    str(trace_jsonl),
                    "--workload",
                    WORKLOAD_ID,
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            meta = json.loads(trace_meta.read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in trace_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(meta["benchmarkLane"], "native-ort-webgpu-incumbent-smoke")
        self.assertTrue(meta["terminalFailureCaptured"])
        self.assertEqual(meta["nativeOrtProviderName"], "WebGpuExecutionProvider")
        self.assertEqual(meta["executionErrorCount"], 1)
        self.assertEqual(rows[0]["status"], "error")
        self.assertIn("failed", rows[0]["errorMessage"])


if __name__ == "__main__":
    unittest.main()
