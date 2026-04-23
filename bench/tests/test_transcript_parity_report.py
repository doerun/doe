#!/usr/bin/env python3
"""Focused tests for the generic transcript parity report builder."""

from __future__ import annotations

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

from bench.tools.build_transcript_parity_report import (  # noqa: E402
    build_report,
    write_json,
)


def write_f32(path: Path, values: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"".join(struct.pack("<f", value) for value in values)
    path.write_bytes(raw)


def sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


SOURCE_PROGRAM = {
    "authoringSurface": "doppler_execution_v1",
    "manifestSha256": "m" * 64,
    "graphSha256": "g" * 64,
    "weightSha256": "w" * 64,
    "inputSetSha256": "i" * 64,
    "programBundleId": "bundle-01",
}


def reference_export(
    transcript_path: Path,
    tokens_sha256: str,
    logits_path: Path,
    logits_sha256: str,
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doppler_int4ple_reference_export",
        "exportStatus": "output_ready",
        "modelId": "gemma-test",
        "manifestSha256": SOURCE_PROGRAM["manifestSha256"],
        "executionGraphSha256": SOURCE_PROGRAM["graphSha256"],
        "weightSetSha256": SOURCE_PROGRAM["weightSha256"],
        "inputSetSha256": SOURCE_PROGRAM["inputSetSha256"],
        "programBundleId": SOURCE_PROGRAM["programBundleId"],
        "inputsSynthetic": False,
        "weightsSynthetic": False,
        "tolerancePolicy": {
            "comparison": "max_abs",
            "atol": 1e-3,
            "rtol": 0,
        },
        "decodeTranscript": {
            "status": "output_ready",
            "transcript": {
                "path": str(transcript_path),
                "sha256": sha256_file(transcript_path),
            },
            "requestedDecodeSteps": 1,
            "actualDecodeSteps": 1,
            "decodeStepsProduced": 1,
            "stopReason": "decode_steps_exhausted",
            "generatedTokenIds": {
                "path": "tokens-reference.u32",
                "sha256": tokens_sha256,
                "dtype": "uint32",
                "tokenCount": 1,
            },
            "logitsDigests": [
                {
                    "stepIndex": 0,
                    "phase": "decode",
                    "contextTokenCount": 4,
                    "selectedTokenId": 7,
                    "dtype": "float32",
                    "shape": [4],
                    "path": str(logits_path),
                    "sha256": logits_sha256,
                    "byteLength": 16,
                }
            ],
        },
    }


def generic_transcript_receipt(
    transcript_path: Path,
    tokens_sha256: str,
    logits_path: Path,
    logits_sha256: str,
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_webgpu_transcript_receipt",
        "status": "output_ready",
        "modelId": "gemma-test",
        "sourceProgram": dict(SOURCE_PROGRAM),
        "inputsSynthetic": False,
        "weightsSynthetic": False,
        "transcript": {
            "status": "output_ready",
            "transcript": {
                "path": str(transcript_path),
                "sha256": sha256_file(transcript_path),
            },
            "requestedDecodeSteps": 1,
            "actualDecodeSteps": 1,
            "decodeStepsProduced": 1,
            "stopReason": "decode_steps_exhausted",
            "generatedTokenIds": {
                "path": "tokens-webgpu.u32",
                "sha256": tokens_sha256,
                "dtype": "uint32",
                "tokenCount": 1,
            },
            "logitsDigests": [
                {
                    "stepIndex": 0,
                    "phase": "decode",
                    "contextTokenCount": 4,
                    "selectedTokenId": 7,
                    "dtype": "float32",
                    "shape": [4],
                    "path": str(logits_path),
                    "sha256": logits_sha256,
                    "byteLength": 16,
                }
            ],
        },
    }


def csl_transcript_receipt(
    transcript_path: Path,
    tokens_sha256: str,
    logits_path: Path,
    logits_sha256: str,
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_int4ple_transcript",
        "status": "simulator_success",
        "modelId": "gemma-test",
        "sourceProgram": dict(SOURCE_PROGRAM),
        "inputsSynthetic": False,
        "weightsSynthetic": False,
        "kvCacheEvidence": {"realKvCache": True},
        "simulatorRun": {"kernelIsStub": False},
        "cslTranscript": {
            "status": "output_ready",
            "transcript": {
                "path": str(transcript_path),
                "sha256": sha256_file(transcript_path),
            },
            "requestedDecodeSteps": 1,
            "actualDecodeSteps": 1,
            "decodeStepsProduced": 1,
            "stopReason": "decode_steps_exhausted",
            "generatedTokenIds": {
                "path": "tokens-csl.u32",
                "sha256": tokens_sha256,
                "dtype": "uint32",
                "tokenCount": 1,
            },
            "logitsDigests": [
                {
                    "stepIndex": 0,
                    "phase": "decode",
                    "contextTokenCount": 4,
                    "selectedTokenId": 7,
                    "dtype": "float32",
                    "shape": [4],
                    "path": str(logits_path),
                    "sha256": logits_sha256,
                    "byteLength": 16,
                }
            ],
        },
    }


class TranscriptParityReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads(
            (
                REPO_ROOT / "config" / "doe-transcript-parity-report.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.validator = jsonschema.Draft202012Validator(self.schema)

    def test_build_report_compares_reference_webgpu_and_csl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reference_logits = root / "reference_logits.f32"
            webgpu_logits = root / "webgpu_logits.f32"
            csl_logits = root / "csl_logits.f32"
            reference_transcript_path = root / "reference_transcript.json"
            webgpu_transcript_path = root / "webgpu_transcript.json"
            csl_transcript_path = root / "csl_transcript.json"

            write_f32(reference_logits, [0.1, 0.2, 0.3, 0.4])
            write_f32(webgpu_logits, [0.1, 0.2, 0.3, 0.4])
            write_f32(csl_logits, [0.1, 0.2, 0.3, 0.4])
            write_json(reference_transcript_path, {"steps": [7]})
            write_json(webgpu_transcript_path, {"steps": [7]})
            write_json(csl_transcript_path, {"steps": [7]})

            reference_path = root / "reference.json"
            webgpu_path = root / "webgpu.json"
            csl_path = root / "csl.json"
            write_json(
                reference_path,
                reference_export(
                    reference_transcript_path,
                    "t" * 64,
                    reference_logits,
                    sha256_file(reference_logits),
                ),
            )
            write_json(
                webgpu_path,
                generic_transcript_receipt(
                    webgpu_transcript_path,
                    "t" * 64,
                    webgpu_logits,
                    sha256_file(webgpu_logits),
                ),
            )
            write_json(
                csl_path,
                csl_transcript_receipt(
                    csl_transcript_path,
                    "t" * 64,
                    csl_logits,
                    sha256_file(csl_logits),
                ),
            )

            report = build_report(
                reference_export_path=reference_path,
                lanes=[("webgpu", webgpu_path), ("csl", csl_path)],
                schema_path=REPO_ROOT
                / "config"
                / "doe-transcript-parity-report.schema.json",
            )

            errors = sorted(
                self.validator.iter_errors(report),
                key=lambda item: tuple(str(part) for part in item.absolute_path),
            )
            self.assertEqual([], errors)
            self.assertEqual(3, report["summary"]["comparisonCount"])
            self.assertEqual(3, report["summary"]["passedCount"])
            self.assertTrue(report["summary"]["sameSourceProgramAcrossParticipants"])

    def test_source_program_drift_marks_failed_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            logits_path = root / "logits.f32"
            transcript_path = root / "transcript.json"
            write_f32(logits_path, [1.0, 2.0, 3.0, 4.0])
            write_json(transcript_path, {"steps": [7]})

            reference_path = root / "reference.json"
            webgpu_path = root / "webgpu.json"
            write_json(
                reference_path,
                reference_export(
                    transcript_path,
                    "a" * 64,
                    logits_path,
                    sha256_file(logits_path),
                ),
            )
            drifted = generic_transcript_receipt(
                transcript_path,
                "a" * 64,
                logits_path,
                sha256_file(logits_path),
            )
            drifted["sourceProgram"]["weightSha256"] = "z" * 64
            write_json(webgpu_path, drifted)

            report = build_report(
                reference_export_path=reference_path,
                lanes=[("webgpu", webgpu_path)],
                schema_path=REPO_ROOT
                / "config"
                / "doe-transcript-parity-report.schema.json",
            )

            comparison = report["comparisons"][0]
            self.assertEqual("failed", comparison["status"])
            self.assertFalse(comparison["sourceProgram"]["weightSha256Match"])
            self.assertFalse(report["summary"]["sameSourceProgramAcrossParticipants"])

    def test_missing_logits_artifact_marks_blocked_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reference_logits = root / "reference_logits.f32"
            transcript_path = root / "transcript.json"
            write_f32(reference_logits, [1.0, 2.0, 3.0, 4.0])
            write_json(transcript_path, {"steps": [7]})

            reference_path = root / "reference.json"
            webgpu_path = root / "webgpu.json"
            write_json(
                reference_path,
                reference_export(
                    transcript_path,
                    "a" * 64,
                    reference_logits,
                    sha256_file(reference_logits),
                ),
            )
            missing = generic_transcript_receipt(
                transcript_path,
                "a" * 64,
                root / "missing_logits.f32",
                "b" * 64,
            )
            write_json(webgpu_path, missing)

            report = build_report(
                reference_export_path=reference_path,
                lanes=[("webgpu", webgpu_path)],
                schema_path=REPO_ROOT
                / "config"
                / "doe-transcript-parity-report.schema.json",
            )

            comparison = report["comparisons"][0]
            self.assertEqual("blocked", comparison["status"])
            self.assertFalse(comparison["transcript"]["comparable"])
            self.assertIn("missing_logits.f32", comparison["blocker"])


if __name__ == "__main__":
    unittest.main()
