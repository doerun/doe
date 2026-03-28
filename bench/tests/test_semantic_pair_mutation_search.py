#!/usr/bin/env python3
"""Regression tests for the semantic pair mutation search runner."""

from __future__ import annotations

import unittest
from pathlib import Path

from bench.runners.run_semantic_pair_mutation_search import build_prompt_candidates
from bench.runners.run_semantic_pair_mutation_search import build_report
from bench.runners.run_semantic_pair_mutation_search import compare_mutation
from bench.runners.run_semantic_pair_mutation_search import render_mutation_prompt


FIXTURE = {
    "scenarioId": "apple_metal_semantic_pair_mutation_search_gemma270m",
    "pairMiningFixturePath": "bench/fixtures/determinism/apple-metal-pair-agnostic-mine.gemma270m.json",
    "dopplerRepoPath": "../doppler",
    "modelArtifactPath": "../doppler/tmp/model",
    "modelId": "gemma-3-270m",
    "defaultCaseCount": 2,
    "defaultRepeatCount": 1,
    "decodeSteps": 1,
    "topK": 24,
    "topCandidatesToKeep": 12,
    "persistLogits": True,
    "browser": {"repeatIsolation": "new-page"},
    "mutationTemplates": [
        {"id": "one-word-choice", "kind": "template", "template": "{prompt} Answer with exactly one word: {left} or {right}."},
        {"id": "swap-inline-choice", "kind": "swap-inline-choice"},
    ],
    "promotionPolicy": {"minimumUsefulnessDelta": 0.01},
}


class SemanticPairMutationSearchTests(unittest.TestCase):
    def test_render_mutation_prompt_swaps_inline_choice(self) -> None:
        case = {
            "promptText": "At a red traffic light, cars should go or stop. They should",
            "leftTokenText": " go",
            "rightTokenText": " stop",
        }
        rendered = render_mutation_prompt({"id": "swap", "kind": "swap-inline-choice"}, case=case)
        self.assertEqual(rendered, "At a red traffic light, cars should stop or go. They should")

    def test_build_prompt_candidates_dedupes_per_mutation(self) -> None:
        case = {
            "pairId": "go__stop",
            "promptId": "red-go-stop",
            "promptText": "At a red traffic light, cars should go or stop. They should",
            "leftTokenText": " go",
            "rightTokenText": " stop",
        }
        prompt_candidates, metadata = build_prompt_candidates([case], templates=FIXTURE["mutationTemplates"])
        self.assertEqual(len(prompt_candidates), 2)
        self.assertEqual(len(metadata), 2)

    def test_compare_mutation_marks_improved_cases(self) -> None:
        comparison = compare_mutation(
            prompt_id="seatbelt-safe-unsafe--not__safe--one-word-choice",
            metadata={
                "templateId": "one-word-choice",
                "mutationKind": "template",
                "mutatedPromptText": "Driving without a seatbelt is safe or unsafe. It is Answer with exactly one word: not or safe.",
                "sourceCase": {
                    "pairId": "not__safe",
                    "promptId": "seatbelt-safe-unsafe",
                    "promptText": "Driving without a seatbelt is safe or unsafe. It is",
                    "phase": "prefill",
                    "stepIndex": 0,
                    "pairGap": 0.04,
                    "outsiderLead": 0.0,
                    "pairLeadFromTop": 0.0,
                    "usefulnessScore": 0.91,
                },
            },
            mutated_case={"usefulnessScore": 0.95, "pairGap": 0.02, "outsiderLead": 0.0, "pairLeadFromTop": 0.0},
            minimum_usefulness_delta=0.01,
        )
        self.assertTrue(comparison["improved"])
        self.assertEqual(comparison["mutatedPromptId"], "seatbelt-safe-unsafe--not__safe--one-word-choice")

    def test_build_report_emits_promoted_mined_cases(self) -> None:
        source_report = {
            "scenarioId": "apple_metal_semantic_pair_hunt_gemma270m_choice_breadth",
            "summary": {
                "bestOverallMatches": [
                    {
                        "pairId": "not__safe",
                        "promptId": "seatbelt-safe-unsafe",
                        "promptText": "Driving without a seatbelt is safe or unsafe. It is",
                        "phase": "prefill",
                        "stepIndex": 0,
                        "sourceReportPath": "bench/out/source.json",
                        "leftTokenText": " not",
                        "rightTokenText": " safe",
                        "pairGap": 0.04,
                        "outsiderLead": 0.0,
                        "pairLeadFromTop": 0.0,
                        "usefulnessScore": 0.91,
                    }
                ]
            },
        }
        mutation_hunt_report = {
            "scenarioId": FIXTURE["scenarioId"],
            "summary": {
                "allCandidates": [
                    {
                        "promptId": "seatbelt-safe-unsafe--not__safe--one-word-choice",
                        "promptText": "Driving without a seatbelt is safe or unsafe. It is Answer with exactly one word: not or safe.",
                        "promptIndex": 0,
                        "phase": "prefill",
                        "stepIndex": 0,
                        "stepLabel": "prefill",
                        "repeatCount": 1,
                        "greedyTokenFlipObserved": False,
                        "byteDriftObserved": False,
                        "artifacts": [
                            {
                                "repeatIndex": 0,
                                "logitsArtifactPath": "bench/out/mutated.bin",
                                "logitsSha256": "abc123",
                                "topCandidates": [
                                    {"token": 711, "logit": 24.41, "tokenText": " not"},
                                    {"token": 6338, "logit": 24.40, "tokenText": " safe"},
                                ],
                            }
                        ],
                    }
                ]
            },
        }

        import bench.runners.run_semantic_pair_mutation_search as module

        original_build_mutation_hunt_report = module.build_mutation_hunt_report
        original_load_json = module.load_json
        try:
            module.build_mutation_hunt_report = lambda *args, **kwargs: (
                mutation_hunt_report,
                Path("/tmp/mutation.real-logit-hunt.json"),
            )
            module.load_json = lambda path: {
                "answerSetRegistryPath": "config/determinism-answer-set-registry.json",
                "registryModelId": "gemma-3-270m-it-q4k-ehf16-af32",
                "allowedAnswerSetIds": ["safety.not_safe"],
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
                    "maxPairLeadToMine": 0.35,
                    "maxOutsiderLeadToMine": 0.35,
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
                }
            }
            report, promoted_mined_report, _ = build_report(
                FIXTURE,
                source_report=source_report,
                output_dir=Path("/tmp"),
                repeat_count=1,
                case_count=1,
            )
        finally:
            module.build_mutation_hunt_report = original_build_mutation_hunt_report
            module.load_json = original_load_json
        self.assertEqual(report["summary"]["improvedMutationCount"], 1)
        self.assertEqual(promoted_mined_report["summary"]["promotedCandidateCount"], 1)
        self.assertEqual(promoted_mined_report["cases"][0]["candidatePairId"], "not__safe")


if __name__ == "__main__":
    unittest.main()
