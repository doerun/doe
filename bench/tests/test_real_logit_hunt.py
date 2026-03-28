#!/usr/bin/env python3
"""Regression tests for the real-logit near-tie hunt runner."""

from __future__ import annotations

import unittest
from pathlib import Path

from bench.runners.run_real_logit_hunt import build_helper_config
from bench.runners.run_real_logit_hunt import build_step_label
from bench.runners.run_real_logit_hunt import build_summary
from bench.runners.run_real_logit_hunt import gather_candidate_groups
from bench.runners.run_real_logit_hunt import rank_candidates
from bench.runners.run_real_logit_hunt import summarize_candidate_group


class RealLogitHuntTests(unittest.TestCase):
    def test_build_step_label_prefill_and_decode(self) -> None:
        self.assertEqual(build_step_label({"phase": "prefill", "stepIndex": 0}), "prefill")
        self.assertEqual(build_step_label({"phase": "decode", "stepIndex": 2}), "decode[2]")

    def test_summarize_candidate_group_detects_flip_and_byte_drift(self) -> None:
        group_key = ("sky-gap", 0, "The sky is blue", "prefill", 0)
        entries = [
            {
                "repeatIndex": 0,
                "stepLabel": "prefill",
                "greedyToken": 563,
                "greedyLogit": 26.3,
                "top2Gap": 0.002,
                "exactMaxTieCount": 1,
                "logitsSha256": "aaa",
                "logitsArtifactPath": None,
                "topCandidates": [{"token": 563, "logit": 26.3}, {"token": 991, "logit": 26.298}],
                "inputToken": None,
            },
            {
                "repeatIndex": 1,
                "stepLabel": "prefill",
                "greedyToken": 991,
                "greedyLogit": 26.31,
                "top2Gap": 0.001,
                "exactMaxTieCount": 1,
                "logitsSha256": "bbb",
                "logitsArtifactPath": None,
                "topCandidates": [{"token": 991, "logit": 26.31}, {"token": 563, "logit": 26.309}],
                "inputToken": None,
            },
        ]
        summary = summarize_candidate_group(group_key, entries)
        self.assertEqual(summary["candidateTier"], "greedy_flip")
        self.assertTrue(summary["greedyTokenFlipObserved"])
        self.assertTrue(summary["byteDriftObserved"])
        self.assertEqual(summary["minTop2Gap"], 0.001)
        self.assertEqual(summary["greedyTokenValues"], [563, 991])

    def test_summarize_candidate_group_detects_exact_tie(self) -> None:
        group_key = ("tie", 1, "Name a color:", "decode", 1)
        entries = [
            {
                "repeatIndex": 0,
                "stepLabel": "decode[1]",
                "greedyToken": 17,
                "greedyLogit": 5.0,
                "top2Gap": 0.0,
                "exactMaxTieCount": 2,
                "logitsSha256": "same",
                "logitsArtifactPath": "bench/out/logits.bin",
                "topCandidates": [{"token": 17, "logit": 5.0}, {"token": 42, "logit": 5.0}],
                "inputToken": 101,
            },
            {
                "repeatIndex": 1,
                "stepLabel": "decode[1]",
                "greedyToken": 17,
                "greedyLogit": 5.0,
                "top2Gap": 0.0,
                "exactMaxTieCount": 2,
                "logitsSha256": "same",
                "logitsArtifactPath": "bench/out/logits.bin",
                "topCandidates": [{"token": 17, "logit": 5.0}, {"token": 42, "logit": 5.0}],
                "inputToken": 101,
            },
        ]
        summary = summarize_candidate_group(group_key, entries)
        self.assertEqual(summary["candidateTier"], "exact_max_tie")
        self.assertTrue(summary["exactMaxTieObserved"])
        self.assertFalse(summary["greedyTokenFlipObserved"])
        self.assertFalse(summary["byteDriftObserved"])

    def test_rank_candidates_prefers_flip_then_exact_tie_then_near_tie(self) -> None:
        ranked = rank_candidates(
            [
                {"candidateTier": "near_tie", "greedyTokenFlipObserved": False, "exactMaxTieObserved": False, "byteDriftObserved": False, "minTop2Gap": 0.0005, "promptIndex": 2, "stepIndex": 0},
                {"candidateTier": "exact_max_tie", "greedyTokenFlipObserved": False, "exactMaxTieObserved": True, "byteDriftObserved": False, "minTop2Gap": 0.0, "promptIndex": 1, "stepIndex": 1},
                {"candidateTier": "greedy_flip", "greedyTokenFlipObserved": True, "exactMaxTieObserved": False, "byteDriftObserved": True, "minTop2Gap": 0.01, "promptIndex": 0, "stepIndex": 0},
            ]
        )
        self.assertEqual(ranked[0]["candidateTier"], "greedy_flip")
        self.assertEqual(ranked[1]["candidateTier"], "exact_max_tie")
        self.assertEqual(ranked[2]["candidateTier"], "near_tie")

    def test_build_summary_groups_by_prompt_and_step(self) -> None:
        harvest = {
            "runs": [
                {
                    "repeatIndex": 0,
                    "promptResults": [
                        {
                            "status": "ok",
                            "id": "sky-gap",
                            "promptIndex": 0,
                            "text": "The sky is blue",
                            "steps": [
                                {
                                    "phase": "prefill",
                                    "stepIndex": 0,
                                    "greedyToken": 563,
                                    "greedyLogit": 26.3,
                                    "top2Gap": 0.002,
                                    "exactMaxTieCount": 1,
                                    "logitsSha256": "aaa",
                                    "topCandidates": [],
                                }
                            ],
                        }
                    ],
                },
                {
                    "repeatIndex": 1,
                    "promptResults": [
                        {
                            "status": "ok",
                            "id": "sky-gap",
                            "promptIndex": 0,
                            "text": "The sky is blue",
                            "steps": [
                                {
                                    "phase": "prefill",
                                    "stepIndex": 0,
                                    "greedyToken": 563,
                                    "greedyLogit": 26.3,
                                    "top2Gap": 0.001,
                                    "exactMaxTieCount": 1,
                                    "logitsSha256": "aaa",
                                    "topCandidates": [],
                                }
                            ],
                        }
                    ],
                },
            ]
        }
        groups = gather_candidate_groups(harvest)
        self.assertEqual(len(groups), 1)
        summary = build_summary(harvest, top_candidates=5)
        self.assertEqual(summary["promptCount"], 1)
        self.assertEqual(summary["stepCandidateCount"], 1)
        self.assertEqual(summary["topCandidates"][0]["candidateTier"], "near_tie")

    def test_build_helper_config_preserves_browser_repeat_isolation(self) -> None:
        fixture = {
            "scenarioId": "apple_metal_real_logit_hunt_gemma270m",
            "dopplerRepoPath": "../doppler",
            "modelArtifactPath": "../doppler/tmp/gemma3-bench-artifacts/gemma-3-270m-it-q4k-ehf16-af32",
            "modelId": "gemma-3-270m-it-q4k-ehf16-af32",
            "promptCandidates": [{"id": "sky-blue", "text": "The sky is blue"}],
            "defaultRepeatCount": 2,
            "decodeSteps": 1,
            "topK": 5,
            "useChatTemplate": False,
            "runtimeConfig": {"inference": {"chatTemplate": {"enabled": False}}},
            "browser": {
                "headless": True,
                "channel": "chromium",
                "timeoutMs": 240000,
                "repeatIsolation": "new-page",
            },
        }
        config = build_helper_config(
            fixture,
            output_dir=Path("/tmp/doe-real-logit-hunt"),
            repeat_count=4,
            persist_logits=False,
        )
        self.assertEqual(config["repeatCount"], 4)
        self.assertEqual(config["browser"]["repeatIsolation"], "new-page")


if __name__ == "__main__":
    unittest.main()
