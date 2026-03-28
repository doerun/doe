#!/usr/bin/env python3
"""Mine replayable semantic token-pair candidates from real-logit scout reports."""

from __future__ import annotations

import argparse
import collections
import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.runners.determinism_search_helpers import canonical_candidate_order
from bench.runners.determinism_search_helpers import canonical_pair_id
from bench.runners.determinism_search_helpers import build_stage_stability_requirements
from bench.runners.determinism_search_helpers import compute_outsider_lead
from bench.runners.determinism_search_helpers import compute_usefulness_score
from bench.runners.determinism_search_helpers import DEFAULT_ANSWER_SET_REGISTRY_PATH
from bench.runners.determinism_search_helpers import DEFAULT_TRIGGER_POLICY_PATH
from bench.runners.determinism_search_helpers import evaluate_trigger_policy
from bench.runners.determinism_search_helpers import find_answer_option_entry
from bench.runners.determinism_search_helpers import is_single_token_answer_text
from bench.runners.determinism_search_helpers import load_answer_set_model_registry
from bench.runners.determinism_search_helpers import load_json
from bench.runners.determinism_search_helpers import load_trigger_policy
from bench.runners.determinism_search_helpers import looks_like_bounded_answer_prompt
from bench.runners.determinism_search_helpers import normalize_answer_token_text
from bench.runners.determinism_search_helpers import pair_case_sort_key
from bench.runners.determinism_search_helpers import prompt_contains_normalized_token
from bench.runners.determinism_search_helpers import relative_or_absolute
from bench.runners.determinism_search_helpers import resolve_repo_path
from bench.runners.determinism_search_helpers import timestamp_label

DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "determinism" / "apple-metal-pair-agnostic-mine.gemma270m.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "apple-metal-pair-agnostic-mine"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Pair-agnostic mining fixture JSON.")
    parser.add_argument(
        "--source-report",
        action="append",
        required=True,
        help="Real-logit hunt report to mine. Pass multiple times to aggregate scouts.",
    )
    parser.add_argument("--per-prompt-limit", type=int, default=None, help="Override per-prompt case limit from the fixture.")
    parser.add_argument("--global-limit", type=int, default=None, help="Override global case limit from the fixture.")
    parser.add_argument("--timestamp", default=None, help="UTC timestamp label (default: current UTC time).")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for mined-pair artifacts.")
    return parser.parse_args()


def ensure_fixture_shape(fixture: dict[str, Any]) -> None:
    required = (
        "scenarioId",
        "defaultPerPromptLimit",
        "defaultGlobalLimit",
        "miningPolicy",
        "registryModelId",
        "triggerPolicyId",
    )
    missing = [field for field in required if field not in fixture]
    if missing:
        raise ValueError(f"fixture missing required fields: {', '.join(missing)}")
    answer_set_registry_path = resolve_repo_path(
        str(fixture.get("answerSetRegistryPath") or DEFAULT_ANSWER_SET_REGISTRY_PATH)
    )
    trigger_policy_path = resolve_repo_path(
        str(fixture.get("triggerPolicyPath") or DEFAULT_TRIGGER_POLICY_PATH)
    )
    load_answer_set_model_registry(answer_set_registry_path, str(fixture["registryModelId"]))
    load_trigger_policy(trigger_policy_path, str(fixture["triggerPolicyId"]))
    policy = fixture["miningPolicy"]
    required_policy = (
        "topCandidateLimit",
        "requireWordLike",
        "requireSingleTokenAnswers",
        "minNormalizedTokenLength",
        "excludedNormalizedTokens",
        "requiredPromptSubstrings",
        "requireBoundedAnswerPrompt",
        "minPromptAnchorCount",
        "allowSingleAnchorTokens",
        "maxPairGapToMine",
        "maxPairLeadToMine",
        "maxOutsiderLeadToMine",
        "maxPairGapForScore",
        "maxPairLeadForScore",
        "maxOutsiderLeadForScore",
        "pairGapWeight",
        "pairLeadWeight",
        "outsiderLeadWeight",
        "promptAnchorWeight",
        "boundedAnswerPromptWeight",
        "sourceByteStableWeight",
        "sourceGreedyStableWeight",
    )
    missing_policy = [field for field in required_policy if field not in policy]
    if missing_policy:
        raise ValueError(f"fixture.miningPolicy missing required fields: {', '.join(missing_policy)}")


