from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from bench.tools.bind_shared_execution_parity import (
    compare_runs,
    normalize_run,
)
from bench.tools.run_doe_csl_int4ple_transcript import load_json, schema_failures, write_json


class TestBindSharedExecutionParity(unittest.TestCase):
    def test_reference_and_webgpu_pass_when_digests_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left_path = tmp_path / "reference.json"
            right_path = tmp_path / "webgpu.json"
            reference = {
                "modelId": "gemma-test",
                "manifestSha256": "a" * 64,
                "executionGraphSha256": "b" * 64,
                "weightSetSha256": "c" * 64,
                "inputSetSha256": "d" * 64,
                "inputsSynthetic": False,
                "weightsSynthetic": False,
                "decodeTranscript": {
                    "transcript": {"path": "decode.json", "sha256": "e" * 64},
                    "requestedDecodeSteps": 2,
                    "actualDecodeSteps": 2,
                    "stopReason": "decode_steps_exhausted",
                    "generatedTokenIds": {"sha256": "f" * 64},
                    "logitsDigests": [],
                },
            }
            webgpu = {
                "modelId": "gemma-test",
                "status": "output_ready",
                "inputsSynthetic": False,
                "weightsSynthetic": False,
                "sourceProgram": {
                    "manifestSha256": "a" * 64,
                    "graphSha256": "b" * 64,
                    "weightSha256": "c" * 64,
                    "inputSetSha256": "d" * 64,
                },
                "webgpuTranscript": {
                    "decodeTranscript": {
                        "transcript": {"path": "decode.json", "sha256": "e" * 64},
                        "requestedDecodeSteps": 2,
                        "actualDecodeSteps": 2,
                        "stopReason": "decode_steps_exhausted",
                        "generatedTokenIds": {"sha256": "f" * 64},
                        "logitsDigests": [],
                    }
                },
                "kvCacheEvidence": {
                    "status": "output_ready",
                    "realKvCache": True,
                    "blocker": "",
                    "byteDigest": "sha256:" + ("1" * 64),
                    "layerDigestCount": 26,
                    "seqLen": 15,
                    "byteDigests": [
                        {
                            "layer": 0,
                            "seqLen": 15,
                            "keyBytes": 4,
                            "valueBytes": 4,
                            "keyDigest": "sha256:" + ("2" * 64),
                            "valueDigest": "sha256:" + ("3" * 64),
                        }
                    ],
                },
            }
            write_json(left_path, reference)
            write_json(right_path, webgpu)
            left_run = normalize_run("doppler_reference_export", left_path, reference)
            right_run = normalize_run("doe_webgpu_transcript", right_path, webgpu)
            comparison, promotion = compare_runs(left_run, right_run)
            self.assertEqual(comparison["status"], "passed")
            self.assertTrue(promotion["sourceProgramMatched"])
            self.assertTrue(right_run["realKvCacheUsed"])
            self.assertTrue(promotion["realKvCacheUsedOnExecutableLane"])

    def test_webgpu_zero_kv_digest_does_not_count_as_real_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            path = tmp_path / "webgpu.json"
            zero_digest = "sha256:" + hashlib.sha256(bytes(4)).hexdigest()
            webgpu = {
                "status": "output_ready",
                "sourceProgram": {},
                "webgpuTranscript": {"decodeTranscript": {}},
                "kvCacheEvidence": {
                    "status": "output_ready",
                    "realKvCache": True,
                    "blocker": "",
                    "byteDigests": [
                        {
                            "layer": 0,
                            "seqLen": 1,
                            "keyBytes": 4,
                            "valueBytes": 4,
                            "keyDigest": zero_digest,
                            "valueDigest": zero_digest,
                        }
                    ],
                },
            }
            write_json(path, webgpu)
            run = normalize_run("doe_webgpu_transcript", path, webgpu)
            self.assertFalse(run["realKvCacheUsed"])

    def test_schema_accepts_normalized_receipt_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            receipt_path = tmp_path / "parity.json"
            receipt = {
                "schemaVersion": 1,
                "artifactKind": "doe_shared_execution_parity",
                "modelId": "gemma-test",
                "sourceProgram": {
                    "authoringSurface": "doppler_execution_v1",
                    "manifestSha256": "a" * 64,
                    "graphSha256": "b" * 64,
                    "weightSha256": "c" * 64,
                    "inputSetSha256": "d" * 64,
                },
                "leftRun": {
                    "kind": "doppler_reference_export",
                    "status": "output_ready",
                    "sourceArtifact": {"path": "left.json", "sha256": "1" * 64},
                    "sourceProgram": {},
                    "inputsSynthetic": False,
                    "weightsSynthetic": False,
                    "kernelIsStub": False,
                },
                "rightRun": {
                    "kind": "doe_webgpu_transcript",
                    "status": "output_ready",
                    "sourceArtifact": {"path": "right.json", "sha256": "2" * 64},
                    "sourceProgram": {},
                    "inputsSynthetic": False,
                    "weightsSynthetic": False,
                    "kernelIsStub": False,
                },
                "comparison": {
                    "status": "passed",
                    "sameManifestHash": True,
                    "sameGraphHash": True,
                    "sameInputSetHash": True,
                    "requestedDecodeStepsMatched": True,
                    "actualDecodeStepsMatched": True,
                    "stopReasonMatched": True,
                    "generatedTokenIdsMatched": True,
                    "perStepLogitsParityPassed": True,
                    "realKvCacheUsedOnExecutableLane": False,
                    "blocker": "",
                },
                "promotionCriteria": {
                    "sourceProgramMatched": True,
                    "decodeContractMatched": True,
                    "tokenIdsMatched": True,
                    "perStepLogitsParityPassed": True,
                    "realKvCacheUsedOnExecutableLane": False,
                    "syntheticInputsAbsent": True,
                    "syntheticWeightsAbsent": True,
                    "stubStagesAbsent": True,
                },
            }
            write_json(receipt_path, receipt)
            schema = load_json(
                Path("config/doe-shared-execution-parity.schema.json").resolve()
            )
            self.assertEqual(schema_failures(receipt, schema), [])


if __name__ == "__main__":
    unittest.main()
