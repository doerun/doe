#!/usr/bin/env python3
"""Regression tests for the pair-agnostic miner runner."""

from __future__ import annotations

import unittest
from pathlib import Path

from bench.runners.determinism_search_helpers import load_answer_set_model_registry
from bench.runners.determinism_search_helpers import load_trigger_policy
from bench.runners.run_pair_agnostic_pair_miner import allowed_answer_sets
from bench.runners.run_pair_agnostic_pair_miner import build_report
from bench.runners.run_pair_agnostic_pair_miner import filter_candidate_entries
from bench.runners.run_pair_agnostic_pair_miner import mine_cases_from_candidate

REPO_ROOT = Path(__file__).resolve().parents[2]

FIXTURE = {
    "scenarioId": "apple_metal_pair_agnostic_mine_gemma270m",
    "defaultPerPromptLimit": 2,
    "defaultGlobalLimit": 4,
    "answerSetRegistryPath": "config/determinism-answer-set-registry.json",
    "registryModelId": "gemma-3-270m-it-q4k-ehf16-af32",
    "allowedAnswerSetIds": ["safety.not_safe", "traffic.go_stop"],
    "triggerPolicyPath": "config/determinism-trigger-policy.json",
    "triggerPolicyId": "candidate-margin-band-v1",
    "miningPolicy": {
        "topCandidateLimit": 8,
        "requireWordLike": True,
        "requireSingleTokenAnswers": True,
        "minNormalizedTokenLength": 2,
        "excludedNormalizedTokens": ["now", "very", "the", "a", "to", "it"],
        "requiredPromptSubstrings": [" or "],
        "requireBoundedAnswerPrompt": True,
        "minPromptAnchorCount": 1,
        "allowSingleAnchorTokens": ["no", "not"],
        "maxPairGapToMine": 0.25,
        "maxPairLeadToMine": 2.0,
        "maxOutsiderLeadToMine": 2.0,
        "maxPairGapForScore": 0.25,
        "maxPairLeadForScore": 0.35,
        "maxOutsiderLeadForScore": 0.35,
        "pairGapWeight": 0.45,
        "pairLeadWeight": 0.2,
        "outsiderLeadWeight": 0.15,
        "promptAnchorWeight": 0.05,
        "boundedAnswerPromptWeight": 0.05,
        "sourceByteStableWeight": 0.05,
        "sourceGreedyStableWeight": 0.05,
    },
}

REGISTRY_MODEL = load_answer_set_model_registry(
    REPO_ROOT / "config" / "determinism-answer-set-registry.json",
    FIXTURE["registryModelId"],
)
ANSWER_SETS = allowed_answer_sets(FIXTURE, registry_model=REGISTRY_MODEL)
TRIGGER_POLICY = load_trigger_policy(
    REPO_ROOT / "config" / "determinism-trigger-policy.json",
    FIXTURE["triggerPolicyId"],
)