def choose_reference_artifact(candidate: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = candidate.get("artifacts") or []
    if not artifacts:
        return None
    dominant_digest = candidate.get("dominantLogitsDigest")
    if dominant_digest:
        for artifact in artifacts:
            if artifact.get("logitsSha256") == dominant_digest:
                return artifact
    return artifacts[0]


def dedupe_entries_by_normalized_text(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        normalized = entry["normalizedTokenText"]
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(entry)
    return deduped


def filter_candidate_entries(
    top_candidates: list[dict[str, Any]],
    *,
    prompt_text: str,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    excluded = {str(token).strip().lower() for token in policy["excludedNormalizedTokens"]}
    require_word_like = bool(policy["requireWordLike"])
    require_single_token = bool(policy["requireSingleTokenAnswers"])
    min_length = int(policy["minNormalizedTokenLength"])
    filtered: list[dict[str, Any]] = []
    for index, entry in enumerate(top_candidates[: int(policy["topCandidateLimit"])], start=1):
        token_text = entry.get("tokenText")
        if not isinstance(token_text, str) or not token_text.strip():
            continue
        normalized = normalize_answer_token_text(token_text)
        if normalized in excluded:
            continue
        if require_single_token and not is_single_token_answer_text(
            token_text,
            min_normalized_length=min_length,
            require_word_like=require_word_like,
        ):
            continue
        filtered.append(
            {
                "token": int(entry["token"]),
                "logit": float(entry["logit"]),
                "tokenText": token_text,
                "normalizedTokenText": normalized,
                "rank": index,
                "promptAnchored": prompt_contains_normalized_token(prompt_text, normalized),
            }
        )
    return dedupe_entries_by_normalized_text(filtered)


def allowed_answer_sets(
    fixture: dict[str, Any],
    *,
    registry_model: dict[str, Any],
) -> list[dict[str, Any]]:
    allowed_ids = set(str(answer_set_id) for answer_set_id in (fixture.get("allowedAnswerSetIds") or []))
    answer_sets = registry_model.get("answerSets") or []
    if not allowed_ids:
        return list(answer_sets)
    return [answer_set for answer_set in answer_sets if answer_set.get("id") in allowed_ids]


def match_answer_set_entries(
    answer_set: dict[str, Any],
    *,
    candidate_entries: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    matches: list[dict[str, Any]] = []
    for option in answer_set["options"]:
        entry = find_answer_option_entry(option, candidate_entries)
        if entry is None:
            return None
        matches.append(
            {
                **entry,
                "answerOptionId": option["id"],
                "answerOptionLabel": option["label"],
            }
        )
    return matches


def candidate_set_repeat_stability(
    candidate: dict[str, Any],
    *,
    matched_entries: list[dict[str, Any]],
) -> tuple[bool, float]:
    artifacts = candidate.get("artifacts") or []
    if not artifacts:
        return False, 0.0
    normalized_pairs = {entry["normalizedTokenText"] for entry in matched_entries}
    stable_hits = 0
    for artifact in artifacts:
        top_candidates = artifact.get("topCandidates") or []
        normalized_present = {
            normalize_answer_token_text(str(top_candidate.get("tokenText") or ""))
            for top_candidate in top_candidates
        }
        if normalized_pairs.issubset(normalized_present):
            stable_hits += 1
    presence_rate = stable_hits / len(artifacts)
    return stable_hits == len(artifacts), presence_rate


def promotion_bucket_for_case(
    *,
    discovery_mode: str,
    trigger_evaluation: dict[str, Any],
    answer_set: dict[str, Any],
    stage_stability: dict[str, Any],
) -> str:
    if discovery_mode != "natural-scout":
        return "mutation-assisted"
    if (
        trigger_evaluation["wouldTrigger"]
        and bool(answer_set.get("headlineEligible"))
        and stage_stability["scout"]["passed"]
        and stage_stability["promote"]["passed"]
    ):
        return "natural-headline"
    return "natural-supporting"


def build_pair_case(
    *,
    candidate: dict[str, Any],
    artifact: dict[str, Any],
    answer_set: dict[str, Any],
    matched_entries: list[dict[str, Any]],
    policy: dict[str, Any],
    registry_model: dict[str, Any],
    trigger_policy: dict[str, Any],
    source_report_path: Path,
    source_report_scenario_id: str | None,
) -> dict[str, Any] | None:
    left = matched_entries[0]
    right = matched_entries[1]
    pair_gap = abs(float(left["logit"]) - float(right["logit"]))
    pair_top_logit = max(float(left["logit"]), float(right["logit"]))
    top_entry = artifact["topCandidates"][0]
    pair_lead_from_top = float(top_entry["logit"]) - pair_top_logit
    outsider_lead = compute_outsider_lead(
        artifact["topCandidates"],
        pair_tokens={int(left["token"]), int(right["token"])},
        pair_top_logit=pair_top_logit,
    )
    if pair_gap > float(policy["maxPairGapToMine"]):
        return None
    if pair_lead_from_top > float(policy["maxPairLeadToMine"]):
        return None
    if outsider_lead > float(policy["maxOutsiderLeadToMine"]):
        return None
    prompt_anchor_count = int(left["promptAnchored"]) + int(right["promptAnchored"])
    if prompt_anchor_count < int(policy["minPromptAnchorCount"]):
        return None
    allow_single_anchor = {str(token).strip().lower() for token in policy["allowSingleAnchorTokens"]}
    if prompt_anchor_count == 1 and (
        left["normalizedTokenText"] not in allow_single_anchor
        and right["normalizedTokenText"] not in allow_single_anchor
    ):
        return None
    bounded_answer_prompt = looks_like_bounded_answer_prompt(
        candidate["promptText"],
        required_substrings=[str(fragment) for fragment in policy["requiredPromptSubstrings"]],
    )
    if bool(policy["requireBoundedAnswerPrompt"]) and not bounded_answer_prompt:
        return None
    answer_set_prompt_anchor_count = sum(
        1
        for anchor in answer_set.get("promptAnchors") or []
        if prompt_contains_normalized_token(candidate["promptText"], normalize_answer_token_text(str(anchor)))
    )
    if answer_set_prompt_anchor_count == 0:
        return None
    pair_id = canonical_pair_id(left["tokenText"], right["tokenText"])
    source_byte_stable = not bool(candidate.get("byteDriftObserved"))
    source_greedy_stable = not bool(candidate.get("greedyTokenFlipObserved"))
    candidate_set_stable, candidate_set_presence_rate = candidate_set_repeat_stability(
        candidate,
        matched_entries=matched_entries,
    )
    stage_stability = build_stage_stability_requirements(
        scout_prompt_tokenization_stable=bool(candidate.get("promptTokenizationStable", False)),
        scout_top_candidate_membership_stable=bool(candidate.get("topCandidateMembershipStable", False)),
        promote_candidate_set_stable=candidate_set_stable,
        promote_digest_stable=source_byte_stable,
    )
    trigger_evaluation = evaluate_trigger_policy(
        trigger_policy,
        [entry["logit"] for entry in matched_entries],
    )
    usefulness_score = compute_usefulness_score(
        pair_gap=pair_gap,
        pair_lead_from_top=pair_lead_from_top,
        outsider_lead=outsider_lead,
        prompt_anchor_count=prompt_anchor_count,
        bounded_answer_prompt=bounded_answer_prompt,
        source_byte_stable=source_byte_stable,
        source_greedy_stable=source_greedy_stable,
        policy=policy,
    )
    canonical_order = canonical_candidate_order(left, right)
    discovery_mode = "natural-scout"
    promotion_bucket = promotion_bucket_for_case(
        discovery_mode=discovery_mode,
        trigger_evaluation=trigger_evaluation,
        answer_set=answer_set,
        stage_stability=stage_stability,
    )
    return {
        "candidateSetSource": "mined-topk-v1",
        "candidateSetId": answer_set["id"],
        "candidateSetRegistryTokenizerId": registry_model["tokenizerId"],
        "answerSetId": answer_set["id"],
        "domainId": answer_set["domainId"],
        "answerOptionIds": [entry["answerOptionId"] for entry in matched_entries],
        "answerOptionLabels": [entry["answerOptionLabel"] for entry in matched_entries],
        "candidatePairId": pair_id,
        "candidateCanonicalOrder": "token-id-ascending",
        "canonicalCandidateSet": canonical_order,
        "discoveryMode": discovery_mode,
        "sourcePromptId": candidate["promptId"],
        "mutationDepth": 0,
        "mutationType": None,
        "promotionBucket": promotion_bucket,
        "sourceReportPath": relative_or_absolute(source_report_path),
        "sourceReportScenarioId": source_report_scenario_id,
        "sourceRepeatIndex": artifact.get("repeatIndex"),
        "promptId": candidate["promptId"],
        "promptText": candidate["promptText"],
        "promptIndex": candidate["promptIndex"],
        "phase": candidate["phase"],
        "stepIndex": int(candidate["stepIndex"]),
        "stepLabel": candidate["stepLabel"],
        "top2Gap": candidate.get("minTop2Gap"),
        "exactMaxTieObserved": bool(candidate.get("exactMaxTieObserved")),
        "topTokenText": top_entry.get("tokenText"),
        "topToken": int(top_entry["token"]),
        "topTokenLogit": float(top_entry["logit"]),
        "leftTokenText": left["tokenText"],
        "leftNormalizedTokenText": left["normalizedTokenText"],
        "leftToken": int(left["token"]),
        "leftLogit": float(left["logit"]),
        "leftRank": int(left["rank"]),
        "leftPromptAnchored": bool(left["promptAnchored"]),
        "rightTokenText": right["tokenText"],
        "rightNormalizedTokenText": right["normalizedTokenText"],
        "rightToken": int(right["token"]),
        "rightLogit": float(right["logit"]),
        "rightRank": int(right["rank"]),
        "rightPromptAnchored": bool(right["promptAnchored"]),
        "pairGap": pair_gap,
        "pairLeadFromTop": pair_lead_from_top,
        "outsiderLead": outsider_lead,
        "promptAnchorCount": prompt_anchor_count,
        "answerSetPromptAnchorCount": answer_set_prompt_anchor_count,
        "boundedAnswerPrompt": bounded_answer_prompt,
        "sourceRepeatCount": int(candidate["repeatCount"]),
        "sourceByteStable": source_byte_stable,
        "sourceGreedyStable": source_greedy_stable,
        "candidateSetStable": candidate_set_stable,
        "candidateSetPresenceRate": candidate_set_presence_rate,
        "triggerPolicyId": trigger_policy["id"],
        "triggerEvaluation": trigger_evaluation,
        "stageStability": stage_stability,
        "usefulnessScore": usefulness_score,
        "logitsArtifactPath": artifact.get("logitsArtifactPath"),
        "logitsSha256": artifact.get("logitsSha256"),
    }


def mine_cases_from_candidate(
    candidate: dict[str, Any],
    *,
    policy: dict[str, Any],
    registry_model: dict[str, Any],
    answer_sets: list[dict[str, Any]],
    trigger_policy: dict[str, Any],
    source_report_path: Path,
    source_report_scenario_id: str | None,
) -> list[dict[str, Any]]:
    artifact = choose_reference_artifact(candidate)
    if artifact is None or not artifact.get("topCandidates"):
        return []
    filtered_entries = filter_candidate_entries(
        artifact["topCandidates"],
        prompt_text=candidate["promptText"],
        policy=policy,
    )
    mined: list[dict[str, Any]] = []
    for answer_set in answer_sets:
        matched_entries = match_answer_set_entries(answer_set, candidate_entries=filtered_entries)
        if matched_entries is None or len(matched_entries) < 2:
            continue
        case = build_pair_case(
            candidate=candidate,
            artifact=artifact,
            answer_set=answer_set,
            matched_entries=matched_entries,
            policy=policy,
            registry_model=registry_model,
            trigger_policy=trigger_policy,
            source_report_path=source_report_path,
            source_report_scenario_id=source_report_scenario_id,
        )
        if case is not None:
            mined.append(case)
    return mined


def build_report(
    fixture: dict[str, Any],
    *,
    source_report_paths: list[Path],
    per_prompt_limit: int,
    global_limit: int,
) -> dict[str, Any]:
    policy = copy.deepcopy(fixture["miningPolicy"])
    answer_set_registry_path = resolve_repo_path(
        str(fixture.get("answerSetRegistryPath") or DEFAULT_ANSWER_SET_REGISTRY_PATH)
    )
    trigger_policy_path = resolve_repo_path(
        str(fixture.get("triggerPolicyPath") or DEFAULT_TRIGGER_POLICY_PATH)
    )
    registry_model = load_answer_set_model_registry(answer_set_registry_path, str(fixture["registryModelId"]))
    trigger_policy = load_trigger_policy(trigger_policy_path, str(fixture["triggerPolicyId"]))
    answer_sets = allowed_answer_sets(fixture, registry_model=registry_model)
    mined_by_prompt: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    all_mined: list[dict[str, Any]] = []
    source_candidate_count = 0
    for source_report_path in source_report_paths:
        report = load_json(source_report_path)
        source_candidates = report.get("summary", {}).get("allCandidates") or report.get("summary", {}).get("topCandidates") or []
        source_candidate_count += len(source_candidates)
        for candidate in source_candidates:
            mined_cases = mine_cases_from_candidate(
                candidate,
                policy=policy,
                registry_model=registry_model,
                answer_sets=answer_sets,
                trigger_policy=trigger_policy,
                source_report_path=source_report_path,
                source_report_scenario_id=report.get("scenarioId"),
            )
            if not mined_cases:
                continue
            mined_by_prompt[candidate["promptId"]].extend(mined_cases)
            all_mined.extend(mined_cases)
    prompt_selected: list[dict[str, Any]] = []
    for prompt_id in sorted(mined_by_prompt):
        ranked = sorted(mined_by_prompt[prompt_id], key=pair_case_sort_key)
        prompt_selected.extend(ranked[:per_prompt_limit])
    prompt_selected.sort(key=pair_case_sort_key)
    promoted_cases = prompt_selected[:global_limit]
    pair_counts = collections.Counter(case["candidatePairId"] for case in promoted_cases)
    promotion_bucket_counts = collections.Counter(case["promotionBucket"] for case in promoted_cases)
    top_by_bucket = {
        bucket: [case for case in promoted_cases if case["promotionBucket"] == bucket][: min(global_limit, 12)]
        for bucket in sorted(promotion_bucket_counts)
    }
    return {
        "schemaVersion": 1,
        "source": "doe-pair-agnostic-mine",
        "scenarioId": fixture["scenarioId"],
        "sourceReportPaths": [relative_or_absolute(path) for path in source_report_paths],
        "answerSetRegistryPath": relative_or_absolute(answer_set_registry_path),
        "registryModelId": registry_model["modelId"],
        "registryTokenizerId": registry_model["tokenizerId"],
        "triggerPolicyPath": relative_or_absolute(trigger_policy_path),
        "triggerPolicyId": trigger_policy["id"],
        "perPromptLimit": per_prompt_limit,
        "globalLimit": global_limit,
        "miningPolicy": policy,
        "summary": {
            "sourceReportCount": len(source_report_paths),
            "sourceCandidateCount": source_candidate_count,
            "minedCandidateCount": len(all_mined),
            "promotedCandidateCount": len(promoted_cases),
            "uniquePromptCount": len({case["promptId"] for case in promoted_cases}),
            "uniquePairIdCount": len(pair_counts),
            "topUsefulCasesByBucket": top_by_bucket,
            "promotionBucketCounts": dict(promotion_bucket_counts),
            "pairCounts": dict(pair_counts),
        },
        "cases": promoted_cases,
    }


def main() -> int:
    args = parse_args()
    fixture_path = resolve_repo_path(args.fixture)
    fixture = load_json(fixture_path)
    ensure_fixture_shape(fixture)
    per_prompt_limit = args.per_prompt_limit or int(fixture["defaultPerPromptLimit"])
    global_limit = args.global_limit or int(fixture["defaultGlobalLimit"])
    source_report_paths = [resolve_repo_path(path) for path in args.source_report]
    stamp = timestamp_label(args.timestamp)
    output_dir = resolve_repo_path(args.output_root) / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(
        fixture,
        source_report_paths=source_report_paths,
        per_prompt_limit=per_prompt_limit,
        global_limit=global_limit,
    )
    report["fixturePath"] = relative_or_absolute(fixture_path)
    report["timestamp"] = stamp
    report_path = output_dir / f"{fixture['scenarioId']}.pair-agnostic-mine.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"reportPath": relative_or_absolute(report_path), "summary": report["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
