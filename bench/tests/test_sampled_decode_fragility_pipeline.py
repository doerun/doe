from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

from bench.lib.sampled_decode_fragility import (  # noqa: E402
    load_json,
    patch_commands_for_sampled_decode,
)
from bench.runners.enrich_sampled_decode_rows import build_rows  # noqa: E402
from bench.runners.promote_sampled_decode_fragility import (  # noqa: E402
    build_catalog,
    build_signature,
)


class SampledDecodeFragilityPipelineTests(unittest.TestCase):
    def test_patch_commands_promotes_sample_uniform_and_semantics(self) -> None:
        commands = load_json(REPO_ROOT / "examples" / "numeric-stability-decode-greedy.commands.json")
        patched = patch_commands_for_sampled_decode(
            commands,
            semantic_stage="patch-test",
            sample_config={
                "temperature": 1.0,
                "topK": 2,
                "topP": 0.75,
                "rngSeed": 17,
                "rngDraw": 0.875,
            },
            max_sample_steps=1,
        )
        sample_dispatch = next(
            command
            for command in patched
            if isinstance(command, dict) and command.get("kernel") == "bench/inference-pipeline/kernels/sample.wgsl"
        )
        self.assertEqual(sample_dispatch["semanticOpId"], "decode.sample_token")
        self.assertEqual(sample_dispatch["semanticStage"], "patch-test.t0")
        self.assertEqual(sample_dispatch["bindings"][0]["buffer_size"], 32)
        uniform_write = next(
            command
            for command in patched
            if isinstance(command, dict)
            and command.get("kind") == "buffer_write"
            and command.get("handle") == 1010
        )
        self.assertEqual(uniform_write["bufferSize"], 32)
        self.assertEqual(len(uniform_write["data"]), 8)
        final_logits = next(
            command
            for command in patched
            if isinstance(command, dict)
            and command.get("kind") == "kernel_dispatch"
            and command.get("semanticOpId") == "decode.final_logits"
        )
        self.assertEqual(final_logits["semanticStage"], "patch-test.t0")

    def test_build_rows_derives_stability_from_repeated_receipts(self) -> None:
        receipt = load_json(REPO_ROOT / "examples" / "doe-numeric-stability-receipt.decode-sample.sample.json")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            receipt_paths = []
            for repeat_index in range(3):
                repeat_path = tmp_root / f"repeat-{repeat_index + 1:02d}.receipt.json"
                repeat_path.write_text((REPO_ROOT / "examples" / "doe-numeric-stability-receipt.decode-sample.sample.json").read_text(encoding="utf-8"), encoding="utf-8")
                receipt_paths.append(str(repeat_path))
            case = {
                "caseId": "decode-demo-sampled",
                "promptText": "Decode demo sampled control case for ordinary Doe execution.",
                "semanticPriorityClass": "other",
                "repeatCount": 3,
                "repeats": [
                    {
                        "status": "success",
                        "decodeReceiptPaths": [receipt_paths[index]],
                    }
                    for index in range(3)
                ],
            }
            rows, enrichment = build_rows(cases=[case], suffix_max_steps=4)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["metrics"]["withinPolicyStable"])
        self.assertFalse(rows[0]["suffixReplay"]["available"])
        self.assertEqual(enrichment["entries"][0]["overrides"]["decodeStepIndex"], 0)

    def test_build_signature_carries_replay_metadata(self) -> None:
        receipt = load_json(REPO_ROOT / "examples" / "doe-numeric-stability-receipt.decode-sample.sample.json")
        ranked_case = {
            "caseId": "decode-demo-sampled::step-0",
            "promptText": "Decode demo sampled control case for ordinary Doe execution.",
            "decodeStepIndex": 0,
            "semanticPriorityClass": "other",
            "selectedTokens": {
                "fast": 0,
                "stable": 0,
                "reference": 1,
                "fastText": "token:0",
                "stableText": "token:0",
                "referenceText": "token:1",
            },
            "metrics": {
                "postTemperatureTop1Margin": 0.24491866,
                "topKBoundaryGap": 0.24491866,
                "topPBoundaryGap": None,
                "cdfDistanceToDraw": 0.125,
                "adjacentDecodePersistence": 0,
                "actualSelectedTokenChanged": True,
                "meaningfulToken": True,
                "withinPolicyStable": True,
                "suffixReplayDivergent": False,
                "suffixReplayAvailable": False,
            },
            "receiptPath": "examples/doe-numeric-stability-receipt.decode-sample.sample.json",
        }
        case = {
            "caseId": "decode-demo-sampled",
            "commandsPath": "examples/numeric-stability-decode-sampled.commands.json",
            "patchedCommandsPath": "bench/out/example/sampled-decode.commands.json",
            "kernelRoot": ".",
            "sampleConfig": {
                "temperature": 1.0,
                "topK": 2,
                "topP": 0.75,
                "rngSeed": 17,
                "rngDraw": 0.875,
            },
            "backend": {
                "vendor": "apple",
                "api": "metal",
                "family": "apple-gpu",
                "driver": "1.0.0",
                "backendLane": "metal_doe_app",
            },
            "maxSampleStepsToCapture": 1,
        }
        validation_plan = load_json(REPO_ROOT / "config" / "numeric-stability-decode-validation-plan.json")
        signature = build_signature(
            ranked_case=ranked_case,
            receipt=receipt,
            case=case,
            validation_plan=validation_plan,
            report_path=REPO_ROOT / "examples" / "numeric-stability-decode-fragility-report.sample.json",
            manifest_path=REPO_ROOT / "examples" / "numeric-stability-decode-harvest.manifest.sample.json",
        )
        self.assertEqual(signature["contractStage"], "metal-promoted")
        self.assertEqual(signature["maxSampleStepsToCapture"], 1)
        catalog = build_catalog(
            signatures=[(REPO_ROOT / "config" / "fragility-signatures" / "decode-promoted" / "signature.json", signature)],
            validation_plan=validation_plan,
            source_report_path=REPO_ROOT / "examples" / "numeric-stability-decode-fragility-report.sample.json",
            source_manifest_path=REPO_ROOT / "examples" / "numeric-stability-decode-harvest.manifest.sample.json",
        )
        self.assertEqual(catalog["summary"]["entryCount"], 1)


if __name__ == "__main__":
    unittest.main()
