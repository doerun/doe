#!/usr/bin/env python3
"""Regression tests for the native Doe ORT EP smoke bench surface."""

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


RUNNER_PATH = REPO_ROOT / "bench" / "executors" / "run-native-ort-ep-bench.py"
WORKLOADS_PATH = REPO_ROOT / "bench" / "workloads" / "workloads.native.ort-doe-ep-smoke.json"
IDENTITY_WORKLOAD_ID = "inference_ort_doe_ep_identity_float32_exactshape"
WORKLOAD_ID = "inference_ort_doe_ep_add_relu_float32_exactshape"
MATMUL_WORKLOAD_ID = "inference_ort_doe_ep_matmul_float32_rank2_exactshape"
MATMUL_ADD_WORKLOAD_ID = "inference_ort_doe_ep_matmul_add_float32_rank2_exactshape"
IDENTITY_SCENARIO_PATH = REPO_ROOT / "bench" / "vendor-native" / "ort_doe_ep_identity_commands.json"
SCENARIO_PATH = REPO_ROOT / "bench" / "vendor-native" / "ort_doe_ep_add_relu_commands.json"
MATMUL_SCENARIO_PATH = REPO_ROOT / "bench" / "vendor-native" / "ort_doe_ep_matmul_commands.json"
MATMUL_ADD_SCENARIO_PATH = REPO_ROOT / "bench" / "vendor-native" / "ort_doe_ep_matmul_add_commands.json"


