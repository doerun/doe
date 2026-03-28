#!/usr/bin/env python3
"""Mutate shortlisted semantic pair prompts and promote only usefulness-improving cases."""

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

from bench.runners.determinism_search_helpers import relative_or_absolute
from bench.runners.determinism_search_helpers import resolve_repo_path
from bench.runners.determinism_search_helpers import timestamp_label
from bench.runners.determinism_search_helpers import DEFAULT_ANSWER_SET_REGISTRY_PATH
from bench.runners.determinism_search_helpers import DEFAULT_TRIGGER_POLICY_PATH
from bench.runners.determinism_search_helpers import load_answer_set_model_registry
from bench.runners.determinism_search_helpers import load_trigger_policy
from bench.runners.run_pair_agnostic_pair_miner import mine_cases_from_candidate
from bench.runners.run_pair_agnostic_pair_miner import allowed_answer_sets
from bench.runners.run_real_logit_hunt import build_helper_config
from bench.runners.run_real_logit_hunt import build_summary
from bench.runners.run_real_logit_hunt import run_helper
from bench.runners.run_semantic_pair_hunt import load_json

DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "determinism" / "apple-metal-semantic-pair-mutation-search.gemma270m.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "apple-metal-semantic-pair-mutation-search"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Semantic pair mutation search fixture JSON.")
    parser.add_argument("--source-report", required=True, help="Semantic pair hunt report to mutate from.")
    parser.add_argument("--case-count", type=int, default=None, help="Override selected source-case count from the fixture.")
    parser.add_argument("--runs", type=int, default=None, help="Override scout repeat count from the fixture.")
    parser.add_argument("--timestamp", default=None, help="UTC timestamp label (default: current UTC time).")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for mutation-search artifacts.")
    return parser.parse_args()


def ensure_fixture_shape(fixture: dict[str, Any]) -> None:
    required = (
        "scenarioId",
        "pairMiningFixturePath",
        "dopplerRepoPath",
        "modelArtifactPath",
        "modelId",
        "defaultCaseCount",
        "defaultRepeatCount",
        "decodeSteps",
        "topK",
        "topCandidatesToKeep",
        "persistLogits",
        "mutationTemplates",
    )
    missing = [field for field in required if field not in fixture]
    if missing:
        raise ValueError(f"fixture missing required fields: {', '.join(missing)}")
    if not isinstance(fixture["mutationTemplates"], list) or not fixture["mutationTemplates"]:
        raise ValueError("fixture must define at least one mutation template")
    if "promotionPolicy" not in fixture:
        raise ValueError("fixture must define promotionPolicy")
    if "minimumUsefulnessDelta" not in fixture["promotionPolicy"]:
        raise ValueError("fixture.promotionPolicy.minimumUsefulnessDelta is required")


def sanitize_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.strip())
    return cleaned.strip("-") or "mutation"


def unique_source_cases(report: dict[str, Any], *, case_count: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int, str]] = set()
    for case in report.get("summary", {}).get("bestOverallMatches") or []:
        pair_id = case.get("pairId") or case.get("candidatePairId")
        key = (
            pair_id,
            case["promptId"],
            case["phase"],
            int(case["stepIndex"]),
            case["sourceReportPath"],
        )
        if key in seen:
            continue
        seen.add(key)
        selected.append(case)
        if len(selected) >= case_count:
            break
    return selected


def build_placeholder_values(case: dict[str, Any]) -> dict[str, str]:
    left = case["leftTokenText"].strip()
    right = case["rightTokenText"].strip()
    return {
        "prompt": case["promptText"],
        "left": left,
        "right": right,
        "leftCapitalized": left[:1].upper() + left[1:],
        "rightCapitalized": right[:1].upper() + right[1:],
    }


def swap_inline_choice(prompt_text: str, *, left: str, right: str) -> str | None:
    left_phrase = left.strip()
    right_phrase = right.strip()
    forward = f"{left_phrase} or {right_phrase}"
    reverse = f"{right_phrase} or {left_phrase}"
    if forward in prompt_text:
        return prompt_text.replace(forward, reverse, 1)
    if reverse in prompt_text:
        return prompt_text.replace(reverse, forward, 1)
    return None


