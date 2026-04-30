from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.build_csl_webgpu_emulator_input import (  # noqa: E402
    build_emulator_input,
    validate_payload,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_bundle(root: Path) -> dict:
    compile_dir = root / "compile" / "gemv"
    compile_dir.mkdir(parents=True)
    (compile_dir / "layout.csl").write_text(
        '@export_name("matrixData", matrixData, true);\n'
        '@export_name("compute", compute, false);\n',
        encoding="utf-8",
    )
    (compile_dir / "pe_program.csl").write_text(
        "fn compute() void { sys_mod.unblock_cmd_stream(); }\n",
        encoding="utf-8",
    )
    (compile_dir / "layout.metadata.json").write_text('{"exports":2}\n', encoding="utf-8")
    (compile_dir / "pe_program.metadata.json").write_text('{"entry":"compute"}\n', encoding="utf-8")

    host_plan = {
        "schemaVersion": 1,
        "artifactKind": "doe_wgsl_host_plan",
        "peGrid": {"width": 32, "height": 4},
        "kernels": [{"name": "gemv", "pattern": "fused_gemv_dequant", "count": 1}],
        "prefillLaunches": [],
        "decodeLaunches": [],
        "compileTargets": [
            {"name": "gemv", "layout": "gemv/layout.csl", "peProgram": "gemv/pe_program.csl"}
        ],
    }
    runtime_config = {
        "schemaVersion": 1,
        "modelConfig": {
            "hiddenDim": 64,
            "numHeads": 1,
            "headDim": 64,
            "numLayers": 1,
            "vocabSize": 128,
            "maxSeqLen": 16,
            "quantFormat": "q4k",
        },
        "weightMappings": [],
        "stateBuffers": [],
    }
    simulator_plan = {
        "schemaVersion": 1,
        "artifactKind": "doe_wgsl_simulator_plan",
        "target": "wse3",
        "inputs": {
            "hostPlanArtifactPath": "host-plan.json",
            "runtimeConfigPath": "runtime-config.json",
            "compileRootPath": "compile",
            "compileTargets": [
                {
                    "name": "gemv",
                    "layout": "gemv/layout.csl",
                    "peProgram": "gemv/pe_program.csl",
                    "compileParams": {"width": 32, "height": 4},
                    "metadata": {"targetPhase": "base"},
                }
            ],
        },
        "runtime": {"peGrid": {"width": 32, "height": 4}},
        "outputs": {
            "tracePath": "trace.json",
            "stdoutPath": "stdout.log",
            "stderrPath": "stderr.log",
        },
    }
    operation_graph = {
        "schemaVersion": 1,
        "artifactKind": "csl_operation_graph",
        "graphId": "gemv-rpc-launch",
        "orchestrationMode": "memcpy",
        "executionPattern": "rpc_launch",
        "sdkVersionFloor": "2.10.0",
        "compile": {
            "arch": "wse3",
            "fabricDims": [39, 6],
            "fabricOffsets": [4, 1],
            "peGrid": {"width": 32, "height": 4},
            "channels": 1,
            "memcpy": True,
            "params": [
                {"name": "width", "type": "i16", "value": 32},
                {"name": "height", "type": "i16", "value": 4},
            ],
            "importPaths": [],
            "outputDir": "compile/compiled/gemv",
            "compileTargets": [
                {
                    "name": "gemv",
                    "layout": "compile/gemv/layout.csl",
                    "peProgram": "compile/gemv/pe_program.csl",
                    "compileParams": {"width": 32, "height": 4},
                }
            ],
        },
        "exportedSymbols": [
            {
                "name": "matrixData",
                "type": "[*]f32",
                "mutable": True,
                "kind": "device_variable",
            },
            {
                "name": "compute",
                "type": "fn()void",
                "mutable": False,
                "kind": "device_function",
            },
        ],
        "operations": [
            {
                "operationId": "h2d-matrixdata",
                "kind": "memcpy_h2d",
                "targetKind": "device_symbol",
                "deviceSymbol": "matrixData",
                "roi": {"x": 0, "y": 0, "width": 32, "height": 4},
                "elementsPerPE": 1,
                "dataType": "MEMCPY_32BIT",
                "order": "ROW_MAJOR",
                "streaming": False,
                "nonblock": True,
            },
            {
                "operationId": "launch-compute",
                "kind": "launch",
                "functionName": "compute",
                "args": [],
                "nonblock": False,
                "unblockCheckpointRequired": True,
            },
        ],
    }
    driver_result = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_driver_result",
        "target": "wse3",
        "contract": "explicit_driver_outcome",
        "simulatorPlanPath": str(root / "simulator-plan.json"),
        "runtimeConfigPath": str(root / "runtime-config.json"),
        "compile": {
            "attempted": True,
            "status": "succeeded",
            "reason": "compiled",
            "targets": [
                {
                    "name": "gemv",
                    "layoutPath": str(compile_dir / "layout.csl"),
                    "peProgramPath": str(compile_dir / "pe_program.csl"),
                    "outputDir": str(root / "compile" / "compiled" / "gemv"),
                    "status": "succeeded",
                }
            ],
        },
        "run": {
            "attempted": False,
            "status": "blocked",
            "reason": "compile_only_fixture",
            "tracePath": str(root / "trace.json"),
            "traceProduced": False,
            "stdoutPath": str(root / "stdout.log"),
            "stderrPath": str(root / "stderr.log"),
        },
        "operationGraph": operation_graph,
    }

    _write_json(root / "host-plan.json", host_plan)
    _write_json(root / "runtime-config.json", runtime_config)
    _write_json(root / "simulator-plan.json", simulator_plan)
    _write_json(root / "driver-result.json", driver_result)
    return driver_result


