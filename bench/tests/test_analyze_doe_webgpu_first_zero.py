from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.analyze_doe_webgpu_first_zero import (  # noqa: E402
    DiagnosticInputs,
    build_diagnostic,
    load_json,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_f32(path: Path, values: list[float]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack(f"<{len(values)}f", *values))
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AnalyzeDoeWebgpuFirstZeroTests(unittest.TestCase):
    def test_all_zero_logits_with_sampling_failure_matches_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logits_path = root / "final_logits.f32"
            logits_sha = write_f32(logits_path, [0.0, 0.0, 0.0, 0.0])
            stdout_log = root / "stdout.log"
            stderr_log = root / "stderr.log"
            stdout_log.write_text("GPU: hasF16=true, hasSubgroups=true\n", encoding="utf-8")
            stderr_log.write_text(
                "Logits has no finite candidate logits after masking\n",
                encoding="utf-8",
            )
            webgpu_path = root / "webgpu.json"
            exporter_path = root / "exporter.json"
            write_json(
                webgpu_path,
                {
                    "modelId": "gemma-test",
                    "sourceProgram": {"authoringSurface": "doppler_execution_v1"},
                    "runtimeRun": {
                        "exitCode": 1,
                        "stdoutLog": {"path": str(stdout_log)},
                        "stderrLog": {"path": str(stderr_log)},
                    },
                },
            )
            write_json(
                exporter_path,
                {
                    "modelId": "gemma-test",
                    "tensorDigest": {
                        "path": str(logits_path),
                        "sha256": logits_sha,
                    },
                    "decodeTranscript": {
                        "status": "output_ready",
                        "requestedDecodeSteps": 8,
                        "actualDecodeSteps": 1,
                        "stopReason": "eos_token",
                        "generatedTokenIds": {
                            "tokenCount": 1,
                            "preview": [1],
                        },
                        "logitsDigests": [{"stepIndex": 0}],
                    },
                    "kvCacheEvidence": {
                        "status": "output_ready",
                        "realKvCache": True,
                        "byteDigest": "sha256:" + ("1" * 64),
                        "layerDigestCount": 1,
                        "seqLen": 4,
                    },
                },
            )

            diagnostic = build_diagnostic(
                DiagnosticInputs(
                    webgpu_receipt=webgpu_path,
                    exporter_receipt=exporter_path,
                    final_logits=None,
                    stdout_log=None,
                    stderr_log=None,
                )
            )
            schema = load_json(
                REPO_ROOT / "config/doe-webgpu-first-zero-diagnostic.schema.json"
            )
            jsonschema.validate(diagnostic, schema)
            self.assertEqual(diagnostic["status"], "blocked_all_zero_logits")
            self.assertTrue(diagnostic["logitsEvidence"]["allZero"])
            self.assertEqual(diagnostic["logitsEvidence"]["nonzeroCount"], 0)
            self.assertTrue(diagnostic["runtimeSignals"]["hasSubgroupsAdvertised"])

    def test_nonzero_logits_are_not_first_zero_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logits_path = root / "final_logits.f32"
            write_f32(logits_path, [0.0, 1.25, -2.0, 0.0])
            webgpu_path = root / "webgpu.json"
            write_json(
                webgpu_path,
                {
                    "modelId": "gemma-test",
                    "sourceProgram": {"authoringSurface": "doppler_execution_v1"},
                    "runtimeRun": {"exitCode": 0},
                },
            )

            diagnostic = build_diagnostic(
                DiagnosticInputs(
                    webgpu_receipt=webgpu_path,
                    exporter_receipt=None,
                    final_logits=logits_path,
                    stdout_log=None,
                    stderr_log=None,
                )
            )
            self.assertEqual(diagnostic["status"], "not_blocked_by_zero_logits")
            self.assertFalse(diagnostic["logitsEvidence"]["allZero"])
            self.assertEqual(diagnostic["logitsEvidence"]["nonzeroCount"], 2)


if __name__ == "__main__":
    unittest.main()
