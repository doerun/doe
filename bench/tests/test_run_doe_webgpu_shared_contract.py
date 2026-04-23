from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bench.tools.run_doe_csl_int4ple_transcript import load_json, schema_failures, write_json
from bench.tools.run_doe_webgpu_shared_contract import (
    build_receipt,
    export_command,
)


class TestRunDoeWebgpuSharedContract(unittest.TestCase):
    def test_export_command_uses_contract_prompt_and_decode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            prompt_path = tmp_path / "prompt.txt"
            prompt_path.write_text("hello", encoding="utf-8")
            contract = {
                "modelId": "gemma-test",
                "sourceProgram": {
                    "manifestPath": str(tmp_path / "manifest.json"),
                    "runtimeProfile": "profiles/production",
                },
                "promptInput": {
                    "prompt": {"path": str(prompt_path)},
                    "inputSetComponents": {"useChatTemplate": False},
                },
                "doeWebgpuRuntime": {
                    "host": "node",
                    "hostExecutable": "node",
                    "providerModule": "packages/doe-gpu/src/compute.js",
                    "kernelPathPolicy": {
                        "mode": "capability-aware",
                        "sourceScope": ["model", "manifest", "config"],
                        "allowSources": ["model", "manifest", "config"],
                        "onIncompatible": "remap",
                    },
                },
                "decodeRequest": {
                    "requestedDecodeSteps": 3,
                    "sampling": {
                        "temperature": 0.7,
                        "topK": 40,
                        "topP": 0.95,
                        "repetitionPenalty": 1.25,
                        "seed": 17,
                    },
                },
            }
            (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "node": None,
                    "provider_module": None,
                    "export_tool": "bench/tools/export_doppler_int4ple_reference.mjs",
                    "doppler_root": "/home/x/deco/doppler",
                    "kernel_path_policy_mode": None,
                    "kernel_path_policy_on_incompatible": None,
                    "kernel_path_policy_source_scope": None,
                },
            )()
            command = export_command(
                args=args,
                contract=contract,
                export_out_dir=tmp_path / "export",
            )
            self.assertIn("--decode-steps", command)
            self.assertIn("3", command)
            self.assertIn("--no-chat-template", command)
            self.assertIn("--temperature", command)
            self.assertIn("0.7", command)
            self.assertIn("--top-k", command)
            self.assertIn("40", command)
            self.assertIn("--top-p", command)
            self.assertIn("0.95", command)
            self.assertIn("--repetition-penalty", command)
            self.assertIn("--seed", command)
            self.assertIn("17", command)
            self.assertIn("--kernel-path-policy-mode", command)
            self.assertIn("capability-aware", command)
            self.assertIn("--kernel-path-policy-on-incompatible", command)
            self.assertIn("remap", command)
            self.assertIn("--kernel-path-policy-source-scope", command)

    def test_build_receipt_matches_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            contract_path = tmp_path / "contract.json"
            stdout_log = tmp_path / "stdout.log"
            stderr_log = tmp_path / "stderr.log"
            exporter_receipt_path = tmp_path / "export.json"
            stdout_log.write_text("", encoding="utf-8")
            stderr_log.write_text("", encoding="utf-8")
            exporter_receipt = {
                "exportStatus": "output_ready",
                "tensorDigest": {
                    "status": "output_ready",
                    "path": "final_logits.f32",
                    "sha256": "1" * 64,
                },
                "decodeTranscript": {
                    "status": "output_ready",
                    "requestedDecodeSteps": 2,
                    "actualDecodeSteps": 2,
                },
                "producer": {"webgpuProvider": "doe-provider"},
            }
            write_json(exporter_receipt_path, exporter_receipt)
            contract = {
                "modelId": "gemma-test",
                "sourceProgram": {
                    "authoringSurface": "doppler_execution_v1",
                    "manifestPath": "manifest.json",
                    "manifestSha256": "a" * 64,
                    "graphPath": "graph.json",
                    "graphSha256": "b" * 64,
                    "weightSetId": "weights",
                    "weightSha256": "c" * 64,
                    "inputSetSha256": "d" * 64,
                    "executionDepth": "not_executed",
                },
                "doeWebgpuRuntime": {
                    "host": "node",
                    "hostExecutable": "node",
                    "providerModule": "packages/doe-gpu/src/compute.js",
                    "kernelPathPolicy": {
                        "mode": "capability-aware",
                        "sourceScope": ["model", "manifest", "config"],
                        "allowSources": ["model", "manifest", "config"],
                        "onIncompatible": "remap",
                    },
                },
                "decodeRequest": {
                    "requestedDecodeSteps": 2,
                    "expectedActualDecodeSteps": 2,
                    "expectedStopReason": "decode_steps_exhausted",
                    "samplingSha256": "e" * 64,
                    "inputSetSha256": "d" * 64,
                    "sampling": {"temperature": 0},
                },
            }
            write_json(contract_path, contract)
            args = type(
                "Args",
                (),
                {
                    "node": None,
                    "provider_module": None,
                    "export_tool": "bench/tools/export_doppler_int4ple_reference.mjs",
                    "kernel_path_policy_mode": None,
                    "kernel_path_policy_on_incompatible": None,
                    "kernel_path_policy_source_scope": None,
                },
            )()
            receipt = build_receipt(
                contract=contract,
                contract_path=contract_path,
                exporter_receipt=exporter_receipt,
                exporter_receipt_path=exporter_receipt_path,
                args=args,
                command=["node", "tool"],
                exit_code=0,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )
            schema = load_json(
                Path("config/doe-webgpu-transcript.schema.json").resolve()
            )
            self.assertEqual(schema_failures(receipt, schema), [])
            self.assertEqual(receipt["status"], "output_ready")
            self.assertEqual(
                receipt["webgpuTranscript"]["producer"],
                "doppler_js_webgpu_on_doe",
            )
            self.assertEqual(receipt["runtimeRun"]["jsHost"], "node")
            self.assertEqual(receipt["runtimeRun"]["jsExecutable"], "node")


if __name__ == "__main__":
    unittest.main()