def render_mutation_prompt(template: dict[str, Any], *, case: dict[str, Any]) -> str | None:
    kind = template.get("kind", "template")
    values = build_placeholder_values(case)
    if kind == "template":
        return str(template["template"]).format(**values)
    if kind == "swap-inline-choice":
        return swap_inline_choice(case["promptText"], left=case["leftTokenText"], right=case["rightTokenText"])
    raise ValueError(f"unsupported mutation template kind: {kind}")


def build_prompt_candidates(source_cases: list[dict[str, Any]], *, templates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    prompt_candidates: list[dict[str, Any]] = []
    metadata_by_prompt_id: dict[str, dict[str, Any]] = {}
    for case in source_cases:
        pair_id = case.get("pairId") or case.get("candidatePairId")
        for template in templates:
            mutated_text = render_mutation_prompt(template, case=case)
            if not mutated_text or mutated_text == case["promptText"]:
                continue
            prompt_id = sanitize_id(f"{case['promptId']}--{pair_id}--{template['id']}")
            if prompt_id in metadata_by_prompt_id:
                continue
            prompt_candidates.append({"id": prompt_id, "text": mutated_text})
            metadata_by_prompt_id[prompt_id] = {
                "sourceCase": case,
                "templateId": template["id"],
                "mutationKind": template.get("kind", "template"),
                "mutatedPromptText": mutated_text,
            }
    return prompt_candidates, metadata_by_prompt_id


def build_mutation_fixture(fixture: dict[str, Any], *, prompt_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scenarioId": fixture["scenarioId"],
        "dopplerRepoPath": fixture["dopplerRepoPath"],
        "modelArtifactPath": fixture["modelArtifactPath"],
        "modelId": fixture["modelId"],
        "defaultRepeatCount": fixture["defaultRepeatCount"],
        "decodeSteps": fixture["decodeSteps"],
        "topK": fixture["topK"],
        "useChatTemplate": bool(fixture.get("useChatTemplate", False)),
        "runtimeConfig": copy.deepcopy(fixture.get("runtimeConfig") or {}),
        "browser": copy.deepcopy(fixture.get("browser") or {}),
        "promptCandidates": prompt_candidates,
    }


def annotate_mutated_case(mutated_case: dict[str, Any], *, source_case: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(mutated_case)
    annotated["discoveryMode"] = "mutation-derived"
    annotated["promotionBucket"] = "mutation-assisted"
    annotated["sourcePromptId"] = source_case["promptId"]
    annotated["mutationDepth"] = int(source_case.get("mutationDepth") or 0) + 1
    annotated["mutationType"] = metadata["templateId"]
    annotated["mutationKind"] = metadata["mutationKind"]
    annotated["sourceDiscoveryMode"] = source_case.get("discoveryMode", "natural-scout")
    annotated["sourcePromotionBucket"] = source_case.get("promotionBucket", "natural-supporting")
    return annotated


def build_mutation_hunt_report(
    fixture: dict[str, Any],
    *,
    output_dir: Path,
    repeat_count: int,
    prompt_candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], Path]:
    helper_fixture = build_mutation_fixture(fixture, prompt_candidates=prompt_candidates)
    helper_config = build_helper_config(
        helper_fixture,
        output_dir=output_dir / "harvest",
        repeat_count=repeat_count,
        persist_logits=bool(fixture["persistLogits"]),
    )
    harvest = run_helper(helper_config, work_dir=output_dir)
    report = {
        "schemaVersion": 1,
        "source": "doe-mutation-real-logit-hunt",
        "scenarioId": fixture["scenarioId"],
        "harvest": harvest,
        "summary": build_summary(harvest, top_candidates=int(fixture["topCandidatesToKeep"])),
    }
    report_path = output_dir / f"{fixture['scenarioId']}.real-logit-hunt.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report, report_path


def load_pair_mining_context(pair_mining_fixture_path: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    pair_fixture = load_json(pair_mining_fixture_path)
    answer_set_registry_path = resolve_repo_path(
        str(pair_fixture.get("answerSetRegistryPath") or DEFAULT_ANSWER_SET_REGISTRY_PATH)
    )
    trigger_policy_path = resolve_repo_path(
        str(pair_fixture.get("triggerPolicyPath") or DEFAULT_TRIGGER_POLICY_PATH)
    )
    registry_model = load_answer_set_model_registry(answer_set_registry_path, str(pair_fixture["registryModelId"]))
    trigger_policy = load_trigger_policy(trigger_policy_path, str(pair_fixture["triggerPolicyId"]))
    answer_sets = allowed_answer_sets(pair_fixture, registry_model=registry_model)
    return pair_fixture, registry_model, answer_sets, trigger_policy


def select_mutated_pair_case(
    mutated_report: dict[str, Any],
    *,
    prompt_id: str,
    pair_id: str,
    policy: dict[str, Any],
    registry_model: dict[str, Any],
    answer_sets: list[dict[str, Any]],
    trigger_policy: dict[str, Any],
    report_path: Path,
) -> dict[str, Any] | None:
    candidates = mutated_report.get("summary", {}).get("allCandidates") or []
    candidate = next((entry for entry in candidates if entry["promptId"] == prompt_id), None)
    if candidate is None:
        return None
    mined_cases = mine_cases_from_candidate(
        candidate,
        policy=policy,
        registry_model=registry_model,
        answer_sets=answer_sets,
        trigger_policy=trigger_policy,
        source_report_path=report_path,
        source_report_scenario_id=mutated_report.get("scenarioId"),
    )
    return next((case for case in mined_cases if case["candidatePairId"] == pair_id), None)


def compare_mutation(
    *,
    prompt_id: str,
    metadata: dict[str, Any],
    mutated_case: dict[str, Any] | None,
    minimum_usefulness_delta: float,
) -> dict[str, Any]:
    source_case = metadata["sourceCase"]
    source_score = float(source_case.get("usefulnessScore") or 0.0)
    mutated_score = float(mutated_case["usefulnessScore"]) if mutated_case is not None else None
    delta = (mutated_score - source_score) if mutated_score is not None else None
    improved = bool(delta is not None and delta >= minimum_usefulness_delta)
    if mutated_case is None:
        outcome = "pair-missing"
    elif improved:
        outcome = "improved"
    else:
        outcome = "not-improved"
    return {
        "pairId": source_case.get("pairId") or source_case.get("candidatePairId"),
        "sourcePromptId": source_case["promptId"],
        "sourcePromptText": source_case["promptText"],
        "sourcePhase": source_case["phase"],
        "sourceStepIndex": int(source_case["stepIndex"]),
        "templateId": metadata["templateId"],
        "mutationKind": metadata["mutationKind"],
        "mutatedPromptId": prompt_id,
        "mutatedPromptText": metadata["mutatedPromptText"],
        "domainId": source_case.get("domainId"),
        "answerSetId": source_case.get("answerSetId"),
        "discoveryMode": "mutation-derived",
        "sourceUsefulnessScore": source_score,
        "mutatedUsefulnessScore": mutated_score,
        "usefulnessDelta": delta,
        "improved": improved,
        "outcome": outcome,
        "sourcePairGap": float(source_case["pairGap"]),
        "mutatedPairGap": float(mutated_case["pairGap"]) if mutated_case is not None else None,
        "sourceOutsiderLead": float(source_case.get("outsiderLead") or 0.0),
        "mutatedOutsiderLead": float(mutated_case["outsiderLead"]) if mutated_case is not None else None,
        "sourcePairLeadFromTop": float(source_case.get("pairLeadFromTop") or 0.0),
        "mutatedPairLeadFromTop": float(mutated_case["pairLeadFromTop"]) if mutated_case is not None else None,
        "mutatedCase": mutated_case,
    }


def build_promoted_mined_report(
    fixture: dict[str, Any],
    *,
    source_report_path: Path,
    pair_mining_fixture: dict[str, Any],
    registry_model: dict[str, Any],
    trigger_policy: dict[str, Any],
    promoted_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "source": "doe-pair-agnostic-mine",
        "scenarioId": fixture["scenarioId"],
        "sourceReportPaths": [relative_or_absolute(source_report_path)],
        "answerSetRegistryPath": relative_or_absolute(
            resolve_repo_path(str(pair_mining_fixture.get("answerSetRegistryPath") or DEFAULT_ANSWER_SET_REGISTRY_PATH))
        ),
        "registryModelId": registry_model["modelId"],
        "registryTokenizerId": registry_model["tokenizerId"],
        "triggerPolicyPath": relative_or_absolute(
            resolve_repo_path(str(pair_mining_fixture.get("triggerPolicyPath") or DEFAULT_TRIGGER_POLICY_PATH))
        ),
        "triggerPolicyId": trigger_policy["id"],
        "perPromptLimit": len(promoted_cases),
        "globalLimit": len(promoted_cases),
        "miningPolicy": pair_mining_fixture["miningPolicy"],
        "summary": {
            "sourceReportCount": 1,
            "sourceCandidateCount": len(promoted_cases),
            "minedCandidateCount": len(promoted_cases),
            "promotedCandidateCount": len(promoted_cases),
            "uniquePromptCount": len({case["promptId"] for case in promoted_cases}),
            "uniquePairIdCount": len({case["candidatePairId"] for case in promoted_cases}),
            "promotionBucketCounts": dict(collections.Counter(case["promotionBucket"] for case in promoted_cases)),
            "topUsefulCasesByBucket": {
                bucket: [case for case in promoted_cases if case["promotionBucket"] == bucket][: min(len(promoted_cases), 12)]
                for bucket in sorted({case["promotionBucket"] for case in promoted_cases})
            },
            "pairCounts": dict(collections.Counter(case["candidatePairId"] for case in promoted_cases)),
        },
        "cases": promoted_cases,
    }


def comparison_sort_key(item: dict[str, Any]) -> tuple[bool, float, float, str]:
    delta = item["usefulnessDelta"] if item["usefulnessDelta"] is not None else float("-inf")
    score = item["mutatedUsefulnessScore"] if item["mutatedUsefulnessScore"] is not None else float("-inf")
    return (
        item["improved"] is False,
        -delta,
        -score,
        str(item["templateId"]),
    )


def build_negative_control_groups(comparisons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for item in comparisons:
        if item["improved"]:
            continue
        key = (
            str(item.get("domainId") or "unknown"),
            str(item.get("answerSetId") or "unknown"),
            str(item["outcome"]),
        )
        grouped[key].append(item)
    return [
        {
            "domainId": domain_id,
            "answerSetId": answer_set_id,
            "outcome": outcome,
            "count": len(items),
            "templateIds": sorted({str(item["templateId"]) for item in items}),
        }
        for (domain_id, answer_set_id, outcome), items in sorted(grouped.items())
    ]


def build_report(
    fixture: dict[str, Any],
    *,
    source_report: dict[str, Any],
    output_dir: Path,
    repeat_count: int,
    case_count: int,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    source_cases = unique_source_cases(source_report, case_count=case_count)
    prompt_candidates, metadata_by_prompt_id = build_prompt_candidates(source_cases, templates=fixture["mutationTemplates"])
    if not prompt_candidates:
        raise ValueError("mutation search did not produce any prompt candidates from the selected source cases")
    mutation_hunt_report, mutation_hunt_report_path = build_mutation_hunt_report(
        fixture,
        output_dir=output_dir,
        repeat_count=repeat_count,
        prompt_candidates=prompt_candidates,
    )
    (
        pair_mining_fixture,
        registry_model,
        answer_sets,
        trigger_policy,
    ) = load_pair_mining_context(resolve_repo_path(fixture["pairMiningFixturePath"]))
    pair_policy = pair_mining_fixture["miningPolicy"]
    minimum_usefulness_delta = float(fixture["promotionPolicy"]["minimumUsefulnessDelta"])
    comparisons: list[dict[str, Any]] = []
    promoted_cases: list[dict[str, Any]] = []
    for prompt_id, metadata in metadata_by_prompt_id.items():
        source_case = metadata["sourceCase"]
        pair_id = source_case.get("pairId") or source_case.get("candidatePairId")
        mutated_case = select_mutated_pair_case(
            mutation_hunt_report,
            prompt_id=prompt_id,
            pair_id=pair_id,
            policy=pair_policy,
            registry_model=registry_model,
            answer_sets=answer_sets,
            trigger_policy=trigger_policy,
            report_path=mutation_hunt_report_path,
        )
        if mutated_case is not None:
            mutated_case = annotate_mutated_case(mutated_case, source_case=source_case, metadata=metadata)
        comparison = compare_mutation(
            prompt_id=prompt_id,
            metadata=metadata,
            mutated_case=mutated_case,
            minimum_usefulness_delta=minimum_usefulness_delta,
        )
        comparisons.append(comparison)
        if comparison["improved"] and mutated_case is not None:
            promoted_cases.append(mutated_case)
    comparisons.sort(key=comparison_sort_key)
    promoted_mined_report = build_promoted_mined_report(
        fixture,
        source_report_path=mutation_hunt_report_path,
        pair_mining_fixture=pair_mining_fixture,
        registry_model=registry_model,
        trigger_policy=trigger_policy,
        promoted_cases=promoted_cases,
    )
    report = {
        "schemaVersion": 1,
        "source": "doe-semantic-pair-mutation-search",
        "scenarioId": fixture["scenarioId"],
        "sourceSemanticReportScenarioId": source_report.get("scenarioId"),
        "sourceSemanticReportPath": None,
        "mutationRealLogitReportPath": relative_or_absolute(mutation_hunt_report_path),
        "promotedMinedCandidateCount": len(promoted_cases),
        "summary": {
            "sourceCaseCount": len(source_cases),
            "mutationCandidateCount": len(prompt_candidates),
            "comparisonCount": len(comparisons),
            "improvedMutationCount": sum(1 for item in comparisons if item["improved"]),
            "outcomeCounts": dict(collections.Counter(item["outcome"] for item in comparisons)),
            "negativeControlGroups": build_negative_control_groups(comparisons),
            "topPromotions": [item for item in comparisons if item["improved"]][: min(8, len(comparisons))],
            "negativeControls": [item for item in comparisons if not item["improved"]][: min(8, len(comparisons))],
        },
        "sourceCases": source_cases,
        "comparisons": comparisons,
    }
    return report, promoted_mined_report, mutation_hunt_report_path


def main() -> int:
    args = parse_args()
    fixture_path = resolve_repo_path(args.fixture)
    fixture = load_json(fixture_path)
    ensure_fixture_shape(fixture)
    source_report_path = resolve_repo_path(args.source_report)
    source_report = load_json(source_report_path)
    stamp = timestamp_label(args.timestamp)
    output_dir = resolve_repo_path(args.output_root) / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report, promoted_mined_report, mutation_hunt_report_path = build_report(
        fixture,
        source_report=source_report,
        output_dir=output_dir,
        repeat_count=args.runs or int(fixture["defaultRepeatCount"]),
        case_count=args.case_count or int(fixture["defaultCaseCount"]),
    )
    report["fixturePath"] = relative_or_absolute(fixture_path)
    report["sourceSemanticReportPath"] = relative_or_absolute(source_report_path)
    report["timestamp"] = stamp
    promoted_mined_report["fixturePath"] = relative_or_absolute(fixture_path)
    promoted_mined_report["timestamp"] = stamp
    promoted_mined_report_path = output_dir / f"{fixture['scenarioId']}.pair-agnostic-mine.json"
    promoted_mined_report_path.write_text(json.dumps(promoted_mined_report, indent=2) + "\n", encoding="utf-8")
    report["promotedMinedReportPath"] = relative_or_absolute(promoted_mined_report_path)
    report["mutationRealLogitReportPath"] = relative_or_absolute(mutation_hunt_report_path)
    report_path = output_dir / f"{fixture['scenarioId']}.semantic-pair-mutation-search.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "reportPath": relative_or_absolute(report_path),
                "promotedMinedReportPath": relative_or_absolute(promoted_mined_report_path),
                "summary": report["summary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
