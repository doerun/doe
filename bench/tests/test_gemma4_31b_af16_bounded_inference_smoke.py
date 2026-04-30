from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._receipt_hash_guard import evaluate_receipt_hash_spine  # noqa: E402
from bench.tools.synthesize_gemma4_31b_af16_bounded_inference_smoke_receipt import (  # noqa: E402
    ARTIFACT_KIND,
    LANE_KEY,
    MODEL_ID,
    build_receipt,
)

SCHEMA_PATH = (
    REPO_ROOT
    / "config/doe-gemma4-31b-af16-bounded-inference-smoke.schema.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _fixture_digest(manifest: dict) -> str:
    clone = json.loads(json.dumps(manifest))
    clone["fixtureDigest"] = ""
    payload = json.dumps(clone, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _materialize_inputs(root: Path) -> dict[str, Path]:
    manifest_path = root / "doppler" / "manifest.json"
    _write_json(
        manifest_path,
        {
            "modelId": MODEL_ID,
            "quantizationInfo": {
                "weights": "q4k",
                "embeddings": "f16",
                "lmHead": "q4k",
                "compute": "f16",
                "variantTag": LANE_KEY,
            },
        },
    )

    reference_root = root / "fixture"
    reference_report = {
        "metrics": {
            "referenceTranscript": {
                "prompt": {
                    "identity": "The color of the sky is",
                    "hash": "sha256:" + "a" * 64,
                    "tokenIdsHash": "sha256:" + "b" * 64,
                    "tokenCount": 19,
                },
                "output": {
                    "tokensGenerated": 2,
                    "textHash": "sha256:" + "c" * 64,
                    "stopReason": "stop-token",
                    "stopTokenId": 106,
                },
                "tokens": {
                    "ids": [9503, 106],
                    "generatedTokenIdsHash": "sha256:" + "d" * 64,
                },
                "logits": {
                    "perStepDigests": [
                        "sha256:" + "e" * 64,
                        "sha256:" + "f" * 64,
                    ]
                },
            }
        }
    }
    _write_json(reference_root / "reference-report.json", reference_report)
    fixture_manifest = {
        "schemaVersion": 1,
        "artifactKind": "doe_frozen_doppler_reference_manifest",
        "modelId": MODEL_ID,
        "dtypeProfile": {
            "weights": "q4k",
            "embeddings": "f16",
            "lmHead": "q4k",
            "compute": "f16",
            "variantTag": LANE_KEY,
        },
        "transcript": {
            "path": "reference-report.json",
            "sha256": _sha256(reference_root / "reference-report.json"),
            "byteLength": (
                reference_root / "reference-report.json"
            ).stat().st_size,
        },
        "fixtureDigest": "",
    }
    fixture_manifest["fixtureDigest"] = _fixture_digest(fixture_manifest)
    _write_json(
        reference_root / "frozen-reference.manifest.json",
        fixture_manifest,
    )

    host_plan_path = root / "host-plan.json"
    _write_json(
        host_plan_path,
        {
            "schemaVersion": 2,
            "artifactKind": "csl_host_plan",
            "hostPlan": {
                "peGrid": {"width": 246, "height": 236},
                "kernels": [
                    {"name": "embed", "pattern": "gather"},
                    {"name": "sample", "pattern": "sample"},
                ],
                "phases": {
                    "prefill": [{"kernelName": "embed"}],
                    "decode": [{"kernelName": "sample"}],
                },
            },
        },
    )

    compile_receipt_path = root / "compile-receipt.json"
    _write_json(
        compile_receipt_path,
        {
            "artifactKind": "doe_full_graph_compile_attempt_receipt",
            "compileTargetCount": 23,
            "compileSucceededCount": 23,
            "blocker": {"class": "none"},
        },
    )

    per_kernel_summary_path = root / "summary.json"
    _write_json(
        per_kernel_summary_path,
        {
            "artifactKind": "doe_manifest_kernel_probe_summary",
            "totals": {
                "kernelCount": 2,
                "boundCount": 0,
                "blockedCount": 2,
            },
            "kernels": [
                {
                    "kernel": "embed",
                    "verdict": "blocked",
                    "blocker": "dry_run",
                },
                {
                    "kernel": "sample",
                    "verdict": "blocked",
                    "blocker": "dry_run",
                },
            ],
        },
    )
    streaming_trace_path = root / "streaming-trace.json"
    _write_json(
        streaming_trace_path,
        {
            "artifactKind": (
                "doe_gemma4_31b_af16_hostplan_streaming_trace"
            ),
            "status": "blocked",
            "perKernelRefresh": {
                "requested": True,
                "status": "blocked",
                "blocker": {"class": "sdk_python_import_failed"},
            },
            "weightStaging": {
                "requiredWeightCount": 4,
                "resolvedWeightCount": 4,
                "unresolvedWeightKeys": [],
            },
            "blockers": [
                {
                    "class": "sdk_python_import_failed",
                    "detail": "SDK container did not launch.",
                },
                {
                    "class": "combined_session_runtime_absent",
                    "detail": "No session transcript exists.",
                },
            ],
        },
    )
    return {
        "manifest": manifest_path,
        "reference_root": reference_root,
        "host_plan": host_plan_path,
        "compile_receipt": compile_receipt_path,
        "per_kernel_summary": per_kernel_summary_path,
        "streaming_trace": streaming_trace_path,
    }


class Gemma431BAf16BoundedInferenceSmokeReceiptTest(unittest.TestCase):
    def _build(self, *, prefill: int) -> dict:
        self.tmp = tempfile.TemporaryDirectory()
        paths = _materialize_inputs(Path(self.tmp.name))
        return build_receipt(
            source_doppler_manifest=paths["manifest"],
            frozen_reference_root=paths["reference_root"],
            compile_receipt=paths["compile_receipt"],
            host_plan=paths["host_plan"],
            per_kernel_summary=paths["per_kernel_summary"],
            prefill_token_count=prefill,
            decode_token_count=2,
            streaming_trace=paths["streaming_trace"],
        )

    def tearDown(self) -> None:
        tmp = getattr(self, "tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_receipt_schema_and_hash_spine_validate(self) -> None:
        receipt = self._build(prefill=19)
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(receipt)
        self.assertEqual(receipt["artifactKind"], ARTIFACT_KIND)
        self.assertEqual(receipt["laneKey"], LANE_KEY)
        self.assertEqual(receipt["dtypeProfile"]["compute"], "f16")
        report = evaluate_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
        self.assertTrue(report.bound, msg=report.violations)

    def test_two_prefill_token_request_records_shape_mismatch(self) -> None:
        receipt = self._build(prefill=2)
        blocker_classes = {b["class"] for b in receipt["blockers"]}
        self.assertNotIn("source_reference_shape_mismatch", blocker_classes)
        self.assertNotIn(
            "manifest_kernel_dispatch_not_bound",
            blocker_classes,
        )
        self.assertIn("sdk_python_import_failed", blocker_classes)
        self.assertIn(
            "combined_session_runtime_absent",
            blocker_classes,
        )
        self.assertFalse(
            receipt["dopplerReference"]["exactShapeMatchesRequested"]
        )

    def test_matching_reference_shape_drops_shape_mismatch(self) -> None:
        receipt = self._build(prefill=19)
        blocker_classes = {b["class"] for b in receipt["blockers"]}
        self.assertNotIn("source_reference_shape_mismatch", blocker_classes)
        self.assertNotIn(
            "manifest_kernel_dispatch_not_bound",
            blocker_classes,
        )
        self.assertIn("sdk_python_import_failed", blocker_classes)
        self.assertIn(
            "combined_session_runtime_absent",
            blocker_classes,
        )


if __name__ == "__main__":
    unittest.main()
