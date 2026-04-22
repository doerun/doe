from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.prepare_doe_csl_int4ple_hardware_receipt import (  # noqa: E402
    build_receipt,
    write_json,
)


SOURCE_PROGRAM = {
    "authoringSurface": "doppler_execution_v1",
    "manifestPath": "/tmp/manifest.json",
    "manifestSha256": "manifest-sha",
    "graphPath": "graph.json",
    "graphSha256": "graph-sha",
    "weightSetId": "weights",
    "weightSha256": "weight-sha",
    "inputSetSha256": "input-sha",
    "programBundle": {
        "path": "program-bundle.json",
        "sha256": "bundle-sha",
        "source": "test",
    },
    "programBundleId": "bundle-id",
}


def write_json_file(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class Int4PleHardwareReceiptTests(unittest.TestCase):
    def test_pending_receipt_gates_and_strict_hardware_mode_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            parity_path = root / "parity.json"
            transcript_path = root / "transcript.json"
            receipt_path = root / "hardware.json"
            parity = {
                "modelId": "gemma-4-e2b-it-q4k-ehf16-af32-int4ple",
                "sourceProgram": SOURCE_PROGRAM,
                "referenceRun": {
                    "decodeTranscript": {
                        "path": "reference-transcript.json",
                        "sha256": "reference-sha",
                        "requestedDecodeSteps": 8,
                        "actualDecodeSteps": 8,
                        "stopReason": "decode_steps_exhausted",
                        "decodeStepsProduced": 8,
                        "generatedTokenIdsSha256": "tokens-sha",
                        "logitsDigestSha256": "logits-sha",
                    }
                },
                "comparison": {"status": "failed"},
                "promotionCriteria": {
                    "fullModelDepthExecuted": False,
                    "decodeTranscriptBound": False,
                    "realKvCacheUsed": False,
                    "stubStagesAbsent": True,
                    "syntheticInputsAbsent": True,
                    "syntheticWeightsAbsent": True,
                },
            }
            transcript = {
                "sourceProgram": SOURCE_PROGRAM,
                "cslTranscript": {
                    "requestedDecodeSteps": 8,
                    "actualDecodeSteps": 0,
                    "stopReason": "not_run",
                    "transcript": {"path": "pending", "sha256": "pending"},
                    "generatedTokenIds": {"sha256": "pending"},
                    "logitsDigests": [],
                },
                "kvCacheEvidence": {
                    "realKvCache": False,
                    "cacheReadCount": 0,
                    "cacheWriteCount": 0,
                    "layerSpanCoverage": {
                        "coveredLayerCount": 0,
                        "layerCount": 35,
                    },
                    "stepStateDigests": [],
                },
            }
            write_json_file(parity_path, parity)
            write_json_file(transcript_path, transcript)
            args = argparse.Namespace(
                execution_target="system",
                program_bundle="/tmp/program-bundle.json",
            )
            receipt = build_receipt(args, parity_path, transcript_path)
            write_json(receipt_path, receipt)

            gate = REPO_ROOT / "bench/gates/doe_csl_int4ple_hardware_receipt_gate.py"
            passed = subprocess.run(
                [sys.executable, str(gate), "--receipt", str(receipt_path)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            strict = subprocess.run(
                [
                    sys.executable,
                    str(gate),
                    "--receipt",
                    str(receipt_path),
                    "--require-hardware-success",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertNotEqual(strict.returncode, 0)
            self.assertIn("expected 'hardware_success'", strict.stdout)


if __name__ == "__main__":
    unittest.main()
