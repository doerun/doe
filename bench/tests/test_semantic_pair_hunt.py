#!/usr/bin/env python3
"""Regression tests for the semantic pair hunt runner."""

from __future__ import annotations

import unittest
from pathlib import Path

from bench.runners.run_semantic_pair_hunt import build_report
from bench.runners.run_semantic_pair_hunt import build_report_from_mined_reports
from bench.runners.run_semantic_pair_hunt import build_state_index
from bench.runners.run_semantic_pair_hunt import enrich_mined_case
from bench.runners.run_semantic_pair_hunt import pair_sort_key
from bench.runners.run_semantic_pair_hunt import scan_pair_in_report


class SemanticPairHuntTests(unittest.TestCase):
    def test_build_state_index_reconstructs_decode_prefix(self) -> None:
        report = {
            "harvest": {
                "runs": [
                    {
                        "repeatIndex": 0,
                        "promptResults": [
                            {
                                "status": "ok",
                                "id": "brakes-safe-unsafe",
                                "text": "Driving without brakes is safe or unsafe. It is",
                                "promptIndex": 0,
                                "promptTokenIds": [10, 20, 30],
                                "greedyTokenSequence": [40, 50],
                                "steps": [
                                    {
                                        "phase": "prefill",
                                        "stepIndex": 0,
                                        "currentIdsLength": 3,
                                        "inputToken": None,
                                    },
                                    {
                                        "phase": "decode",
                                        "stepIndex": 1,
                                        "currentIdsLength": 4,
                                        "inputToken": 40,
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        }
        state_index = build_state_index(report)
        self.assertEqual(
            state_index[("brakes-safe-unsafe", "prefill", 0)]["currentIds"],
            [10, 20, 30],
        )
        self.assertEqual(
            state_index[("brakes-safe-unsafe", "decode", 1)]["currentIds"],
            [10, 20, 30, 40],
        )

    def test_scan_pair_in_report_emits_decode_state_recipe_and_artifact_identity(self) -> None:
        pair = {
            "id": "brakes_not_safe",
            "leftTokenText": " not",
            "rightTokenText": " safe",
            "promptIds": ["brakes-safe-unsafe"],
        }
        report = {
            "scenarioId": "apple_metal_real_logit_hunt_gemma270m_choice_primer",
            "harvest": {
                "runs": [
                    {
                        "repeatIndex": 0,
                        "promptResults": [
                            {
                                "status": "ok",
                                "id": "brakes-safe-unsafe",
                                "text": "Driving without brakes is safe or unsafe. It is",
                                "promptIndex": 0,
                                "promptTokenIds": [1, 2, 3],
                                "greedyTokenSequence": [711],
                                "steps": [
                                    {
                                        "phase": "prefill",
                                        "stepIndex": 0,
                                        "currentIdsLength": 3,
                                        "inputToken": None,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            "summary": {
                "allCandidates": [
                    {
                        "promptId": "brakes-safe-unsafe",
                        "promptText": "Driving without brakes is safe or unsafe. It is",
                        "phase": "prefill",
                        "stepIndex": 0,
                        "stepLabel": "prefill",
                        "minTop2Gap": 0.1,
                        "artifacts": [
                            {
                                "repeatIndex": 0,
                                "logitsArtifactPath": "bench/out/brakes.bin",
                                "logitsSha256": "abc123",
                                "topCandidates": [
                                    {"token": 1492, "tokenText": " now", "logit": 23.95},
                                    {"token": 711, "tokenText": " not", "logit": 23.02},
                                    {"token": 6338, "tokenText": " safe", "logit": 22.04},
                                ],
                            }
                        ],
                    }
                ]
            },
        }
        matches = scan_pair_in_report(pair=pair, report=report, report_path=Path("/tmp/source.json"))
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match["pairId"], "brakes_not_safe")
        self.assertEqual(match["leftToken"], 711)
        self.assertEqual(match["rightToken"], 6338)
        self.assertEqual(match["logitsArtifactPath"], "bench/out/brakes.bin")
        self.assertEqual(match["logitsSha256"], "abc123")
        self.assertEqual(match["decodeStateRecipe"]["promptTokenIds"], [1, 2, 3])
        self.assertEqual(match["decodeStateRecipe"]["decodePrefixTokenIds"], [])

    def test_pair_sort_key_prefers_tighter_semantic_gap_then_closer_to_top(self) -> None:
        ranked = sorted(
            [
                {"pairGap": 0.2, "pairLeadFromTop": 0.4, "leftRank": 2, "rightRank": 3},
                {"pairGap": 0.2, "pairLeadFromTop": 0.1, "leftRank": 4, "rightRank": 5},
                {"pairGap": 0.1, "pairLeadFromTop": 0.9, "leftRank": 7, "rightRank": 8},
            ],
            key=pair_sort_key,
        )
        self.assertEqual(ranked[0]["pairGap"], 0.1)
        self.assertEqual(ranked[1]["pairLeadFromTop"], 0.1)

    def test_build_report_tracks_unmatched_pair_ids(self) -> None:
        fixture = {
            "scenarioId": "apple_metal_semantic_pair_hunt_gemma270m",
            "defaultPerPairLimit": 2,
            "semanticPairs": [
                {
                    "id": "match",
                    "leftTokenText": " not",
                    "rightTokenText": " safe",
                    "promptIds": ["brakes-safe-unsafe"],
                },
                {
                    "id": "miss",
                    "leftTokenText": " yes",
                    "rightTokenText": " no",
                    "promptIds": ["brakes-safe-unsafe"],
                },
            ],
        }
        source_report_path = Path("/tmp/source-report.json")
        report = {
            "scenarioId": "src",
            "harvest": {
                "runs": [
                    {
                        "repeatIndex": 0,
                        "promptResults": [
                            {
                                "status": "ok",
                                "id": "brakes-safe-unsafe",
                                "text": "Driving without brakes is safe or unsafe. It is",
                                "promptIndex": 0,
                                "promptTokenIds": [1, 2, 3],
                                "greedyTokenSequence": [711],
                                "steps": [{"phase": "prefill", "stepIndex": 0, "currentIdsLength": 3}],
                            }
                        ],
                    }
                ]
            },
            "summary": {
                "allCandidates": [
                    {
                        "promptId": "brakes-safe-unsafe",
                        "promptText": "Driving without brakes is safe or unsafe. It is",
                        "phase": "prefill",
                        "stepIndex": 0,
                        "stepLabel": "prefill",
                        "minTop2Gap": 0.1,
                        "artifacts": [
                            {
                                "repeatIndex": 0,
                                "logitsArtifactPath": "bench/out/brakes.bin",
                                "logitsSha256": "abc123",
                                "topCandidates": [
                                    {"token": 1492, "tokenText": " now", "logit": 23.95},
                                    {"token": 711, "tokenText": " not", "logit": 23.02},
                                    {"token": 6338, "tokenText": " safe", "logit": 22.04},
                                ],
                            }
                        ],
                    }
                ]
            },
        }

        import bench.runners.run_semantic_pair_hunt as module

        original = module.load_json
        try:
            module.load_json = lambda path: report
            built = build_report(fixture, source_report_paths=[source_report_path], per_pair_limit=2)
        finally:
            module.load_json = original
        self.assertEqual(built["summary"]["matchedPairCount"], 1)
        self.assertEqual(built["summary"]["unmatchedPairIds"], ["miss"])

    def test_enrich_mined_case_adds_decode_state_recipe(self) -> None:
        source_index = {
            "bench/out/source.real-logit-hunt.json": {
                "stateIndex": {
                    ("seatbelt-safe-unsafe", "prefill", 0): {
                        "promptTokenIds": [1, 2, 3],
                        "currentIds": [1, 2, 3],
                        "currentIdsLength": 3,
                        "recordedCurrentIdsLength": 3,
                        "inputToken": None,
                        "greedyTokenSequence": [711],
                    }
                }
            }
        }
        enriched = enrich_mined_case(
            {
                "candidatePairId": "not__safe",
                "sourceReportPath": "bench/out/source.real-logit-hunt.json",
                "promptId": "seatbelt-safe-unsafe",
                "phase": "prefill",
                "stepIndex": 0,
            },
            source_index=source_index,
        )
        self.assertEqual(enriched["decodeStateRecipe"]["promptTokenIds"], [1, 2, 3])
        self.assertEqual(enriched["decodeStateRecipe"]["decodePrefixTokenIds"], [])

    def test_build_report_from_mined_reports_groups_cases_by_pair_id(self) -> None:
        source_report = {
            "harvest": {
                "runs": [
                    {
                        "repeatIndex": 0,
                        "promptResults": [
                            {
                                "status": "ok",
                                "id": "seatbelt-safe-unsafe",
                                "text": "Driving without a seatbelt is safe or unsafe. It is",
                                "promptIndex": 0,
                                "promptTokenIds": [1, 2, 3],
                                "greedyTokenSequence": [711],
                                "steps": [{"phase": "prefill", "stepIndex": 0, "currentIdsLength": 3}],
                            }
                        ],
                    }
                ]
            }
        }
        mined_report = {
            "scenarioId": "apple_metal_pair_agnostic_mine_gemma270m",
            "sourceReportPaths": ["bench/out/source.real-logit-hunt.json"],
            "cases": [
                {
                    "candidatePairId": "not__safe",
                    "candidateSetSource": "mined-topk-v1",
                    "sourceReportPath": "bench/out/source.real-logit-hunt.json",
                    "sourceReportScenarioId": "source",
                    "sourceRepeatIndex": 0,
                    "promptId": "seatbelt-safe-unsafe",
                    "promptText": "Driving without a seatbelt is safe or unsafe. It is",
                    "phase": "prefill",
                    "stepIndex": 0,
                    "stepLabel": "prefill",
                    "pairGap": 0.04,
                    "pairLeadFromTop": 0.0,
                    "leftTokenText": " not",
                    "leftToken": 711,
                    "leftLogit": 24.4,
                    "leftRank": 1,
                    "rightTokenText": " safe",
                    "rightToken": 6338,
                    "rightLogit": 24.36,
                    "rightRank": 2,
                    "usefulnessScore": 0.91,
                }
            ],
        }

        import bench.runners.run_semantic_pair_hunt as module

        original = module.load_json
        try:
            module.load_json = lambda path: source_report if "source.real-logit-hunt" in str(path) else mined_report
            built = build_report_from_mined_reports([mined_report], per_pair_limit=2)
        finally:
            module.load_json = original
        self.assertEqual(built["sourceKind"], "mined-topk-v1")
        self.assertEqual(built["summary"]["matchedPairCount"], 1)
        self.assertEqual(built["pairs"][0]["pairId"], "not__safe")
        self.assertEqual(built["pairs"][0]["topMatches"][0]["decodeStateRecipe"]["promptTokenIds"], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
