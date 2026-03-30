import tempfile
import unittest
from pathlib import Path

from bench.lib.config_validation import load_validated_config
from bench.runners.search_sampled_decode_prompts import build_next_round_prompt_candidates
from bench.runners.search_sampled_decode_prompts import dedupe_prompt_candidates
from bench.runners.search_sampled_decode_prompts import initial_prompt_candidates
from bench.runners.search_sampled_decode_prompts import run_search


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO_ROOT / "config" / "numeric-stability-decode-prompt-search-plan.json"


SOURCE_FIXTURE = {
    "scenarioId": "apple_metal_real_logit_hunt_gemma270m_policy_breadth",
    "dopplerRepoPath": "../doppler",
    "modelArtifactPath": "../doppler/tmp/model",
    "modelId": "gemma-3-270m-it-q4k-ehf16-af32",
    "defaultRepeatCount": 2,
    "decodeSteps": 1,
    "topK": 32,
    "useChatTemplate": False,
    "runtimeConfig": {"inference": {"chatTemplate": {"enabled": False}}},
    "browser": {"repeatIsolation": "new-page"},
    "promptCandidates": [
        {
            "id": "allow-block",
            "text": "Answer with exactly one word: allow or block. Question: A phishing email should be Answer:",
        },
        {
            "id": "approve-deny",
            "text": "Answer with exactly one word: approve or deny. Question: A hotfix should be Answer:",
        },
    ],
}

PAIR_FIXTURE = {
    "scenarioId": "apple_metal_pair_agnostic_mine_gemma270m",
    "registryModelId": "gemma-3-270m-it-q4k-ehf16-af32",
    "triggerPolicyId": "candidate-margin-band-v1",
    "defaultPerPromptLimit": 2,
    "defaultGlobalLimit": 8,
    "miningPolicy": {
        "topCandidateLimit": 8,
        "requireWordLike": True,
        "requireSingleTokenAnswers": True,
        "minNormalizedTokenLength": 2,
        "excludedNormalizedTokens": ["the"],
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
    },
}

PLAN = {
    "schemaVersion": 1,
    "planVersion": "test-v1",
    "sourceFixturePath": "unused-source.json",
    "pairMiningFixturePath": "unused-pair.json",
    "rounds": 2,
    "beamWidth": 2,
    "maxPromptCandidatesPerRound": 4,
    "perPromptLimit": 2,
    "globalLimit": 4,
    "topCandidatesToKeep": 4,
    "persistLogits": False,
    "repeatCount": 2,
    "minimumUsefulnessScore": 0.5,
    "mutationTemplates": [
        {"id": "question-answer", "kind": "structured-choice", "style": "question-answer"},
        {"id": "answer-question-reversed", "kind": "structured-choice", "style": "answer-question", "reverseOptions": True},
        {"id": "swap-inline-choice", "kind": "swap-inline-choice"},
    ],
}


