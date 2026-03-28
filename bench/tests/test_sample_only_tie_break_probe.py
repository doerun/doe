#!/usr/bin/env python3
"""Regression tests for the sample-only tie-break probe runner."""

from __future__ import annotations

import copy
import unittest

from bench.runners.run_sample_only_tie_break_probe import apply_mutation
from bench.runners.run_sample_only_tie_break_probe import as_f32
from bench.runners.run_sample_only_tie_break_probe import build_sample_only_commands
from bench.runners.run_sample_only_tie_break_probe import build_summary
from bench.runners.run_sample_only_tie_break_probe import case_claim_summary
from bench.runners.run_sample_only_tie_break_probe import ensure_fixture_shape
from bench.runners.run_sample_only_tie_break_probe import expected_greedy_from_logits
from bench.runners.run_sample_only_tie_break_probe import nextafter_f32
from bench.runners.run_sample_only_tie_break_probe import resolve_choice_candidates
from bench.runners.run_sample_only_tie_break_probe import select_source_cases


VALID_FIXTURE = {
    "scenarioId": "apple_metal_sample_only_tie_break_gemma270m",
    "kernelRoot": "bench/kernels",
    "profile": "apple-metal",
    "backendLanes": [{"id": "doe", "backendLane": "native:apple-metal:doe"}],
    "doeStableToken": {"mode": "host-bytes", "topCandidates": 5},
    "doeStableChoice": {
        "mode": "host-bytes",
        "topCandidates": 5,
        "policyId": "bench/not-safe-first",
        "triggerPolicyId": "candidate-margin-band-v1",
        "candidateSetId": "safety.not_safe",
        "candidateSetSource": "source-report-resolved",
        "candidates": [
            {"token": 711, "label": "not"},
            {"token": 6338, "label": "safe"},
        ],
        "ambiguityTriggerPolicyId": "candidate-margin-band-v1",
    },
    "doeReviewedChoice": {
        "mode": "host-bytes",
        "topCandidates": 5,
        "reviewPolicyId": "bench/reviewer-v1",
        "triggerPolicyId": "candidate-margin-band-v1",
        "candidateSetId": "safety.not_safe",
        "candidateSetSource": "source-report-resolved",
        "candidates": [
            {"token": 711, "label": "not"},
            {"token": 6338, "label": "safe"},
        ],
        "ambiguityTriggerPolicyId": "candidate-margin-band-v1",
        "decision": {
            "token": 6338,
            "label": "safe",
            "reviewerId": "bench/reviewer-v1",
            "decisionId": "review-001",
        },
    },
    "mutations": [{"id": "as-captured", "kind": "identity"}],
    "defaultRunCount": 2,
    "defaultCaseCount": 1,
}


