#!/usr/bin/env python3
"""Normalize decode.sample_token receipts into rankable decode-fragility rows."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from bench.lib.config_validation import load_validated_config


RECEIPT_SCHEMA_PATH = REPO_ROOT / "config" / "doe-numeric-stability-receipt.schema.json"
ENRICHMENT_SCHEMA_PATH = REPO_ROOT / "config" / "numeric-stability-decode-row-enrichment.schema.json"
ROW_SCHEMA_PATH = REPO_ROOT / "config" / "numeric-stability-decode-row.schema.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "numeric-stability-decode-rows"

POLICY_ACTION_WORDS = {
    "allow",
    "block",
    "approve",
    "approved",
    "deny",
    "denied",
    "go",
    "stop",
    "public",
    "private",
    "internal",
    "external",
    "release",
    "redact",
    "accept",
    "reject",
    "keep",
}
JSON_BOOLEAN_WORDS = {"true", "false", "null"}
MODERATION_WORDS = {"safe", "unsafe", "spam", "phishing", "allow", "block"}
SHORT_ANSWER_WORDS = {"yes", "no", "keep", "flip"}
DELIMITER_ONLY = {"{", "}", "[", "]", "(", ")", ",", ":", ";", "\"", "'"}
TOKEN_INDEX_PATTERN = re.compile(r"(?:\.t|\.tok|\.step)(\d+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Receipt JSON or JSONL path.")
    parser.add_argument(
        "--enrichment",
        default=None,
        help="Optional enrichment JSON for prompt text, stability, suffix replay, and semantic class overrides.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Output root for normalized JSONL rows.",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="UTC timestamp label. Default: derive from current UTC time.",
    )
    return parser.parse_args()


def timestamp_label() -> str:
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def relative_or_absolute(path: Path) -> str:
    absolute = path.resolve()
    try:
        return str(absolute.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(absolute)


def load_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if not isinstance(payload, dict):
                    raise ValueError(f"{path}:{line_number} must contain JSON objects")
                rows.append(payload)
        return rows
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    raise ValueError(f"{path} must contain a JSON object, array of objects, or JSONL objects")


def load_receipts(path: Path) -> list[dict[str, Any]]:
    schema = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    receipts = load_json_or_jsonl(path)
    for index, receipt in enumerate(receipts):
        errors = sorted(validator.iter_errors(receipt), key=lambda error: list(error.absolute_path))
        if errors:
            raise jsonschema.ValidationError(
                f"{path} receipt index {index} failed validation: {errors[0].message}"
            )
    return receipts


def load_enrichment(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = load_validated_config(path, ENRICHMENT_SCHEMA_PATH)
    return list(payload["entries"])


def validate_rows(rows: list[dict[str, Any]]) -> None:
    schema = json.loads(ROW_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for index, row in enumerate(rows):
        errors = sorted(validator.iter_errors(row), key=lambda error: list(error.absolute_path))
        if errors:
            raise jsonschema.ValidationError(
                f"normalized decode row index {index} failed validation: {errors[0].message}"
            )


def receipt_matches_decode_boundary(receipt: dict[str, Any]) -> bool:
    return (
        receipt.get("semanticOpId") == "decode.sample_token"
        or receipt.get("semanticPhase") == "sample_token"
        or receipt.get("operatorFamily") == "decode-sample-token"
    )


def match_enrichment(
    entries: list[dict[str, Any]],
    *,
    receipt_path: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    for entry in entries:
        match = entry["match"]
        if "receiptPath" in match and match["receiptPath"] != receipt_path:
            continue
        if "semanticStage" in match and match["semanticStage"] != receipt["semanticStage"]:
            continue
        if "semanticOpId" in match and match["semanticOpId"] != receipt["semanticOpId"]:
            continue
        return dict(entry["overrides"])
    return {}


def safe_temperature(value: Any) -> float:
    if value is None:
        return 1.0
    temperature = float(value)
    return temperature if temperature > 0 else 1.0


def softmax_probabilities(logits: list[float], *, temperature: float) -> list[float]:
    if not logits:
        return []
    scaled = [logit / temperature for logit in logits]
    maximum = max(scaled)
    weights = [math.exp(value - maximum) for value in scaled]
    denominator = sum(weights)
    return [weight / denominator for weight in weights]


def sorted_fast_candidates(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        receipt["candidates"],
        key=lambda candidate: (-float(candidate["fastLogit"]), int(candidate["tokenId"])),
    )


def candidate_label_map(receipt: dict[str, Any]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for candidate in receipt["candidates"]:
        label = candidate.get("label")
        if label is None:
            continue
        mapping[int(candidate["tokenId"])] = str(label)
    return mapping


def normalize_token_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped[:1] in {"\"", "'"} and stripped[-1:] == stripped[:1] and len(stripped) >= 2:
        stripped = stripped[1:-1].strip()
    return stripped or None


def canonical_token_form(value: str | None) -> str | None:
    normalized = normalize_token_text(value)
    if normalized is None:
        return None
    return re.sub(r"[^a-z0-9_]+", "", normalized.lower()) or None


def looks_like_meaningful_token(token_forms: list[str], semantic_priority_class: str) -> bool:
    if semantic_priority_class != "other":
        return True
    if not token_forms:
        return False
    unique_forms = sorted(set(token_forms))
    if len(unique_forms) <= 1:
        return False
    if all(form in JSON_BOOLEAN_WORDS for form in unique_forms):
        return True
    if any(form in POLICY_ACTION_WORDS for form in unique_forms):
        return True
    if any(form in MODERATION_WORDS for form in unique_forms):
        return True
    if any(form in SHORT_ANSWER_WORDS for form in unique_forms):
        return True
    if all(form in DELIMITER_ONLY for form in unique_forms):
        return False
    return any(any(character.isalnum() for character in form) for form in unique_forms)


def infer_semantic_priority_class(token_forms: list[str]) -> str:
    if not token_forms:
        return "other"
    if any(form in JSON_BOOLEAN_WORDS for form in token_forms):
        return "json-boolean"
    if any(form in POLICY_ACTION_WORDS for form in token_forms):
        return "policy-action"
    if any(form in MODERATION_WORDS for form in token_forms):
        return "moderation-label"
    if any("_" in form or "." in form for form in token_forms):
        return "tool-choice"
    if any(form in SHORT_ANSWER_WORDS for form in token_forms):
        return "short-answer"
    return "other"


def infer_decode_step_index(receipt: dict[str, Any]) -> int:
    for value in (receipt.get("semanticOpId"), receipt.get("semanticStage")):
        match = TOKEN_INDEX_PATTERN.search(str(value or ""))
        if match:
            return int(match.group(1))
    return 0


def build_selected_token_text(
    receipt: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, str]:
    labels = candidate_label_map(receipt)
    selected = receipt["selectedToken"]
    override_text = dict(overrides.get("selectedTokenText") or {})
    result: dict[str, str] = {}
    for lane in ("fast", "stable", "reference"):
        if lane in override_text:
            result[lane] = str(override_text[lane])
            continue
        token_id = int(selected[lane])
        label = labels.get(token_id)
        if label is not None:
            result[lane] = label
    return result


def build_probability_metrics(receipt: dict[str, Any]) -> dict[str, Any]:
    candidates = sorted_fast_candidates(receipt)
    fast_logits = [float(candidate["fastLogit"]) for candidate in candidates]
    decode_boundary = receipt.get("decodeBoundary") or {}
    boundary_metrics = decode_boundary.get("metrics") or {}
    selected_token = receipt["selectedToken"]
    live_selected_token = decode_boundary.get("liveSelectedToken")
    probabilities = softmax_probabilities(
        fast_logits,
        temperature=safe_temperature(decode_boundary.get("temperature")),
    )
    top1_margin = 0.0
    if len(probabilities) >= 2:
        top1_margin = max(0.0, probabilities[0] - probabilities[1])

    top_k_gap = None
    top_k = decode_boundary.get("topK")
    if top_k is not None and len(probabilities) > int(top_k):
        boundary_index = int(top_k) - 1
        top_k_gap = max(0.0, probabilities[boundary_index] - probabilities[boundary_index + 1])

    top_p_gap = None
    top_p = decode_boundary.get("topP")
    if top_p is not None and probabilities:
        cumulative = 0.0
        boundary_index = None
        for index, probability in enumerate(probabilities):
            cumulative += probability
            if cumulative >= float(top_p):
                boundary_index = index
                break
        if boundary_index is not None and boundary_index + 1 < len(probabilities):
            top_p_gap = max(0.0, probabilities[boundary_index] - probabilities[boundary_index + 1])

    cdf_distance = None
    rng_draw = decode_boundary.get("rngDraw")
    selected_fast = int(receipt["selectedToken"]["fast"])
    if rng_draw is not None and probabilities:
        cumulative = 0.0
        selected_interval = None
        for index, candidate in enumerate(candidates):
            lower = cumulative
            cumulative += probabilities[index]
            if int(candidate["tokenId"]) == selected_fast:
                selected_interval = (lower, cumulative)
                break
        if selected_interval is not None:
            draw = float(rng_draw)
            lower, upper = selected_interval
            if lower <= draw <= upper:
                cdf_distance = min(draw - lower, upper - draw)
            else:
                cdf_distance = min(abs(draw - lower), abs(draw - upper))

    actual_selected_token_changed = (
        int(selected_token["fast"]) != int(selected_token["stable"])
        or int(selected_token["fast"]) != int(selected_token["reference"])
    )

    def metric_or_fallback(metric_name: str, fallback: Any) -> Any:
        value = boundary_metrics.get(metric_name)
        return fallback if value is None else value

    def live_selected_matches(lane: str) -> bool | None:
        if live_selected_token is None:
            return None
        return int(live_selected_token) == int(selected_token[lane])

    return {
        "postTemperatureTop1Margin": round(
            float(boundary_metrics.get("fastTop1Margin", top1_margin)),
            8,
        ),
        "topKBoundaryGap": (
            boundary_metrics.get("topKBoundaryGap")
            if boundary_metrics.get("topKBoundaryGap") is not None
            else (None if top_k_gap is None else round(top_k_gap, 8))
        ),
        "topPBoundaryGap": (
            boundary_metrics.get("topPBoundaryGap")
            if boundary_metrics.get("topPBoundaryGap") is not None
            else (None if top_p_gap is None else round(top_p_gap, 8))
        ),
        "cdfDistanceToDraw": (
            boundary_metrics.get("cdfDistanceToDraw")
            if boundary_metrics.get("cdfDistanceToDraw") is not None
                else (None if cdf_distance is None else round(max(0.0, cdf_distance), 8))
        ),
        "adjacentDecodePersistence": boundary_metrics.get("adjacentDecodePersistence"),
        "actualSelectedTokenChanged": bool(
            metric_or_fallback("actualSelectedTokenChanged", actual_selected_token_changed)
        ),
        "liveSelectedMatchesFast": metric_or_fallback(
            "liveSelectedMatchesFast",
            live_selected_matches("fast"),
        ),
        "liveSelectedMatchesStable": metric_or_fallback(
            "liveSelectedMatchesStable",
            live_selected_matches("stable"),
        ),
        "liveSelectedMatchesReference": metric_or_fallback(
            "liveSelectedMatchesReference",
            live_selected_matches("reference"),
        ),
    }


def build_row(receipt: dict[str, Any], *, receipt_path: str, overrides: dict[str, Any]) -> dict[str, Any]:
    selected_token_text = build_selected_token_text(receipt, overrides)
    token_forms = [
        form
        for form in (
            canonical_token_form(selected_token_text.get("fast")),
            canonical_token_form(selected_token_text.get("stable")),
            canonical_token_form(selected_token_text.get("reference")),
        )
        if form is not None
    ]
    semantic_priority_class = str(
        overrides.get("semanticPriorityClass") or infer_semantic_priority_class(token_forms)
    )
    actual_selected_token_changed = (
        int(receipt["selectedToken"]["fast"]) != int(receipt["selectedToken"]["stable"])
        or int(receipt["selectedToken"]["fast"]) != int(receipt["selectedToken"]["reference"])
    )
    metrics = build_probability_metrics(receipt)
    metrics.update(
        {
            "adjacentDecodePersistence": (
                overrides.get("adjacentDecodePersistence")
                if overrides.get("adjacentDecodePersistence") is not None
                else metrics.get("adjacentDecodePersistence")
            ),
            "actualSelectedTokenChanged": bool(
                metrics.get("actualSelectedTokenChanged", actual_selected_token_changed)
            ),
            "meaningfulToken": looks_like_meaningful_token(token_forms, semantic_priority_class),
            "withinPolicyStable": bool(overrides.get("withinPolicyStable", False)),
        }
    )

    decode_boundary = receipt.get("decodeBoundary") or {}
    first_divergence = receipt.get("firstDivergence") or {}
    first_upstream = (decode_boundary.get("upstreamLinks") or [None])[0]
    upstream_semantic_op = (
        first_divergence.get("semanticOpId")
        or (first_upstream or {}).get("semanticOpId")
    )
    row: dict[str, Any] = {
        "caseId": str(
            overrides.get("caseId")
            or f"{receipt['semanticStage']}::{receipt['semanticOpId']}::{infer_decode_step_index(receipt)}"
        ),
        "promptText": str(overrides.get("promptText") or receipt["semanticStage"]),
        "decodeStepIndex": int(overrides.get("decodeStepIndex", infer_decode_step_index(receipt))),
        "semanticPriorityClass": semantic_priority_class,
        "sourceArtifactPath": receipt_path,
        "receiptPath": receipt_path,
        "decodeConfig": {
            "temperature": decode_boundary.get("temperature"),
            "topK": decode_boundary.get("topK"),
            "topP": decode_boundary.get("topP"),
            "rngSeed": decode_boundary.get("rngSeed"),
            "randomDraw": decode_boundary.get("rngDraw"),
        },
        "selectedToken": {
            "fast": int(receipt["selectedToken"]["fast"]),
            "stable": int(receipt["selectedToken"]["stable"]),
            "reference": int(receipt["selectedToken"]["reference"]),
        },
        "metrics": metrics,
        "upstream": {
            "fastStableDisagreement": bool(
                receipt["trigger"]["checks"]["selectedTokenDisagreement"]
                or receipt["selectedToken"]["fast"] != receipt["selectedToken"]["stable"]
            ),
            "firstDivergenceSemanticOpId": upstream_semantic_op,
        },
        "suffixReplay": {
            "available": bool(((overrides.get("suffixReplay") or {}).get("available", False))),
            "divergent": bool(((overrides.get("suffixReplay") or {}).get("divergent", False))),
            "replayStepCount": (overrides.get("suffixReplay") or {}).get("replayStepCount"),
        },
    }
    if selected_token_text:
        row["selectedTokenText"] = selected_token_text
    return row


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    enrichment_path = Path(args.enrichment) if args.enrichment else None
    output_root = Path(args.output_root)
    timestamp = args.timestamp or timestamp_label()

    receipts = load_receipts(input_path)
    enrichments = load_enrichment(enrichment_path)
    receipt_path = relative_or_absolute(input_path)
    rows = [
        build_row(
            receipt,
            receipt_path=receipt_path,
            overrides=match_enrichment(enrichments, receipt_path=receipt_path, receipt=receipt),
        )
        for receipt in receipts
        if receipt_matches_decode_boundary(receipt)
    ]
    validate_rows(rows)
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "numeric_stability_decode.rows.jsonl"
    write_jsonl(output_path, rows)
    print(str(output_path))


if __name__ == "__main__":
    main()