class SearchSampledDecodePromptsTests(unittest.TestCase):
    def test_checked_in_plan_validates_and_keeps_semantic_seed_families(self) -> None:
        plan = load_validated_config(
            PLAN_PATH,
            REPO_ROOT / "config" / "numeric-stability-decode-prompt-search-plan.schema.json",
        )
        self.assertEqual(plan["planVersion"], "2026-03-30-sampled-decode-prompt-search-v4")
        self.assertGreaterEqual(plan["rounds"], 2)
        self.assertEqual(
            plan["sourceFixturePath"],
            "bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.prompt-search-sharp.json",
        )
        self.assertEqual(
            plan["pairMiningFixturePath"],
            "bench/fixtures/determinism/apple-metal-pair-agnostic-mine.gemma270m.search-loose.json",
        )
        self.assertTrue(any(template["kind"] == "structured-choice" for template in plan["mutationTemplates"]))
        source_fixture = __import__("json").loads(
            (REPO_ROOT / plan["sourceFixturePath"]).read_text(encoding="utf-8")
        )
        prompt_ids = {candidate["id"] for candidate in source_fixture["promptCandidates"]}
        self.assertIn("free-will-yes-no-unknown", prompt_ids)
        self.assertIn("justice-revenge-both", prompt_ids)

    def test_dedupe_prompt_candidates_skips_normalized_duplicates(self) -> None:
        deduped = dedupe_prompt_candidates(
            [
                {"id": "allow-block", "text": "Allow or block: a phishing email should be"},
                {"id": "allow-block-dup", "text": "Allow  or  block: a phishing email should be"},
            ],
            seen_prompt_texts=set(),
            limit=8,
        )
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["id"], "allow-block")

    def test_initial_prompt_candidates_prefers_plan_candidates(self) -> None:
        prompts = initial_prompt_candidates(PLAN, SOURCE_FIXTURE)
        self.assertEqual(len(prompts), 2)
        self.assertTrue(prompts[0]["text"].startswith("Answer with exactly one word:"))

    def test_build_next_round_prompt_candidates_uses_structured_templates(self) -> None:
        source_cases = [
            {
                "candidatePairId": "allow__block",
                "promptId": "allow-block",
                "promptText": "Answer with exactly one word: allow or block. Question: A phishing email should be Answer:",
                "leftTokenText": " allow",
                "rightTokenText": " block",
            }
        ]
        prompts = build_next_round_prompt_candidates(
            source_cases,
            mutation_templates=PLAN["mutationTemplates"],
            seen_prompt_texts={},
            limit=8,
        )
        self.assertGreaterEqual(len(prompts), 1)
        self.assertTrue(any(prompt["text"].startswith("Question:") for prompt in prompts))
        self.assertTrue(any("block or allow" in prompt["text"] for prompt in prompts))

    def test_build_next_round_prompt_candidates_preserves_three_way_choices(self) -> None:
        source_cases = [
            {
                "candidatePairId": "justice__revenge",
                "promptId": "justice-revenge-both",
                "promptText": "Justice, revenge, or both: wanting a murderer imprisoned for life is",
                "leftTokenText": " justice",
                "rightTokenText": " revenge",
                "usefulnessScore": 0.9,
            }
        ]
        prompts = build_next_round_prompt_candidates(
            source_cases,
            mutation_templates=[
                {"id": "answer-question", "kind": "structured-choice", "style": "answer-question"},
                {"id": "inline-colon-reversed", "kind": "structured-choice", "style": "inline-colon", "reverseOptions": True},
            ],
            seen_prompt_texts=set(),
            limit=8,
        )
        self.assertTrue(
            any(
                prompt["text"] == "Answer with exactly one word: Justice, revenge, or both. Question: wanting a murderer imprisoned for life is Answer:"
                for prompt in prompts
            )
        )
        self.assertTrue(
            any(
                prompt["text"] == "both, revenge, or Justice: wanting a murderer imprisoned for life is"
                for prompt in prompts
            )
        )

    def test_run_search_executes_rounds_with_fake_oracles(self) -> None:
        harvest_calls = []

        def fake_run_helper(config, *, work_dir):
            harvest_calls.append([candidate["id"] for candidate in config["promptCandidates"]])
            return {
                "runs": [
                    {
                        "repeatIndex": 0,
                        "promptResults": [],
                    }
                ]
            }

        def fake_pair_report_builder(_fixture, *, source_report_paths, per_prompt_limit, global_limit):
            round_id = Path(source_report_paths[0]).parent.name
            if round_id == "round-01":
                cases = [
                    {
                        "candidatePairId": "allow__block",
                        "promptId": "allow-block",
                        "promptText": "Allow or block: a phishing email should be",
                        "leftTokenText": " allow",
                        "rightTokenText": " block",
                        "usefulnessScore": 0.9,
                    }
                ]
            else:
                cases = []
            return {"cases": cases, "summary": {"promotedCandidateCount": len(cases)}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            source_fixture_path = tmp_root / "source.json"
            pair_fixture_path = tmp_root / "pair.json"
            source_fixture_path.write_text(__import__("json").dumps(SOURCE_FIXTURE), encoding="utf-8")
            pair_fixture_path.write_text(__import__("json").dumps(PAIR_FIXTURE), encoding="utf-8")
            plan = dict(PLAN)
            plan["sourceFixturePath"] = str(source_fixture_path)
            plan["pairMiningFixturePath"] = str(pair_fixture_path)
            report = run_search(
                plan,
                plan_path=tmp_root / "plan.json",
                output_dir=tmp_root / "out",
                timestamp="20260330T010000Z",
                run_helper_fn=fake_run_helper,
                pair_report_builder=fake_pair_report_builder,
            )
        self.assertEqual(report["summary"]["executedRoundCount"], 2)
        self.assertEqual(len(harvest_calls), 2)
        self.assertEqual(report["summary"]["bestCases"][0]["candidatePairId"], "allow__block")


if __name__ == "__main__":
    unittest.main()
