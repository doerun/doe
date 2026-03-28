#!/usr/bin/env python3
"""Rank semantic token-pair cases and emit replayable decode-state recipes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.runners.determinism_search_helpers import load_json
from bench.runners.determinism_search_helpers import relative_or_absolute
from bench.runners.determinism_search_helpers import resolve_repo_path
from bench.runners.determinism_search_helpers import semantic_match_sort_key
from bench.runners.determinism_search_helpers import timestamp_label

DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "determinism" / "apple-metal-semantic-pair-hunt.gemma270m.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "apple-metal-semantic-pair-hunt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Semantic pair hunt fixture JSON.")
    parser.add_argument(
        "--source-report",
        action="append",
        default=[],
        help="Real-logit hunt report to scan. Pass multiple times to aggregate reports.",
    )
    parser.add_argument(
        "--mined-report",
        action="append",
        default=[],
        help="Pair-agnostic mined-pair report to promote into decode-state receipts. Pass multiple times to aggregate.",
    )
    parser.add_argument("--per-pair-limit", type=int, default=None, help="Override per-pair result limit from the fixture.")
    parser.add_argument("--timestamp", default=None, help="UTC timestamp label (default: current UTC time).")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for semantic-pair hunt artifacts.")
    return parser.parse_args()


def ensure_fixture_shape(fixture: dict[str, Any]) -> None:
    missing = [field for field in ("scenarioId", "semanticPairs", "defaultPerPairLimit") if field not in fixture]
    if missing:
        raise ValueError(f"fixture missing required fields: {', '.join(missing)}")
    if not isinstance(fixture["semanticPairs"], list) or not fixture["semanticPairs"]:
        raise ValueError("fixture must define at least one semantic pair")
    for index, pair in enumerate(fixture["semanticPairs"]):
        for field in ("id", "leftTokenText", "rightTokenText"):
            if not isinstance(pair.get(field), str) or not pair[field]:
                raise ValueError(f"semanticPairs[{index}].{field} must be a non-empty string")


def build_prompt_key(prompt_result: dict[str, Any]) -> str:
    prompt_id = prompt_result.get("id")
    if isinstance(prompt_id, str) and prompt_id:
        return prompt_id
    return f"prompt-{prompt_result['promptIndex']:03d}"


def build_state_index(report: dict[str, Any]) -> dict[tuple[str, str, int], dict[str, Any]]:
    prompt_results_by_id: dict[str, dict[str, Any]] = {}
    for run in report.get("harvest", {}).get("runs", []):
        for prompt_result in run.get("promptResults", []):
            if prompt_result.get("status") != "ok":
                continue
            prompt_key = build_prompt_key(prompt_result)
            prompt_results_by_id.setdefault(prompt_key, prompt_result)

    state_index: dict[tuple[str, str, int], dict[str, Any]] = {}
    for prompt_key, prompt_result in prompt_results_by_id.items():
        prompt_tokens = list(prompt_result.get("promptTokenIds") or [])
        greedy_sequence = list(prompt_result.get("greedyTokenSequence") or [])
        prompt_text = prompt_result.get("text")
        for step in prompt_result.get("steps", []):
            phase = step["phase"]
            step_index = int(step["stepIndex"])
            if phase == "prefill":
                current_ids = list(prompt_tokens)
            else:
                current_ids = prompt_tokens + greedy_sequence[:step_index]
            state_index[(prompt_key, phase, step_index)] = {
                "promptId": prompt_key,
                "promptText": prompt_text,
                "phase": phase,
                "stepIndex": step_index,
                "stepLabel": "prefill" if phase == "prefill" else f"decode[{step_index}]",
                "promptTokenIds": list(prompt_tokens),
                "greedyTokenSequence": list(greedy_sequence),
                "currentIds": current_ids,
                "currentIdsLength": len(current_ids),
                "recordedCurrentIdsLength": step.get("currentIdsLength"),
                "inputToken": step.get("inputToken"),
            }
    return state_index


def find_token_entry(entries: list[dict[str, Any]], token_text: str) -> dict[str, Any] | None:
    return next((entry for entry in entries if entry.get("tokenText") == token_text), None)


def pair_sort_key(result: dict[str, Any]) -> tuple[float, float, int, int]:
    return (
        float(result["pairGap"]),
        float(result["pairLeadFromTop"]),
        int(result["leftRank"]),
        int(result["rightRank"]),
    )


def scan_pair_in_report(
    *,
    pair: dict[str, Any],
    report: dict[str, Any],
    report_path: Path,
) -> list[dict[str, Any]]:
    state_index = build_state_index(report)
    candidates = report.get("summary", {}).get("allCandidates") or report.get("summary", {}).get("topCandidates") or []
    results: list[dict[str, Any]] = []
    allowed_prompts = set(pair.get("promptIds") or [])
    for candidate in candidates:
        prompt_id = candidate.get("promptId")
        if allowed_prompts and prompt_id not in allowed_prompts:
            continue
        artifacts = candidate.get("artifacts") or []
        if not artifacts:
            continue
        state = state_index.get((prompt_id, candidate["phase"], int(candidate["stepIndex"])))
        if state is None:
            continue
        for artifact in artifacts:
            top_candidates = artifact.get("topCandidates") or []
            left_entry = find_token_entry(top_candidates, pair["leftTokenText"])
            right_entry = find_token_entry(top_candidates, pair["rightTokenText"])
            if left_entry is None or right_entry is None or not top_candidates:
                continue
            top_entry = top_candidates[0]
            left_rank = next(index for index, entry in enumerate(top_candidates, start=1) if entry is left_entry)
            right_rank = next(index for index, entry in enumerate(top_candidates, start=1) if entry is right_entry)
            pair_top_logit = max(float(left_entry["logit"]), float(right_entry["logit"]))
            results.append(
                {
                    "pairId": pair["id"],
                    "candidateSetSource": "fixture-declared",
                    "sourceReportPath": relative_or_absolute(report_path),
                    "sourceReportScenarioId": report.get("scenarioId"),
                    "sourceRepeatIndex": artifact.get("repeatIndex"),
                    "promptId": prompt_id,
                    "promptText": candidate["promptText"],
                    "phase": candidate["phase"],
                    "stepIndex": int(candidate["stepIndex"]),
                    "stepLabel": candidate["stepLabel"],
                    "top2Gap": candidate.get("minTop2Gap"),
                    "pairGap": abs(float(left_entry["logit"]) - float(right_entry["logit"])),
                    "pairLeadFromTop": float(top_entry["logit"]) - pair_top_logit,
                    "topTokenText": top_entry.get("tokenText"),
                    "topToken": int(top_entry["token"]),
                    "topTokenLogit": float(top_entry["logit"]),
                    "leftTokenText": pair["leftTokenText"],
                    "leftToken": int(left_entry["token"]),
                    "leftLogit": float(left_entry["logit"]),
                    "leftRank": left_rank,
                    "rightTokenText": pair["rightTokenText"],
                    "rightToken": int(right_entry["token"]),
                    "rightLogit": float(right_entry["logit"]),
                    "rightRank": right_rank,
                    "higherLogitTokenText": pair["leftTokenText"] if float(left_entry["logit"]) >= float(right_entry["logit"]) else pair["rightTokenText"],
                    "usefulnessScore": None,
                    "decodeStateRecipe": {
                        "promptTokenIds": state["promptTokenIds"],
                        "decodePrefixTokenIds": state["currentIds"][len(state["promptTokenIds"]):],
                        "currentIds": state["currentIds"],
                        "currentIdsLength": state["currentIdsLength"],
                        "recordedCurrentIdsLength": state["recordedCurrentIdsLength"],
                        "inputToken": state["inputToken"],
                        "greedyTokenSequence": state["greedyTokenSequence"],
                    },
                    "logitsArtifactPath": artifact.get("logitsArtifactPath"),
                    "logitsSha256": artifact.get("logitsSha256"),
                }
            )
    return sorted(results, key=semantic_match_sort_key)


def build_source_report_index(source_report_paths: list[Path]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for path in source_report_paths:
        report = load_json(path)
        indexed[relative_or_absolute(path)] = {
            "path": path,
            "report": report,
            "stateIndex": build_state_index(report),
        }
    return indexed


def enrich_mined_case(mined_case: dict[str, Any], *, source_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source_key = mined_case["sourceReportPath"]
    indexed = source_index.get(source_key)
    if indexed is None:
        raise ValueError(f"mined case references unknown source report: {source_key}")
    state = indexed["stateIndex"].get((mined_case["promptId"], mined_case["phase"], int(mined_case["stepIndex"])))
    if state is None:
        raise ValueError(
            "source report does not contain decode-state recipe inputs for "
            f"{mined_case['promptId']} phase={mined_case['phase']} stepIndex={mined_case['stepIndex']}"
        )
    result = dict(mined_case)
    result["pairId"] = mined_case["candidatePairId"]
    result["decodeStateRecipe"] = {
        "promptTokenIds": state["promptTokenIds"],
        "decodePrefixTokenIds": state["currentIds"][len(state["promptTokenIds"]):],
        "currentIds": state["currentIds"],
        "currentIdsLength": state["currentIdsLength"],
        "recordedCurrentIdsLength": state["recordedCurrentIdsLength"],
        "inputToken": state["inputToken"],
        "greedyTokenSequence": state["greedyTokenSequence"],
    }
    return result


def build_report_from_mined_reports(
    mined_reports: list[dict[str, Any]],
    *,
    per_pair_limit: int,
) -> dict[str, Any]:
    referenced_source_paths = {
        resolve_repo_path(str(path))
        for report in mined_reports
        for path in report.get("sourceReportPaths") or []
    }
    source_index = build_source_report_index(sorted(referenced_source_paths))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for report in mined_reports:
        for case in report.get("cases") or []:
            enriched = enrich_mined_case(case, source_index=source_index)
            grouped.setdefault(enriched["candidatePairId"], []).append(enriched)
    per_pair: list[dict[str, Any]] = []
    all_matches: list[dict[str, Any]] = []
    for pair_id in sorted(grouped):
        matches = sorted(grouped[pair_id], key=semantic_match_sort_key)
        top_matches = matches[:per_pair_limit]
        exemplar = matches[0]
        per_pair.append(
            {
                "pairId": pair_id,
                "leftTokenText": exemplar["leftTokenText"],
                "rightTokenText": exemplar["rightTokenText"],
                "candidateSetSource": exemplar["candidateSetSource"],
                "matchCount": len(matches),
                "topMatches": top_matches,
            }
        )
        all_matches.extend(top_matches)
    all_matches.sort(key=semantic_match_sort_key)
    return {
        "schemaVersion": 1,
        "source": "doe-semantic-pair-hunt",
        "scenarioId": mined_reports[0]["scenarioId"] if mined_reports else "doe-semantic-pair-hunt",
        "sourceKind": "mined-topk-v1",
        "sourceReportPaths": sorted(source_index.keys()),
        "perPairLimit": per_pair_limit,
        "summary": {
            "pairCount": len(per_pair),
            "matchedPairCount": sum(1 for pair in per_pair if pair["matchCount"] > 0),
            "unmatchedPairIds": [],
            "bestOverallMatches": all_matches[:per_pair_limit],
        },
        "pairs": per_pair,
    }


def build_report(
    fixture: dict[str, Any],
    *,
    source_report_paths: list[Path],
    per_pair_limit: int,
) -> dict[str, Any]:
    source_reports = [(path, load_json(path)) for path in source_report_paths]
    per_pair: list[dict[str, Any]] = []
    all_matches: list[dict[str, Any]] = []
    for pair in fixture["semanticPairs"]:
        pair_matches: list[dict[str, Any]] = []
        for report_path, report in source_reports:
            pair_matches.extend(scan_pair_in_report(pair=pair, report=report, report_path=report_path))
        pair_matches.sort(key=pair_sort_key)
        top_matches = pair_matches[:per_pair_limit]
        per_pair.append(
            {
                "pairId": pair["id"],
                "leftTokenText": pair["leftTokenText"],
                "rightTokenText": pair["rightTokenText"],
                "promptIds": list(pair.get("promptIds") or []),
                "matchCount": len(pair_matches),
                "topMatches": top_matches,
            }
        )
        all_matches.extend(top_matches)
    all_matches.sort(key=semantic_match_sort_key)
    return {
        "schemaVersion": 1,
        "source": "doe-semantic-pair-hunt",
        "scenarioId": fixture["scenarioId"],
        "sourceKind": "fixture-declared",
        "sourceReportPaths": [relative_or_absolute(path) for path in source_report_paths],
        "perPairLimit": per_pair_limit,
        "summary": {
            "pairCount": len(fixture["semanticPairs"]),
            "matchedPairCount": sum(1 for pair in per_pair if pair["matchCount"] > 0),
            "unmatchedPairIds": [pair["pairId"] for pair in per_pair if pair["matchCount"] == 0],
            "bestOverallMatches": all_matches[:per_pair_limit],
        },
        "pairs": per_pair,
    }


def main() -> int:
    args = parse_args()
    mined_report_paths = [resolve_repo_path(path) for path in args.mined_report]
    source_report_paths = [resolve_repo_path(path) for path in args.source_report]
    if not source_report_paths and not mined_report_paths:
        raise ValueError("pass at least one --source-report or --mined-report")
    if source_report_paths and mined_report_paths:
        raise ValueError("use --source-report or --mined-report, not both in the same invocation")
    stamp = timestamp_label(args.timestamp)
    output_dir = resolve_repo_path(args.output_root) / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = resolve_repo_path(args.fixture)
    fixture = None
    if source_report_paths:
        fixture = load_json(fixture_path)
        ensure_fixture_shape(fixture)
        per_pair_limit = args.per_pair_limit or int(fixture["defaultPerPairLimit"])
        report = build_report(fixture, source_report_paths=source_report_paths, per_pair_limit=per_pair_limit)
        report["fixturePath"] = relative_or_absolute(fixture_path)
    else:
        mined_reports = [load_json(path) for path in mined_report_paths]
        per_pair_limit = args.per_pair_limit or int(mined_reports[0].get("perPromptLimit") or 3)
        report = build_report_from_mined_reports(mined_reports, per_pair_limit=per_pair_limit)
        report["fixturePath"] = None
        report["minedReportPaths"] = [relative_or_absolute(path) for path in mined_report_paths]
    report["timestamp"] = stamp
    report_name = report["scenarioId"]
    report_path = output_dir / f"{report_name}.semantic-pair-hunt.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"reportPath": relative_or_absolute(report_path), "summary": report["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