class SampleOnlyTieBreakProbeTests(unittest.TestCase):
    def test_build_sample_only_commands_uses_vocab_size_and_buffer_bytes(self) -> None:
        commands = build_sample_only_commands([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(commands[0]["data"][0], 4)
        self.assertEqual(commands[1]["bufferSize"], 16)
        self.assertEqual(len(commands[1]["data"]), 4)
        self.assertEqual(commands[2]["kernel"], "sample.wgsl")
        self.assertEqual(commands[2]["bindings"][1]["buffer_size"], 16)

    def test_top2_exact_tie_changes_expected_token_to_lowest_index(self) -> None:
        logits = [0.0, 5.0, 7.0, -1.0]
        mutated, details = apply_mutation(logits, {"id": "tie", "kind": "top2_exact_tie"}, top_k=4)
        self.assertEqual(details["top1Token"], 2)
        self.assertEqual(details["top2Token"], 1)
        expected = expected_greedy_from_logits(mutated, top_k=4)
        self.assertEqual(expected["exactMaxTieCount"], 2)
        self.assertEqual(expected["expectedGreedyToken"], 1)

    def test_top2_second_candidate_wins_by_ulp_swaps_expected_winner(self) -> None:
        logits = [0.0, 5.0, 7.0, -1.0]
        mutated, _ = apply_mutation(
            logits,
            {"id": "swap", "kind": "top2_second_candidate_wins_by_ulp"},
            top_k=4,
        )
        expected = expected_greedy_from_logits(mutated, top_k=4)
        self.assertEqual(expected["expectedGreedyToken"], 1)
        self.assertEqual(expected["exactMaxTieCount"], 1)
        self.assertGreater(mutated[1], mutated[2])

    def test_topk_exact_tie_ties_requested_prefix(self) -> None:
        logits = [0.0, 5.0, 7.0, 6.0, 4.0]
        mutated, _ = apply_mutation(
            logits,
            {"id": "tie4", "kind": "topk_exact_tie", "topK": 4},
            top_k=5,
        )
        expected = expected_greedy_from_logits(mutated, top_k=5)
        self.assertEqual(expected["exactMaxTieCount"], 4)
        self.assertEqual(expected["expectedGreedyToken"], 1)

    def test_explicit_token_texts_exact_tie_uses_named_source_tokens(self) -> None:
        logits = [0.0, 5.0, 7.0, 6.0, 4.0]
        case_entry = {
            "promptId": "brakes-safe-unsafe",
            "stepLabel": "prefill",
            "artifacts": [
                {
                    "topCandidates": [
                        {"token": 2, "tokenText": " now"},
                        {"token": 3, "tokenText": " not"},
                        {"token": 4, "tokenText": " safe"},
                    ]
                }
            ],
        }
        mutated, details = apply_mutation(
            logits,
            {"id": "semantic-tie", "kind": "explicit_tokens_exact_tie", "tokenTexts": [" not", " safe"]},
            top_k=5,
            case_entry=case_entry,
        )
        expected = expected_greedy_from_logits(mutated, top_k=5)
        self.assertEqual(details["tiedTokens"], [3, 4])
        self.assertEqual(details["tiedTokenTexts"], [" not", " safe"])
        self.assertEqual(expected["exactMaxTieCount"], 2)
        self.assertEqual(expected["expectedGreedyToken"], 3)

    def test_select_source_cases_supports_prompt_filters(self) -> None:
        report = {
            "summary": {
                "allCandidates": [
                    {
                        "promptId": "a",
                        "phase": "prefill",
                        "stepIndex": 0,
                        "artifacts": [{"logitsArtifactPath": "bench/out/a.bin"}],
                    },
                    {
                        "promptId": "b",
                        "phase": "decode",
                        "stepIndex": 1,
                        "artifacts": [{"logitsArtifactPath": "bench/out/b.bin"}],
                    },
                ]
            }
        }
        selected = select_source_cases(
            report,
            case_count=1,
            case_filters=[{"promptId": "b", "phase": "decode", "stepIndex": 1}],
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["promptId"], "b")

    def test_resolve_choice_candidates_supports_token_text_lookup(self) -> None:
        case_entry = {
            "promptId": "seatbelt-safe-unsafe",
            "stepLabel": "prefill",
            "artifacts": [
                {
                    "topCandidates": [
                        {"token": 1492, "tokenText": " now"},
                        {"token": 711, "tokenText": " not"},
                        {"token": 6338, "tokenText": " safe"},
                    ]
                }
            ],
        }
        resolved = resolve_choice_candidates(
            {
                "candidates": [
                    {"tokenText": " not", "label": "not"},
                    {"tokenText": " safe", "label": "safe"},
                ]
            },
            case_entry,
        )
        self.assertEqual(resolved, [{"token": 711, "label": "not"}, {"token": 6338, "label": "safe"}])

    def test_ensure_fixture_shape_requires_stable_choice_provenance_fields(self) -> None:
        for field in ("triggerPolicyId", "candidateSetId", "candidateSetSource"):
            with self.subTest(field=field):
                fixture = copy.deepcopy(VALID_FIXTURE)
                del fixture["doeStableChoice"][field]
                with self.assertRaisesRegex(ValueError, f"fixture.doeStableChoice missing required field: {field}"):
                    ensure_fixture_shape(fixture)

    def test_ensure_fixture_shape_rejects_mismatched_stable_choice_policy_ids(self) -> None:
        fixture = copy.deepcopy(VALID_FIXTURE)
        fixture["doeStableChoice"]["ambiguityTriggerPolicyId"] = "exact-max-tie-v1"
        with self.assertRaisesRegex(
            ValueError,
            "fixture.doeStableChoice.triggerPolicyId must match fixture.doeStableChoice.ambiguityTriggerPolicyId",
        ):
            ensure_fixture_shape(fixture)

    def test_ensure_fixture_shape_requires_reviewed_choice_decision(self) -> None:
        fixture = copy.deepcopy(VALID_FIXTURE)
        del fixture["doeReviewedChoice"]["decision"]
        with self.assertRaisesRegex(
            ValueError,
            "fixture.doeReviewedChoice missing required field: decision",
        ):
            ensure_fixture_shape(fixture)

    def test_ensure_fixture_shape_rejects_mismatched_reviewed_choice_policy_ids(self) -> None:
        fixture = copy.deepcopy(VALID_FIXTURE)
        fixture["doeReviewedChoice"]["ambiguityTriggerPolicyId"] = "exact-max-tie-v1"
        with self.assertRaisesRegex(
            ValueError,
            "fixture.doeReviewedChoice.triggerPolicyId must match fixture.doeReviewedChoice.ambiguityTriggerPolicyId",
        ):
            ensure_fixture_shape(fixture)

    def test_nextafter_f32_moves_one_f32_step(self) -> None:
        base = as_f32(7.0)
        stepped = nextafter_f32(base, float("inf"))
        self.assertGreater(stepped, base)
        self.assertEqual(as_f32(stepped), stepped)

    def test_case_claim_summary_marks_stable_token_differentiator(self) -> None:
        claim = case_claim_summary(
            lane_summaries={
                "doe": {"stableAcrossRuns": True},
                "dawn": {"stableAcrossRuns": True},
            },
            cross_lane={
                "operators": {
                    "sample.output_token": {
                        "sameAcrossLanes": True,
                        "sameDecodedValueAcrossLanes": True,
                    }
                }
            },
            tie_break_audit={
                "lanes": {
                    "doe": {
                        "actualSampledToken": 808,
                        "matchesExpectedGreedyToken": False,
                    }
                },
                "crossLane": {
                    "sample.output_token": {
                        "allLanesMatchExpectedGreedyToken": False,
                    }
                },
            },
            stable_token={
                "token": 107,
                "matchesExpectedGreedyToken": True,
            },
            stable_choice=None,
            reviewed_choice=None,
        )
        self.assertTrue(claim["doeStableTokenDifferentiator"])
        self.assertTrue(claim["doeStableTokenDiffersFromDoeRawToken"])
        self.assertFalse(claim["doeStableChoiceConfigured"])

    def test_case_claim_summary_marks_stable_choice_differentiator(self) -> None:
        claim = case_claim_summary(
            lane_summaries={
                "doe": {"stableAcrossRuns": True},
                "dawn": {"stableAcrossRuns": True},
            },
            cross_lane={
                "operators": {
                    "sample.output_token": {
                        "sameAcrossLanes": True,
                        "sameDecodedValueAcrossLanes": True,
                    }
                }
            },
            tie_break_audit={
                "lanes": {
                    "doe": {
                        "actualSampledToken": 1492,
                        "matchesExpectedGreedyToken": True,
                    }
                },
                "crossLane": {
                    "sample.output_token": {
                        "allLanesMatchExpectedGreedyToken": True,
                    }
                },
            },
            stable_token={
                "token": 1492,
                "matchesExpectedGreedyToken": True,
            },
            stable_choice={
                "token": 711,
                "receipt": {
                    "ambiguityTriggered": True,
                    "selectedBy": "stable-choice-policy",
                },
            },
            reviewed_choice=None,
        )
        self.assertTrue(claim["doeStableChoiceConfigured"])
        self.assertTrue(claim["doeStableChoiceTriggered"])
        self.assertTrue(claim["doeStableChoiceDiffersFromDoeRawToken"])
        self.assertTrue(claim["doeStableChoiceDiffersFromDoeStableToken"])
        self.assertTrue(claim["doeStableChoiceDifferentiator"])

    def test_case_claim_summary_marks_reviewed_choice_differentiator(self) -> None:
        claim = case_claim_summary(
            lane_summaries={
                "doe": {"stableAcrossRuns": True},
                "dawn": {"stableAcrossRuns": True},
            },
            cross_lane={
                "operators": {
                    "sample.output_token": {
                        "sameAcrossLanes": True,
                        "sameDecodedValueAcrossLanes": True,
                    }
                }
            },
            tie_break_audit={
                "lanes": {
                    "doe": {
                        "actualSampledToken": 1492,
                        "matchesExpectedGreedyToken": True,
                    }
                },
                "crossLane": {
                    "sample.output_token": {
                        "allLanesMatchExpectedGreedyToken": True,
                    }
                },
            },
            stable_token={
                "token": 1492,
                "matchesExpectedGreedyToken": True,
            },
            stable_choice={
                "token": 711,
                "receipt": {
                    "ambiguityTriggered": True,
                    "selectedBy": "stable-choice-policy",
                },
            },
            reviewed_choice={
                "token": 6338,
                "receipt": {
                    "ambiguityTriggered": True,
                    "selectedBy": "reviewed-choice-decision",
                    "decisionAccepted": True,
                },
            },
        )
        self.assertTrue(claim["doeReviewedChoiceConfigured"])
        self.assertTrue(claim["doeReviewedChoiceTriggered"])
        self.assertTrue(claim["doeReviewedChoiceDecisionAccepted"])
        self.assertTrue(claim["doeReviewedChoiceDiffersFromDoeRawToken"])
        self.assertTrue(claim["doeReviewedChoiceDiffersFromDoeStableToken"])
        self.assertTrue(claim["doeReviewedChoiceDiffersFromDoeStableChoice"])
        self.assertTrue(claim["doeReviewedChoiceDifferentiator"])

    def test_build_summary_counts_stable_token_differentiators(self) -> None:
        summary = build_summary(
            [
                {
                    "caseId": "a",
                    "mutationId": "force-top4-exact-tie",
                    "claim": {
                        "sameDecodedValueAcrossLanes": True,
                        "allLanesMatchExpectedGreedyToken": False,
                        "doeStableTokenDifferentiator": True,
                        "doeStableChoiceDifferentiator": False,
                        "doeReviewedChoiceDifferentiator": False,
                    },
                },
                {
                    "caseId": "b",
                    "mutationId": "as-captured",
                    "claim": {
                        "sameDecodedValueAcrossLanes": True,
                        "allLanesMatchExpectedGreedyToken": True,
                        "doeStableTokenDifferentiator": False,
                        "doeStableChoiceDifferentiator": True,
                        "doeReviewedChoiceDifferentiator": True,
                    },
                },
            ]
        )
        self.assertEqual(summary["stableTokenDifferentiatorCaseCount"], 1)
        self.assertEqual(summary["stableChoiceDifferentiatorCaseCount"], 1)
        self.assertEqual(summary["reviewedChoiceDifferentiatorCaseCount"], 1)


if __name__ == "__main__":
    unittest.main()