def _write_fake_smoke(path: Path, *, success: bool) -> None:
    exit_code = 0 if success else 1
    payload = {
        "success": success,
        "failureReason": "" if success else "fused Add -> Relu smoke failed",
        "pluginPath": "runtime/zig/zig-out/lib/libonnxruntime_doe_ep.so",
        "ortLibraryPath": "libonnxruntime.so.1.23",
        "ortRuntimeVersion": "1.23.2",
        "ortHeaderApiVersion": 26,
        "ortApiVersionRequested": 23,
        "selectedEp": {
            "discoveredDeviceCount": 1,
            "name": "DoeExecutionProvider",
            "vendor": "Doe",
            "hardwareDeviceType": "OrtHardwareDeviceType_GPU",
        },
        "pluginDebug": {
            "symbolsLoaded": True,
            "finalCounters": {
                "getCapabilityCalls": 1,
                "claimedNodes": 2,
                "claimedIdentityNodes": 0,
                "claimedAddNodes": 1,
                "claimedReluNodes": 1,
                "claimedMatMulNodes": 0,
                "compileCalls": 1,
                "compiledIdentityGroups": 0,
                "compiledAddGroups": 0,
                "compiledReluGroups": 0,
                "compiledMatMulGroups": 0,
                "compiledMatMulAddGroups": 0,
                "compiledAddReluGroups": 1,
                "createStateCalls": 1,
                "computeCalls": 1,
                "computeIdentityCalls": 0,
                "computeAddCalls": 0,
                "computeReluCalls": 0,
                "computeMatMulCalls": 0,
                "computeMatMulAddCalls": 0,
                "computeAddReluCalls": 1,
                "releaseStateCalls": 1,
            },
        },
        "operations": {
            "registerExecutionProviderLibrary": {"ok": True, "code": "ORT_OK", "message": ""},
            "getEpDevices": {"ok": True, "code": "ORT_OK", "message": ""},
            "appendExecutionProviderV2": {"ok": True, "code": "ORT_OK", "message": ""},
        },
        "cases": [
            {
                "caseName": "add_relu",
                "modelKind": "Add->Relu",
                "success": success,
                "failureReason": "" if success else "fused Add -> Relu smoke failed",
                "sessionInputsHaveEpDevice": True,
                "outputsMatch": success,
                "routedThroughDoe": success,
                "expectedClaimedNodes": 2,
                "expectedOutputShape": [1, 4],
                "actualOutputShape": [1, 4],
                "expectedOutput": [0, 0, 3, 6],
                "actualOutput": [0, 0, 3, 6] if success else [0, 0, 0, 0],
                "debugCountersBefore": {},
                "debugCountersAfter": {},
                "debugCountersDelta": {
                    "getCapabilityCalls": 1,
                    "claimedNodes": 2,
                    "claimedAddNodes": 1,
                    "claimedReluNodes": 1,
                    "compileCalls": 1,
                    "compiledAddReluGroups": 1,
                    "createStateCalls": 1,
                    "computeCalls": 1,
                    "computeAddReluCalls": 1,
                    "releaseStateCalls": 1,
                },
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


class NativeOrtEpSmokeLaneTests(unittest.TestCase):
    def test_workload_manifest_loads_native_smoke_lane(self) -> None:
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
        self.assertFalse(workload.comparable)
        self.assertEqual(workload.benchmark_class, "directional")
        self.assertFalse(workload.claim_eligible)
        self.assertEqual(
            workload.commands_path,
            "bench/vendor-native/ort_doe_ep_add_relu_commands.json",
        )
        self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_identity_workload_manifest_loads_native_smoke_lane(self) -> None:
        workloads = config_support.load_workloads(
            WORKLOADS_PATH,
            "",
            include_noncomparable=True,
            include_extended=False,
            workload_cohort="all",
            selector={"ids": [IDENTITY_WORKLOAD_ID]},
        )
        self.assertEqual(len(workloads), 1)
        workload = workloads[0]
        self.assertEqual(workload.id, IDENTITY_WORKLOAD_ID)
        self.assertFalse(workload.comparable)
        self.assertEqual(workload.benchmark_class, "directional")
        self.assertFalse(workload.claim_eligible)
        self.assertEqual(
            workload.commands_path,
            "bench/vendor-native/ort_doe_ep_identity_commands.json",
        )
        self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_identity_scenario_payload_matches_native_smoke_contract(self) -> None:
        payload = json.loads(IDENTITY_SCENARIO_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 1)
        scenario = payload[0]
        self.assertEqual(scenario["kind"], "vendor-native-benchmark-scenario")
        self.assertEqual(scenario["schemaVersion"], 1)
        self.assertEqual(scenario["scenarioId"], IDENTITY_WORKLOAD_ID)
        self.assertEqual(scenario["caseName"], "identity")

    def test_scenario_payload_matches_native_smoke_contract(self) -> None:
        payload = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 1)
        scenario = payload[0]
        self.assertEqual(scenario["kind"], "vendor-native-benchmark-scenario")
        self.assertEqual(scenario["schemaVersion"], 1)
        self.assertEqual(scenario["scenarioId"], WORKLOAD_ID)
        self.assertEqual(scenario["caseName"], "add_relu")

    def test_matmul_workload_manifest_loads_native_smoke_lane(self) -> None:
        workloads = config_support.load_workloads(
            WORKLOADS_PATH,
            "",
            include_noncomparable=True,
            include_extended=False,
            workload_cohort="all",
            selector={"ids": [MATMUL_WORKLOAD_ID]},
        )
        self.assertEqual(len(workloads), 1)
        workload = workloads[0]
        self.assertEqual(workload.id, MATMUL_WORKLOAD_ID)
        self.assertFalse(workload.comparable)
        self.assertEqual(workload.benchmark_class, "directional")
        self.assertFalse(workload.claim_eligible)
        self.assertEqual(
            workload.commands_path,
            "bench/vendor-native/ort_doe_ep_matmul_commands.json",
        )
        self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_matmul_scenario_payload_matches_native_smoke_contract(self) -> None:
        payload = json.loads(MATMUL_SCENARIO_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 1)
        scenario = payload[0]
        self.assertEqual(scenario["kind"], "vendor-native-benchmark-scenario")
        self.assertEqual(scenario["schemaVersion"], 1)
        self.assertEqual(scenario["scenarioId"], MATMUL_WORKLOAD_ID)
        self.assertEqual(scenario["caseName"], "matmul")

    def test_matmul_add_workload_manifest_loads_native_smoke_lane(self) -> None:
        workloads = config_support.load_workloads(
            WORKLOADS_PATH,
            "",
            include_noncomparable=True,
            include_extended=False,
            workload_cohort="all",
            selector={"ids": [MATMUL_ADD_WORKLOAD_ID]},
        )
        self.assertEqual(len(workloads), 1)
        workload = workloads[0]
        self.assertEqual(workload.id, MATMUL_ADD_WORKLOAD_ID)
        self.assertFalse(workload.comparable)
        self.assertEqual(workload.benchmark_class, "directional")
        self.assertFalse(workload.claim_eligible)
        self.assertEqual(
            workload.commands_path,
            "bench/vendor-native/ort_doe_ep_matmul_add_commands.json",
        )
        self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_matmul_add_scenario_payload_matches_native_smoke_contract(self) -> None:
        payload = json.loads(MATMUL_ADD_SCENARIO_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 1)
        scenario = payload[0]
        self.assertEqual(scenario["kind"], "vendor-native-benchmark-scenario")
        self.assertEqual(scenario["schemaVersion"], 1)
        self.assertEqual(scenario["scenarioId"], MATMUL_ADD_WORKLOAD_ID)
        self.assertEqual(scenario["caseName"], "matmul_add")

    def test_runner_emits_success_trace_for_native_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-native-ort-ep-success-") as tmpdir:
            tmp = Path(tmpdir)
            fake_smoke = tmp / "fake-smoke.py"
            scenario_path = tmp / "scenario.json"
            trace_meta_path = tmp / "trace.meta.json"
            trace_jsonl_path = tmp / "trace.ndjson"
            _write_fake_smoke(fake_smoke, success=True)
            scenario_path.write_text(
                json.dumps(
                    [
                        {
                            "kind": "vendor-native-benchmark-scenario",
                            "schemaVersion": 1,
                            "scenarioId": WORKLOAD_ID,
                            "caseName": "add_relu",
                            "smokeBinaryPath": str(fake_smoke),
                            "pluginPath": str(fake_smoke),
                        }
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--scenario",
                    str(scenario_path),
                    "--trace-meta",
                    str(trace_meta_path),
                    "--trace-jsonl",
                    str(trace_jsonl_path),
                    "--workload",
                    WORKLOAD_ID,
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = json.loads(trace_meta_path.read_text(encoding="utf-8"))
            rows = [
                json.loads(line)
                for line in trace_jsonl_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(meta["runtimeHost"], "native")
        self.assertEqual(meta["benchmarkLane"], "native-ort-doe-ep-smoke")
        self.assertEqual(meta["nativeOrtCaseName"], "add_relu")
        self.assertEqual(meta["executionProvider"], "doe")
        self.assertEqual(meta["executionSuccessCount"], 1)
        self.assertEqual(meta["pluginDebug"]["finalCounters"]["claimedNodes"], 2)
        self.assertEqual(rows[0]["status"], "success")
        self.assertTrue(rows[0]["routedThroughDoe"])
        self.assertTrue(rows[0]["outputsMatch"])

    def test_runner_emits_failure_trace_for_native_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-native-ort-ep-failure-") as tmpdir:
            tmp = Path(tmpdir)
            fake_smoke = tmp / "fake-smoke.py"
            scenario_path = tmp / "scenario.json"
            trace_meta_path = tmp / "trace.meta.json"
            trace_jsonl_path = tmp / "trace.ndjson"
            _write_fake_smoke(fake_smoke, success=False)
            scenario_path.write_text(
                json.dumps(
                    [
                        {
                            "kind": "vendor-native-benchmark-scenario",
                            "schemaVersion": 1,
                            "scenarioId": WORKLOAD_ID,
                            "caseName": "add_relu",
                            "smokeBinaryPath": str(fake_smoke),
                            "pluginPath": str(fake_smoke),
                        }
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--scenario",
                    str(scenario_path),
                    "--trace-meta",
                    str(trace_meta_path),
                    "--trace-jsonl",
                    str(trace_jsonl_path),
                    "--workload",
                    WORKLOAD_ID,
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            meta = json.loads(trace_meta_path.read_text(encoding="utf-8"))
            rows = [
                json.loads(line)
                for line in trace_jsonl_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(meta["runtimeHost"], "native")
        self.assertEqual(meta["executionErrorCount"], 1)
        self.assertTrue(meta["terminalFailureCaptured"])
        self.assertIn("failed", meta["failureMessage"])
        self.assertEqual(rows[0]["status"], "error")
        self.assertIn("failed", rows[0]["errorMessage"])


if __name__ == "__main__":
    unittest.main()
