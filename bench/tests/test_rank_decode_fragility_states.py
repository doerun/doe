import json
import tempfile
import unittest
from pathlib import Path

from bench.lib.config_validation import load_validated_config
from bench.runners.rank_decode_fragility_states import build_report
from bench.runners.rank_decode_fragility_states import write_report


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO_ROOT / "config" / "numeric-stability-decode-fragility-plan.json"


class RankDecodeFragilityStatesTests(unittest.TestCase):
    def setUp(self):
        self.plan = load_validated_config(PLAN_PATH)

    def test_promotable_case_ranks_above_rejects(self):
        cases = [
            {
                "caseId": "promotable-red-light",
                "promptText": "Answer with exactly one word: go or stop. Question: At a red traffic light, cars should Answer:",
                "decodeStepIndex": 0,
                "semanticPriorityClass": "policy-action",
                "sourceArtifactPath": "bench/out/example/red-go-stop.receipt.jsonl",
                "receiptPath": "bench/out/example/red-go-stop.receipt.jsonl",
                "selectedToken": {"fast": 4721, "stable": 817, "reference": 817},
                "selectedTokenText": {"fast": " stop", "stable": " go", "reference": " go"},
                "metrics": {
                    "postTemperatureTop1Margin": 0.02118,
                    "topKBoundaryGap": 0.004,
                    "topPBoundaryGap": 0.003,
                    "cdfDistanceToDraw": 0.002,
                    "adjacentDecodePersistence": 2,
                    "actualSelectedTokenChanged": True,
                    "meaningfulToken": True,
                    "withinPolicyStable": True,
                },
                "upstream": {
                    "fastStableDisagreement": True,
                    "firstDivergenceSemanticOpId": "matmul.logits",
                },
                "suffixReplay": {"available": True, "divergent": True, "replayStepCount": 2},
            },
            {
                "caseId": "reject-junk-token",
                "promptText": "irrelevant",
                "decodeStepIndex": 0,
                "semanticPriorityClass": "other",
                "sourceArtifactPath": "bench/out/example/junk.receipt.jsonl",
                "selectedToken": {"fast": 1, "stable": 2, "reference": 2},
                "metrics": {
                    "postTemperatureTop1Margin": 0.001,
                    "actualSelectedTokenChanged": True,
                    "meaningfulToken": False,
                    "withinPolicyStable": True,
                },
                "upstream": {"fastStableDisagreement": True},
                "suffixReplay": {"available": True, "divergent": True},
            },
        ]

        report = build_report(
            cases=cases,
            plan=self.plan,
            plan_path=PLAN_PATH,
            source_path=Path("bench/out/example/sample-token.jsonl"),
            timestamp="20260329T235000Z",
        )

        self.assertEqual(report["rankedCases"][0]["caseId"], "promotable-red-light")
        self.assertEqual(report["rankedCases"][0]["rankingBucket"], "promotable")
        self.assertEqual(report["rankedCases"][1]["rankingBucket"], "reject")
        self.assertIn("meaningless-token", report["rankedCases"][1]["rejectionReasons"])

    def test_missing_suffix_replay_stays_investigate(self):
        cases = [
            {
                "caseId": "reject-no-suffix",
                "promptText": "Should this run?",
                "decodeStepIndex": 0,
                "semanticPriorityClass": "json-boolean",
                "sourceArtifactPath": "bench/out/example/no-suffix.receipt.jsonl",
                "selectedToken": {"fast": 10, "stable": 11, "reference": 11},
                "metrics": {
                    "postTemperatureTop1Margin": 0.002,
                    "actualSelectedTokenChanged": True,
                    "meaningfulToken": True,
                    "withinPolicyStable": True,
                },
                "upstream": {"fastStableDisagreement": True},
                "suffixReplay": {"available": False, "divergent": False},
            }
        ]
        report = build_report(
            cases=cases,
            plan=self.plan,
            plan_path=PLAN_PATH,
            source_path=Path("bench/out/example/sample-token.jsonl"),
            timestamp="20260329T235100Z",
        )
        ranked = report["rankedCases"][0]
        self.assertEqual(ranked["rankingBucket"], "investigate")
        self.assertIn("missing-suffix-replay", ranked["rejectionReasons"])

    def test_write_report_emits_schema_shaped_json(self):
        cases = [
            {
                "caseId": "investigate-case",
                "promptText": "Answer true or false.",
                "decodeStepIndex": 2,
                "semanticPriorityClass": "json-boolean",
                "sourceArtifactPath": "bench/out/example/investigate.receipt.jsonl",
                "selectedToken": {"fast": 1, "stable": 2, "reference": 2},
                "metrics": {
                    "postTemperatureTop1Margin": 0.04,
                    "topKBoundaryGap": 0.02,
                    "actualSelectedTokenChanged": True,
                    "meaningfulToken": True,
                    "withinPolicyStable": True,
                },
                "upstream": {"fastStableDisagreement": True},
                "suffixReplay": {"available": True, "divergent": True},
            }
        ]
        report = build_report(
            cases=cases,
            plan=self.plan,
            plan_path=PLAN_PATH,
            source_path=Path("bench/out/example/sample-token.jsonl"),
            timestamp="20260329T235200Z",
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = write_report(
                report,
                output_root=Path(tmp_dir),
                timestamp="20260329T235200Z",
            )
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["artifactKind"], "numeric-stability-decode-fragility-report")
            self.assertEqual(payload["summary"]["caseCount"], 1)


if __name__ == "__main__":
    unittest.main()