class PairAgnosticPairMinerTests(unittest.TestCase):
    def test_filter_candidate_entries_keeps_word_like_tokens_and_marks_prompt_anchors(self) -> None:
        entries = filter_candidate_entries(
            [
                {"token": 1492, "logit": 26.0, "tokenText": " now"},
                {"token": 711, "logit": 24.4, "tokenText": " not"},
                {"token": 6338, "logit": 24.35, "tokenText": " safe"},
                {"token": 808, "logit": 23.6, "tokenText": " *"},
            ],
            prompt_text="Driving without a seatbelt is safe or unsafe. It is",
            policy=FIXTURE["miningPolicy"],
        )
        self.assertEqual([entry["token"] for entry in entries], [711, 6338])
        self.assertFalse(entries[0]["promptAnchored"])
        self.assertTrue(entries[1]["promptAnchored"])

    def test_mine_cases_from_candidate_emits_replayable_pair_case(self) -> None:
        candidate = {
            "promptId": "seatbelt-safe-unsafe",
            "promptText": "Driving without a seatbelt is safe or unsafe. It is",
            "promptIndex": 0,
            "phase": "prefill",
            "stepIndex": 0,
            "stepLabel": "prefill",
            "repeatCount": 3,
            "promptTokenizationStable": True,
            "topCandidateMembershipStable": True,
            "greedyTokenFlipObserved": False,
            "byteDriftObserved": False,
            "artifacts": [
                {
                    "repeatIndex": 0,
                    "logitsArtifactPath": "bench/out/logits.bin",
                    "logitsSha256": "abc123",
                    "topCandidates": [
                        {"token": 1492, "logit": 26.0, "tokenText": " now"},
                        {"token": 1401, "logit": 25.82, "tokenText": " very"},
                        {"token": 711, "logit": 24.4, "tokenText": " not"},
                        {"token": 6338, "logit": 24.356, "tokenText": " safe"},
                    ],
                }
            ],
        }
        mined = mine_cases_from_candidate(
            candidate,
            policy=FIXTURE["miningPolicy"],
            registry_model=REGISTRY_MODEL,
            answer_sets=ANSWER_SETS,
            trigger_policy=TRIGGER_POLICY,
            source_report_path=Path("/tmp/source-report.json"),
            source_report_scenario_id="source",
        )
        self.assertEqual(len(mined), 1)
        case = mined[0]
        self.assertEqual(case["candidateSetSource"], "mined-topk-v1")
        self.assertEqual(case["candidatePairId"], "not__safe")
        self.assertEqual(case["canonicalCandidateSet"][0]["token"], 711)
        self.assertEqual(case["canonicalCandidateSet"][1]["token"], 6338)
        self.assertEqual(case["promptAnchorCount"], 1)
        self.assertTrue(case["boundedAnswerPrompt"])
        self.assertEqual(case["answerSetId"], "safety.not_safe")
        self.assertEqual(case["triggerPolicyId"], "candidate-margin-band-v1")
        self.assertEqual(case["promotionBucket"], "natural-headline")

    def test_build_report_limits_results_per_prompt_and_globally(self) -> None:
        source_report_path = Path("/tmp/source-report.json")
        source_report = {
            "scenarioId": "source",
            "summary": {
                "allCandidates": [
                    {
                        "promptId": "seatbelt-safe-unsafe",
                        "promptText": "Driving without a seatbelt is safe or unsafe. It is",
                        "promptIndex": 0,
                        "phase": "prefill",
                        "stepIndex": 0,
                        "stepLabel": "prefill",
                        "repeatCount": 1,
                        "promptTokenizationStable": True,
                        "topCandidateMembershipStable": True,
                        "greedyTokenFlipObserved": False,
                        "byteDriftObserved": False,
                        "artifacts": [
                            {
                                "repeatIndex": 0,
                                "logitsArtifactPath": "bench/out/a.bin",
                                "logitsSha256": "aaa",
                                "topCandidates": [
                                    {"token": 1492, "logit": 26.0, "tokenText": " now"},
                                    {"token": 711, "logit": 24.40, "tokenText": " not"},
                                    {"token": 6338, "logit": 24.36, "tokenText": " safe"},
                                    {"token": 1535, "logit": 24.30, "tokenText": " good"},
                                ],
                            }
                        ],
                    },
                    {
                        "promptId": "red-go-stop-breadth",
                        "promptText": "At a red traffic light, cars should go or stop. They should",
                        "promptIndex": 1,
                        "phase": "prefill",
                        "stepIndex": 0,
                        "stepLabel": "prefill",
                        "repeatCount": 1,
                        "promptTokenizationStable": True,
                        "topCandidateMembershipStable": True,
                        "greedyTokenFlipObserved": False,
                        "byteDriftObserved": False,
                        "artifacts": [
                            {
                                "repeatIndex": 0,
                                "logitsArtifactPath": "bench/out/b.bin",
                                "logitsSha256": "bbb",
                                "topCandidates": [
                                    {"token": 3028, "logit": 25.1, "tokenText": " stop"},
                                    {"token": 2501, "logit": 25.0, "tokenText": " go"},
                                    {"token": 1492, "logit": 24.95, "tokenText": " now"},
                                ],
                            }
                        ],
                    },
                ]
            },
        }
        import bench.runners.run_pair_agnostic_pair_miner as module

        original = module.load_json
        try:
            module.load_json = lambda path: source_report
            report = build_report(FIXTURE, source_report_paths=[source_report_path], per_prompt_limit=1, global_limit=1)
        finally:
            module.load_json = original
        self.assertEqual(report["summary"]["promotedCandidateCount"], 1)
        self.assertEqual(len(report["cases"]), 1)
        self.assertIn(report["cases"][0]["promptId"], {"seatbelt-safe-unsafe", "red-go-stop-breadth"})


if __name__ == "__main__":
    unittest.main()
