import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from bench.runners.normalize_decode_fragility_rows import build_row
from bench.runners.normalize_decode_fragility_rows import load_enrichment
from bench.runners.normalize_decode_fragility_rows import load_receipts
from bench.runners.normalize_decode_fragility_rows import match_enrichment
from bench.runners.normalize_decode_fragility_rows import write_jsonl


REPO_ROOT = Path(__file__).resolve().parents[2]
ENRICHMENT_PATH = REPO_ROOT / "examples" / "numeric-stability-decode-row-enrichment.sample.json"
RECEIPT_SAMPLE_PATH = REPO_ROOT / "examples" / "doe-numeric-stability-receipt.decode-sample.sample.json"


class NormalizeDecodeFragilityRowsTests(unittest.TestCase):
    def test_build_row_uses_receipt_shape_and_enrichment(self):
        receipt = {
            "schemaVersion": 1,
            "mode": "numeric-stability",
            "operatorFamily": "decode-sample-token",
            "semanticOpId": "decode.sample_token",
            "semanticStage": "decode_demo",
            "semanticPhase": "sample_token",
            "policyRegistryPath": "config/numeric-stability-policy.json",
            "policyRegistryVersion": "2026-03-29-execution-profiles-v1",
            "routeTaxonomyVersion": "numeric-stability-routes-v1",
            "proofArtifactPath": "pipeline/lean/artifacts/proven-conditions.json",
            "triggerPolicyId": "numeric-instability/selected-token-disagreement-with-reference-improvement-v1",
            "routingPolicyId": "numeric-stability/prefer-stable-on-selected-token-disagreement-v1",
            "fastPolicyId": "decode-final-logits/forward-f32-v1",
            "stablePolicyId": "decode-final-logits/forward-serial-v1",
            "referencePolicyId": "decode-final-logits/cpu-f64-serial-v1",
            "candidates": [
                {"tokenId": 4721, "label": " stop", "fastLogit": 1.25, "stableLogit": 1.10, "referenceLogit": 1.10},
                {"tokenId": 817, "label": " go", "fastLogit": 1.20, "stableLogit": 1.30, "referenceLogit": 1.30},
                {"tokenId": 12, "label": " wait", "fastLogit": 0.80, "stableLogit": 0.75, "referenceLogit": 0.75},
            ],
            "executionIdentity": None,
            "firstDivergence": {
                "semanticOpId": "matmul.logits",
                "semanticStage": "decode_demo",
                "semanticPhase": "final_logits",
                "fastDigest": "0" * 64,
                "stableDigest": "1" * 64,
            },
            "decodeBoundary": {
                "decodeMode": "greedy-argmax",
                "logitsCoverage": "full-vocab",
                "vocabSize": 3,
                "residualMassUpperBound": None,
                "temperature": 0.7,
                "topK": 2,
                "topP": 0.9,
                "rngSeed": 17,
                "rngDraw": 0.42,
                "survivingTokenSetKind": "top-k",
                "survivingTokenIds": [4721, 817],
                "liveSelectedToken": 4721,
                "liveSelectedMatchesCommittedSelection": True,
                "upstreamLinks": [
                    {
                        "semanticOpId": "decode.final_logits",
                        "semanticStage": "decode_demo",
                        "semanticPhase": "final_logits",
                        "selectedPolicyId": "decode-final-logits/forward-f32-v1",
                        "decision": "accept-fast",
                    }
                ],
                "metrics": {
                    "fastTop1Margin": 0.05,
                    "stableTop1Margin": 0.20,
                    "referenceTop1Margin": 0.20,
                    "topKBoundaryGap": 0.03,
                    "topPBoundaryGap": 0.02,
                    "cdfDistanceToDraw": 0.01,
                    "adjacentDecodePersistence": 1,
                    "actualSelectedTokenChanged": True,
                    "liveSelectedMatchesFast": True,
                    "liveSelectedMatchesStable": False,
                    "liveSelectedMatchesReference": False,
                },
            },
            "selectedToken": {
                "fast": 4721,
                "stable": 817,
                "reference": 817,
                "fastMatchesReference": False,
                "stableMatchesReference": True,
            },
            "trigger": {
                "fired": True,
                "checks": {
                    "firstDivergencePresent": True,
                    "sensitiveOperatorMatched": True,
                    "selectedTokenDisagreement": True,
                    "stableMatchesExactReference": True,
                    "fastMissesExactReference": True,
                },
                "proofLinks": [],
            },
            "route": {
                "decision": "prefer-stable",
                "selectionMode": "stable",
                "committedResultMode": "stable",
                "downstreamAction": "continue",
                "effectApplied": True,
                "selectedPolicyId": "decode-final-logits/forward-serial-v1",
                "selectedToken": 817,
                "proofLinks": [],
                "selectionProofLinks": [],
            },
        }
        enrichments = load_enrichment(ENRICHMENT_PATH)
        overrides = match_enrichment(
            enrichments,
            receipt_path="examples/doe-numeric-stability-receipt.decode-sample.sample.json",
            receipt=receipt,
        )
        row = build_row(
            receipt,
            receipt_path="examples/doe-numeric-stability-receipt.decode-sample.sample.json",
            overrides={
                **overrides,
                "caseId": "red-go-stop-decode0",
                "promptText": "Answer with exactly one word: go or stop. Question: At a red traffic light, cars should Answer:",
                "decodeStepIndex": 0,
                "semanticPriorityClass": "policy-action",
                "withinPolicyStable": True,
                "adjacentDecodePersistence": 2,
                "suffixReplay": {"available": True, "divergent": True, "replayStepCount": 2},
            },
        )
        self.assertEqual(row["caseId"], "red-go-stop-decode0")
        self.assertEqual(row["semanticPriorityClass"], "policy-action")
        self.assertTrue(row["metrics"]["actualSelectedTokenChanged"])
        self.assertTrue(row["metrics"]["liveSelectedMatchesFast"])
        self.assertFalse(row["metrics"]["liveSelectedMatchesStable"])
        self.assertTrue(row["metrics"]["meaningfulToken"])
        self.assertEqual(row["upstream"]["firstDivergenceSemanticOpId"], "matmul.logits")
        self.assertEqual(row["suffixReplay"]["replayStepCount"], 2)
        self.assertEqual(row["metrics"]["postTemperatureTop1Margin"], 0.05)

    def test_write_jsonl_emits_one_row_per_line(self):
        rows = [{"caseId": "case-1"}]
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "rows.jsonl"
            write_jsonl(output_path, rows)
            payload = output_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(payload), 1)
            self.assertEqual(json.loads(payload[0])["caseId"], "case-1")

    def test_checked_in_sample_receipt_preserves_runtime_top1_margin(self):
        receipt = load_receipts(RECEIPT_SAMPLE_PATH)[0]
        enrichments = load_enrichment(ENRICHMENT_PATH)
        overrides = match_enrichment(
            enrichments,
            receipt_path=str(RECEIPT_SAMPLE_PATH),
            receipt=receipt,
        )
        row = build_row(
            receipt,
            receipt_path=str(RECEIPT_SAMPLE_PATH),
            overrides=overrides,
        )
        self.assertAlmostEqual(
            row["metrics"]["postTemperatureTop1Margin"],
            0.24491866,
            places=8,
        )
        self.assertAlmostEqual(
            row["metrics"]["postTemperatureTop1Margin"],
            receipt["decodeBoundary"]["metrics"]["fastTop1Margin"],
            places=8,
        )

    def test_missing_boolean_metrics_fall_back_to_live_selected_token_and_receipt_lanes(self):
        receipt = deepcopy(load_receipts(RECEIPT_SAMPLE_PATH)[0])
        boundary_metrics = receipt["decodeBoundary"]["metrics"]
        del boundary_metrics["actualSelectedTokenChanged"]
        del boundary_metrics["liveSelectedMatchesFast"]
        del boundary_metrics["liveSelectedMatchesStable"]
        del boundary_metrics["liveSelectedMatchesReference"]
        enrichments = load_enrichment(ENRICHMENT_PATH)
        overrides = match_enrichment(
            enrichments,
            receipt_path=str(RECEIPT_SAMPLE_PATH),
            receipt=receipt,
        )
        row = build_row(
            receipt,
            receipt_path=str(RECEIPT_SAMPLE_PATH),
            overrides=overrides,
        )
        self.assertTrue(row["metrics"]["actualSelectedTokenChanged"])
        self.assertTrue(row["metrics"]["liveSelectedMatchesFast"])
        self.assertTrue(row["metrics"]["liveSelectedMatchesStable"])
        self.assertFalse(row["metrics"]["liveSelectedMatchesReference"])


if __name__ == "__main__":
    unittest.main()
