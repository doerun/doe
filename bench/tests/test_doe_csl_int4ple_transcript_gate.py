from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from bench.gates.doe_csl_int4ple_transcript_gate import (
    check_transcript_reference_parity,
    sha256_file,
)


def write_f32(path: Path, values: list[float]) -> None:
    path.write_bytes(b"".join(struct.pack("<f", value) for value in values))


def transcript(path: Path, sha256: str) -> dict:
    return {
        "status": "output_ready",
        "requestedDecodeSteps": 1,
        "actualDecodeSteps": 1,
        "stopReason": "decode_steps_exhausted",
        "generatedTokenIds": {"sha256": "t" * 64},
        "logitsDigests": [
            {
                "stepIndex": 0,
                "phase": "decode",
                "contextTokenCount": 4,
                "selectedTokenId": 7,
                "dtype": "float32",
                "shape": [4],
                "path": str(path),
                "sha256": sha256,
            }
        ],
    }


def export(path: Path, sha256: str, comparison: str = "max_abs") -> dict:
    return {
        "tolerancePolicy": {
            "comparison": comparison,
            "atol": 1e-3,
            "rtol": 0,
        },
        "decodeTranscript": transcript(path, sha256),
    }


class DoeCslInt4PleTranscriptGateTest(unittest.TestCase):
    def test_generated_tokens_exact_and_logits_tolerance_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reference_logits = root / "reference.f32"
            actual_logits = root / "actual.f32"
            write_f32(reference_logits, [0.1, 0.2, 0.3, 0.4])
            write_f32(actual_logits, [0.1001, 0.2, 0.3, 0.4])
            receipt = {"cslTranscript": transcript(actual_logits, "a" * 64)}
            failures: list[str] = []

            check_transcript_reference_parity(
                receipt,
                export(reference_logits, sha256_file(reference_logits)),
                failures,
            )

            self.assertEqual([], failures)

    def test_generated_token_hash_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            logits = root / "logits.f32"
            write_f32(logits, [0.1, 0.2, 0.3, 0.4])
            receipt = {"cslTranscript": transcript(logits, sha256_file(logits))}
            receipt["cslTranscript"]["generatedTokenIds"]["sha256"] = "x" * 64
            failures: list[str] = []

            check_transcript_reference_parity(
                receipt,
                export(logits, sha256_file(logits)),
                failures,
            )

            self.assertTrue(
                any("generatedTokenIds.sha256" in item for item in failures)
            )

    def test_sha256_exact_policy_rejects_logits_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reference_logits = root / "reference.f32"
            actual_logits = root / "actual.f32"
            write_f32(reference_logits, [0.1, 0.2, 0.3, 0.4])
            write_f32(actual_logits, [0.1001, 0.2, 0.3, 0.4])
            receipt = {"cslTranscript": transcript(actual_logits, "a" * 64)}
            failures: list[str] = []

            check_transcript_reference_parity(
                receipt,
                export(
                    reference_logits,
                    sha256_file(reference_logits),
                    comparison="sha256_exact",
                ),
                failures,
            )

            self.assertTrue(any("sha256_exact" in item for item in failures))


if __name__ == "__main__":
    unittest.main()
