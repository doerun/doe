#!/usr/bin/env python3
"""Rank normalized sample.token fragility rows for promotion readiness."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from bench.lib.config_validation import load_validated_config


DEFAULT_PLAN_PATH = REPO_ROOT / "config" / "numeric-stability-decode-fragility-plan.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "numeric-stability-decode-fragility"
REPORT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "numeric-stability-decode-fragility-report"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSONL path containing normalized decode fragility rows.")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN_PATH), help="Decode fragility plan config path.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for ranked reports.")
    parser.add_argument("--timestamp", default=None, help="UTC timestamp label. Default: current UTC time.")
    return parser.parse_args()


def timestamp_label() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def relative_or_absolute(path: Path) -> str:
    absolute = path.resolve()
    try:
        return str(absolute.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(absolute)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} must be a JSON object per line")
            rows.append(payload)
    return rows


def get_path(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def normalize_numeric(value: Any, *, direction: str, ceiling: float | None) -> float:
    if direction == "boolean-boost":
        return 1.0 if bool(value) else 0.0
    if value is None:
        return 0.0
    numeric = float(value)
    if ceiling is None:
        ceiling = 1.0
    bounded = min(max(numeric, 0.0), float(ceiling))
    ratio = bounded / float(ceiling)
    if direction == "lower-is-fragile":
        return max(0.0, 1.0 - ratio)
    if direction == "lower-is-better":
        return max(0.0, 1.0 - ratio)
    if direction == "higher-is-fragile":
        return min(1.0, ratio)
    raise ValueError(f"unsupported signal direction: {direction}")


def build_semantic_priority_map(plan: dict[str, Any]) -> dict[str, float]:
    return {
        entry["classId"]: float(entry["priorityWeight"])
        for entry in plan["semanticPriorityClasses"]
    }


def validate_required_paths(case: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for dotted_path in plan["normalizedInputContract"]["requiredPaths"]:
        if get_path(case, dotted_path) is None:
            missing.append(dotted_path)
    return missing


def score_case(case: dict[str, Any], plan: dict[str, Any], semantic_priority_map: dict[str, float]) -> tuple[float, list[str]]:
    missing_required = validate_required_paths(case, plan)
    if missing_required:
        return 0.0, [f"missing-required-field:{path}" for path in missing_required]
    score = semantic_priority_map.get(case["semanticPriorityClass"], 0.0)
    rejection_reasons: list[str] = []
    for signal in plan["scoringSignals"]:
        value = get_path(case, signal["sourcePath"])
        if value is None:
            if signal.get("missingValuePolicy") == "reject":
                rejection_reasons.append(f"missing-required-field:{signal['sourcePath']}")
            continue
        score += float(signal["weight"]) * normalize_numeric(
            value,
            direction=signal["direction"],
            ceiling=signal.get("normalizationCeiling"),
        )
    return score, rejection_reasons


def ranking_bucket_threshold(plan: dict[str, Any], bucket_id: str) -> float:
    for bucket in plan["rankingBuckets"]:
        if bucket["bucketId"] == bucket_id:
            return float(bucket["minimumScore"])
    raise ValueError(f"missing ranking bucket threshold for {bucket_id}")


def evaluate_promotion(case: dict[str, Any], plan: dict[str, Any], score: float, initial_reasons: list[str]) -> tuple[str, list[str]]:
    hard_reasons = list(initial_reasons)
    investigate_reasons: list[str] = []
    requirements = plan["promotionRequirements"]
    if not bool(get_path(case, "metrics.actualSelectedTokenChanged")):
        hard_reasons.append("selected-token-unchanged")
    if not bool(get_path(case, "metrics.meaningfulToken")):
        hard_reasons.append("meaningless-token")
    decode_step_index = int(case["decodeStepIndex"])
    if decode_step_index > int(requirements["maxDecodeStepIndex"]):
        hard_reasons.append("late-decode-position")
    if not bool(get_path(case, "metrics.withinPolicyStable")):
        investigate_reasons.append("within-policy-instability")
    if not bool(get_path(case, "upstream.fastStableDisagreement")):
        hard_reasons.append("missing-upstream-disagreement")
    if not bool(get_path(case, "suffixReplay.available")):
        investigate_reasons.append("missing-suffix-replay")
    elif not bool(get_path(case, "suffixReplay.divergent")):
        investigate_reasons.append("suffix-replay-converged")

    if hard_reasons:
        return "reject", sorted(set(hard_reasons))
    if score >= float(requirements["minimumPromotableScore"]) and not investigate_reasons:
        return "promotable", []
    investigate_threshold = ranking_bucket_threshold(plan, "investigate")
    if score >= investigate_threshold:
        reasons = investigate_reasons or ["score-below-threshold"]
        return "investigate", sorted(set(reasons))
    reasons = investigate_reasons + ["score-below-threshold"]
    return "reject", sorted(set(reasons))


def build_ranked_case(case: dict[str, Any], score: float, ranking_bucket: str, rejection_reasons: list[str]) -> dict[str, Any]:
    selected_tokens = {
        "fast": int(case["selectedToken"]["fast"]),
        "stable": int(case["selectedToken"]["stable"]),
        "reference": int(case["selectedToken"]["reference"]),
    }
    selected_token_text = case.get("selectedTokenText") or {}
    for key in ("fast", "stable", "reference"):
        if selected_token_text.get(key) is not None:
            selected_tokens[f"{key}Text"] = str(selected_token_text[key])

    metrics = dict(case.get("metrics") or {})
    if case.get("suffixReplay"):
        metrics["suffixReplayDivergent"] = bool(case["suffixReplay"].get("divergent"))
        metrics["suffixReplayAvailable"] = bool(case["suffixReplay"].get("available"))

    ranked_case = {
        "caseId": str(case["caseId"]),
        "promptText": str(case["promptText"]),
        "decodeStepIndex": int(case["decodeStepIndex"]),
        "semanticPriorityClass": str(case["semanticPriorityClass"]),
        "score": round(float(score), 6),
        "rankingBucket": ranking_bucket,
        "selectedTokens": selected_tokens,
        "sourceArtifactPath": str(case["sourceArtifactPath"]),
        "metrics": metrics,
        "rejectionReasons": rejection_reasons,
    }
    receipt_path = case.get("receiptPath")
    if receipt_path:
        ranked_case["receiptPath"] = str(receipt_path)
    upstream_semantic_op = get_path(case, "upstream.firstDivergenceSemanticOpId")
    if upstream_semantic_op:
        ranked_case["upstreamSemanticOpId"] = str(upstream_semantic_op)
    return ranked_case


def summarize_ranked_cases(ranked_cases: list[dict[str, Any]]) -> dict[str, Any]:
    counts_by_bucket = collections.Counter(case["rankingBucket"] for case in ranked_cases)
    counts_by_semantic_class = collections.Counter(case["semanticPriorityClass"] for case in ranked_cases)
    summary: dict[str, Any] = {
        "caseCount": len(ranked_cases),
        "countsByBucket": dict(sorted(counts_by_bucket.items())),
        "countsBySemanticPriorityClass": dict(sorted(counts_by_semantic_class.items())),
    }
    if ranked_cases:
        summary["topCaseId"] = ranked_cases[0]["caseId"]
    return summary


def build_report(*, cases: list[dict[str, Any]], plan: dict[str, Any], plan_path: Path, source_path: Path, timestamp: str) -> dict[str, Any]:
    semantic_priority_map = build_semantic_priority_map(plan)
    ranked_cases: list[dict[str, Any]] = []
    for case in cases:
        score, initial_reasons = score_case(case, plan, semantic_priority_map)
        ranking_bucket, rejection_reasons = evaluate_promotion(case, plan, score, initial_reasons)
        ranked_cases.append(build_ranked_case(case, score, ranking_bucket, rejection_reasons))
    ranked_cases.sort(key=lambda case: (-case["score"], case["caseId"]))
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "artifactKind": ARTIFACT_KIND,
        "timestamp": timestamp,
        "planPath": relative_or_absolute(plan_path),
        "sourcePath": relative_or_absolute(source_path),
        "rankedCases": ranked_cases,
        "summary": summarize_ranked_cases(ranked_cases),
    }


def write_report(report: dict[str, Any], *, output_root: Path, timestamp: str) -> Path:
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "numeric_stability_decode_fragility.report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    plan_path = Path(args.plan)
    output_root = Path(args.output_root)
    timestamp = args.timestamp or timestamp_label()

    plan = load_validated_config(plan_path)
    cases = load_jsonl(input_path)
    report = build_report(
        cases=cases,
        plan=plan,
        plan_path=plan_path,
        source_path=input_path,
        timestamp=timestamp,
    )
    report_path = write_report(report, output_root=output_root, timestamp=timestamp)
    print(str(report_path))


if __name__ == "__main__":
    main()