class CslWebgpuEmulatorInputTests(unittest.TestCase):
    def test_builds_schema_valid_input_from_driver_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_bundle(root)
            payload = build_emulator_input(bundle_root=root)
            validate_payload(payload, REPO_ROOT / "config/csl-webgpu-emulator-input.schema.json")

            self.assertEqual(payload["artifactKind"], "csl_webgpu_emulator_input")
            self.assertEqual(payload["sources"]["operationGraphSource"], "driver_result")
            self.assertEqual(payload["hostInputs"]["mode"], "unbound")
            self.assertEqual(payload["compileTargets"][0]["name"], "gemv")
            self.assertEqual(payload["compileTargets"][0]["driverStatus"], "succeeded")
            self.assertIn("layoutMetadata", payload["compileTargets"][0])
            self.assertTrue(payload["operationGraphSha256"].startswith("sha256:"))

    def test_binds_doppler_rdrr_inputs_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_bundle(root)
            program_bundle = root / "program-bundle.json"
            rdrr_manifest = root / "manifest.json"
            transcript = root / "reference-transcript.json"
            _write_json(program_bundle, {"schema": "doppler.program-bundle/v1"})
            _write_json(rdrr_manifest, {"format": "RDRR"})
            _write_json(transcript, {"schema": "doppler.reference-transcript/v1"})

            payload = build_emulator_input(
                bundle_root=root,
                program_bundle=program_bundle,
                rdrr_manifest=rdrr_manifest,
                reference_transcript=transcript,
            )

            self.assertEqual(payload["hostInputs"]["mode"], "doppler_rdrr")
            self.assertIn("programBundle", payload["hostInputs"])
            self.assertIn("rdrrManifest", payload["hostInputs"])
            self.assertIn("referenceTranscript", payload["hostInputs"])

    def test_missing_operation_graph_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            driver_result = _seed_bundle(root)
            driver_result.pop("operationGraph")
            _write_json(root / "driver-result.json", driver_result)

            with self.assertRaisesRegex(ValueError, "operation graph is required"):
                build_emulator_input(bundle_root=root)

    def test_schema_rejects_execution_claim_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_bundle(root)
            payload = build_emulator_input(bundle_root=root)
            payload["claimScope"] = "webgpu_execution"

            with self.assertRaises(jsonschema.ValidationError):
                validate_payload(
                    payload,
                    REPO_ROOT / "config/csl-webgpu-emulator-input.schema.json",
                )


if __name__ == "__main__":
    unittest.main()
