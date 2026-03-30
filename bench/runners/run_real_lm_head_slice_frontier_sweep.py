#!/usr/bin/env python3
"""Explore LM-head fragility using Pareto-frontier seed selection plus prompt mutation."""

from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.runners.determinism_search_helpers import relative_or_absolute
from bench.runners.determinism_search_helpers import timestamp_label
from bench.runners.run_determinism_probe import resolve_repo_path
from bench.runners.run_real_logit_hunt import ensure_fixture_shape as ensure_source_fixture_shape
from bench.runners.run_real_logit_hunt import load_json


DEFAULT_SEED_REPORT = (
    REPO_ROOT
    / "bench"
    / "out"
    / "apple-metal-real-lm-head-slice-hunt-search-sharp"
    / "20260330T171628Z"
    / "apple_metal_real_lm_head_slice_hunt_gemma270m_search_sharp.real-lm-head-slice-hunt.json"
)
DEFAULT_LM_HEAD_FIXTURE = (
    REPO_ROOT
    / "bench"
    / "fixtures"
    / "determinism"
    / "apple-metal-real-lm-head-slice-hunt.gemma270m.search-sharp.json"
)
DEFAULT_SOURCE_FIXTURE = (
    REPO_ROOT
    / "bench"
    / "fixtures"
    / "determinism"
    / "apple-metal-real-logit-hunt.gemma270m.prompt-search-sharp.json"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "apple-metal-real-lm-head-slice-frontier-sweep"


DEFAULT_LM_HEAD_RUNNER = REPO_ROOT / "bench" / "runners" / "run_real_lm_head_slice_hunt.py"

_SEGMENT_DELIMITERS = ".!?:;"
_OR_TOKEN_RE = re.compile(r"(?<!\w)or(?!\w)", re.IGNORECASE)


_QUESTION_PREFIXES = (
    "Question:",
    "Query:",
    "Prompt:",
    "Consider this:",
    "Prompt text:",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-report", default=str(DEFAULT_SEED_REPORT), help="Seed LM-head hunt report JSON.")
    parser.add_argument("--source-logit-fixture", default=str(DEFAULT_SOURCE_FIXTURE), help="Source real-logit hunt fixture JSON.")
    parser.add_argument("--lm-head-scenario-fixture", default=str(DEFAULT_LM_HEAD_FIXTURE), help="Base LM-head slice hunt fixture JSON.")
    parser.add_argument("--frontier-limit", type=int, default=12, help="Maximum number of frontier seeds to mutate.")
    parser.add_argument("--frontier-layers", type=int, default=12, help="How many Pareto layers to draw seeds from.")
    parser.add_argument("--frontier-gap-epsilon", type=float, default=0.02, help="Gap tolerance for approximate dominance in frontier layers.")
    parser.add_argument("--frontier-f16-epsilon", type=float, default=1.0, help="F16-bit-gap tolerance for approximate dominance.")
    parser.add_argument("--mutations-per-seed", type=int, default=3, help="Mutations generated per seed prompt.")
    parser.add_argument("--timestamp", default=None, help="UTC timestamp label for outputs.")
    parser.add_argument("--top-candidates", type=int, default=12, help="Top candidates to keep in final LM-head summary.")
    parser.add_argument("--runs", type=int, default=3, help="Repeat count for each frontier sweep prompt.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for frontier artifacts.")
    parser.add_argument("--max-source-prompts", type=int, default=40, help="Optional cap on prompt candidates used for mutation.")

    parser.add_argument(
        "--mutation-factor",
        type=float,
        default=1.0,
        help="Risk-weight multiplier for near-threshold frontier points (higher explores tighter-gap seeds).",
    )
    return parser.parse_args()


def f16_bits(value: float) -> int:
    return struct.unpack("<H", struct.pack("<e", float(value)))[0]


def f16(value: float) -> float:
    return struct.unpack("<e", struct.pack("<e", float(value)))[0]


def _prev_delimiter_position(text: str, index: int) -> int:
    max_pos = -1
    for delimiter in _SEGMENT_DELIMITERS:
        max_pos = max(max_pos, text.rfind(delimiter, 0, index))
    return max_pos


def _next_delimiter_position(text: str, index: int) -> int:
    next_pos = len(text)
    for delimiter in _SEGMENT_DELIMITERS:
        candidate = text.find(delimiter, index)
        if candidate != -1:
            next_pos = min(next_pos, candidate)
    return next_pos


def _is_option_phrase(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if "," in stripped or "\n" in stripped:
        return False
    if not any(char.isalpha() for char in stripped):
        return False
    words = stripped.split()
    return 1 <= len(words) <= 4


def parse_choice(prompt_text: str) -> dict[str, Any] | None:
    for match in _OR_TOKEN_RE.finditer(prompt_text):
        left_end = match.start()
        right_start = match.end()
        if left_end == 0 or right_start >= len(prompt_text):
            continue
        if not (prompt_text[left_end - 1].isspace() and prompt_text[right_start].isspace()):
            continue

        start = _prev_delimiter_position(prompt_text, left_end) + 1
        end = _next_delimiter_position(prompt_text, right_start)
        left = prompt_text[start:left_end].strip(" \t-")
        right = prompt_text[right_start:end].strip(" \t-")

        if not _is_option_phrase(left) or not _is_option_phrase(right):
            continue
        if left.lower() == right.lower():
            continue

        marker = ""
        marker_match = re.search(
            r"(?i)(answer with exactly one word|choose exactly one word):\s*$",
            prompt_text[:start],
        )
        if marker_match:
            marker = marker_match.group(1).strip().lower()

        while start < len(prompt_text) and prompt_text[start].isspace():
            start += 1

        return {
            "marker": marker,
            "left": left,
            "right": right,
            "start": start,
            "end": end,
            "tail": prompt_text[start:end],
        }

    return None


def parse_marker_choice(prompt_text: str) -> dict[str, Any] | None:
    # Kept for compatibility with existing report/debug tooling.
    return parse_choice(prompt_text)


def frontier_point_for_prompt(prompt_group: dict[str, Any]) -> dict[str, Any] | None:
    prefill = prompt_group["prefillStep"]
    top_candidates = prefill.get("topCandidates") or []
    if len(top_candidates) < 2 or prefill.get("top2Gap") is None:
        return None
    t0 = float(top_candidates[0]["logit"])
    t1 = float(top_candidates[1]["logit"])
    b0 = f16_bits(t0)
    b1 = f16_bits(t1)
    return {
        "promptId": prompt_group["promptId"],
        "promptIndex": int(prompt_group["promptIndex"]),
        "promptText": prompt_group["promptText"],
        "top2Gap": float(prefill["top2Gap"]),
        "top2Logits": (t0, t1),
        "top2F16": (f16(t0), f16(t1)),
        "f16BitsGap": abs(int(b0) - int(b1)),
        "f16Tie": b0 == b1,
        "sourceStable": bool(prompt_group.get("sourceStable", False)),
    }


def frontier_point_score(point: dict[str, Any]) -> float:
    gap = float(point["top2Gap"])
    f16_bits_gap = float(point["f16BitsGap"])

    # Lower is better: we prioritize narrow top2 gaps first,
    # then near-boundary f16 behavior.
    # f16 tie and 1-bit proximity are intentionally favored by
    # adding a strong negative score bonus.
    tie_bonus = 0.4 if f16_bits_gap <= 1 else 0.0
    if gap <= 0:
        gap = 1e-12
    return gap + f16_bits_gap * 1e-4 - tie_bonus * (1.0 / (gap + 1e-12))


def is_dominated(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    gap_epsilon: float,
    f16_bits_epsilon: float,
) -> bool:
    return (
        float(b["top2Gap"]) <= float(a["top2Gap"]) + gap_epsilon
        and float(b["f16BitsGap"]) <= float(a["f16BitsGap"]) + f16_bits_epsilon
        and (
            float(b["top2Gap"]) < float(a["top2Gap"]) - gap_epsilon
            or float(b["f16BitsGap"]) < float(a["f16BitsGap"]) - f16_bits_epsilon
        )
    )


def pareto_frontier(
    points: list[dict[str, Any]],
    *,
    gap_epsilon: float,
    f16_bits_epsilon: float,
) -> list[dict[str, Any]]:
    sorted_points = sorted(points, key=lambda p: (float(p["top2Gap"]), int(p["f16BitsGap"]), p["promptIndex"]))
    frontier: list[dict[str, Any]] = []
    for point in sorted_points:
        dominated = False
        for existing in frontier:
            if is_dominated(point, existing, gap_epsilon=gap_epsilon, f16_bits_epsilon=f16_bits_epsilon):
                dominated = True
                break
        if dominated:
            continue
        frontier = [
            existing
            for existing in frontier
            if not is_dominated(existing, point, gap_epsilon=gap_epsilon, f16_bits_epsilon=f16_bits_epsilon)
        ]
        frontier.append(point)
    frontier.sort(key=lambda p: (float(p["top2Gap"]), int(p["f16BitsGap"]), p["promptIndex"]))
    return frontier


def pareto_frontier_layers(
    points: list[dict[str, Any]],
    *,
    gap_epsilon: float,
    f16_bits_epsilon: float,
) -> list[list[dict[str, Any]]]:
    remaining = list(points)
    layers: list[list[dict[str, Any]]] = []
    while remaining:
        frontier = pareto_frontier(
            remaining,
            gap_epsilon=float(gap_epsilon),
            f16_bits_epsilon=float(f16_bits_epsilon),
        )
        if not frontier:
            break
        frontier_ids = {id(item) for item in frontier}
        layers.append(frontier)
        remaining = [point for point in remaining if id(point) not in frontier_ids]
    return layers


def mutation_variants(case: dict[str, Any]) -> list[dict[str, str]]:
    parsed = parse_marker_choice(case["promptText"])
    if not parsed:
        return []
    marker = parsed["marker"]
    left = parsed["left"]
    right = parsed["right"]
    tail = parsed["tail"]
    prompt = case["promptText"]
    start = parsed["start"]
    end = parsed["end"]

    marker_text = marker.strip() if marker else ""

    original = f"{left} or {right}"
    swapped = f"{right} or {left}"
    options = [
        original,
        swapped,
        f"{left.capitalize()} or {right.capitalize()}",
        f" {left} or {right}",
        f"{left}  or  {right}",
        f"{left} or  {right}",
        f"{left.title()} or {right.title()}",
    ]

    prefix = prompt[:start]
    suffix = prompt[end:]

    def replace_question_prefix(prefixes: tuple[str, ...]) -> str:
        suffix_lower = suffix.lower()
        marker = None
        for marker_candidate in (". question:", ". prompt:", ". query:"):
            if marker_candidate in suffix_lower:
                marker = marker_candidate
                break
        if marker is None:
            yield suffix
            return

        marker_start = suffix_lower.index(marker)
        marker_end = marker_start + len(marker)
        suffix_tail = suffix[marker_end:]
        for question_prefix in prefixes:
            yield suffix[:marker_start] + f". {question_prefix}" + suffix_tail

    question_variants = list(dict.fromkeys(replace_question_prefix(_QUESTION_PREFIXES)))

    # Keep only unique, non-empty mutations, capped downstream.
    prompts: list[dict[str, str]] = []
    mutated_seen: set[str] = set()
    for option_index, option in enumerate(options):
        if option == tail:
            continue
        mutated = f"{prompt[:start]}{option}{prompt[end:]}"
        if mutated in mutated_seen:
            continue
        mutated_seen.add(mutated)
        mutation_id = "swap" if option == swapped else f"mut{option_index:02d}"
        prompts.append(
            {
                "id_suffix": mutation_id,
                "text": mutated,
            }
        )
    for variant_index, variant_suffix in enumerate(question_variants):
        mutated = prefix + tail + variant_suffix
        if mutated in mutated_seen:
            continue
        mutated_seen.add(mutated)
        prompts.append({"id_suffix": f"question{variant_index:02d}", "text": mutated})

    # For non-markered prompts, add a structured framing variant that can expose parser behavior.
    if not marker_text:
        framed = f"Answer with exactly one word: {original}."
        mutated = f"{prompt[:start]}{framed}{prompt[end:]}"
        if mutated not in mutated_seen:
            mutated_seen.add(mutated)
            prompts.append({"id_suffix": "framed", "text": mutated})
    deduped: list[dict[str, str]] = []
    seen = {case["promptText"]}
    for row in prompts:
        text = row["text"]
        if text in seen:
            continue
        seen.add(text)
        deduped.append(row)
    return deduped


def build_mutated_logit_fixture(
    source_fixture_path: Path,
    *,
    prompt_candidates: list[dict[str, str]],
) -> tuple[dict[str, Any], Path, Path]:
    source_fixture = load_json(source_fixture_path)
    ensure_source_fixture_shape(source_fixture)
    source_fixture = dict(source_fixture)
    source_fixture["promptCandidates"] = prompt_candidates
    tmp_root = Path(tempfile.mkdtemp(prefix="doe-lm-head-fringe-"))
    tmp_root.mkdir(parents=True, exist_ok=True)
    source_path = tmp_root / "fringe.real-logit-hunt.prompts.json"
    source_path.write_text(json.dumps(source_fixture, indent=2) + "\n", encoding="utf-8")
    return source_fixture, source_path, tmp_root


def build_mutated_lm_fixture(
    lm_fixture_path: Path,
    *,
    source_fixture_path: Path,
    prompt_count: int,
) -> Path:
    fixture = load_json(lm_fixture_path)
    mutated = dict(fixture)
    mutated["sourceRealLogitFixturePath"] = str(source_fixture_path)
    path = source_fixture_path.parent / f"fringe-lm-head.{prompt_count:03d}.hunt.json"
    path.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
    return path


def run_frontier_sweep(
    *,
    fixture_path: Path,
    runs: int,
    top_candidates: int,
    output_root: Path,
    timestamp: str,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(DEFAULT_LM_HEAD_RUNNER),
            "--fixture",
            str(fixture_path),
            "--runs",
            str(runs),
            "--top-candidates",
            str(top_candidates),
            "--timestamp",
            timestamp,
            "--output-root",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "lm-head frontier run failed\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    payload = json.loads(completed.stdout.strip() or "{}")
    if not isinstance(payload, dict) or "reportPath" not in payload:
        raise RuntimeError("lm-head run returned no reportPath")
    report_path = resolve_repo_path(payload["reportPath"])
    report = load_json(report_path)
    return {"payload": payload, "report": report, "report_path": report_path}


def main() -> int:
    args = parse_args()
    seed_report = load_json(resolve_repo_path(args.seed_report))
    prompt_groups = seed_report.get("promptGroups") or []
    all_points: list[dict[str, Any]] = []
    for group in prompt_groups:
        if not group.get("sourceStable"):
            continue
        point = frontier_point_for_prompt(group)
        if point is not None:
            all_points.append(point)

    if not all_points:
        print(json.dumps({"status": "no-usable-prompt-groups", "count": len(prompt_groups)}, indent=2))
        return 0

    frontier_layers = pareto_frontier_layers(
        all_points,
        gap_epsilon=float(args.frontier_gap_epsilon),
        f16_bits_epsilon=float(args.frontier_f16_epsilon),
    )
    selected_frontier_points: list[dict[str, Any]] = []
    for layer_index, layer in enumerate(frontier_layers[: max(1, int(args.frontier_layers))]):
        for point in sorted(layer, key=frontier_point_score):
            if len(selected_frontier_points) >= args.frontier_limit:
                break
            selected_frontier_points.append({**point, "frontierLayer": layer_index})
        if len(selected_frontier_points) >= args.frontier_limit:
            break

    if not selected_frontier_points:
        print(json.dumps({"status": "no-frontier-selections", "count": len(all_points)}, indent=2))
        return 0

    if args.mutation_factor and args.mutation_factor > 1.0:
        for point in selected_frontier_points:
            if float(point["top2Gap"]) < 0.05:
                repeats = max(1, int(args.mutations_per_seed * args.mutation_factor))
            elif float(point["top2Gap"]) < 0.2:
                repeats = max(1, int(args.mutations_per_seed * args.mutation_factor * 0.75))
            else:
                repeats = max(1, int(args.mutations_per_seed * 0.5))
            point["mutationBudget"] = repeats
    else:
        for point in selected_frontier_points:
            point["mutationBudget"] = args.mutations_per_seed

    frontier = selected_frontier_points
    seed_points = selected_frontier_points
    frontier_report = [
        {
            "promptId": p["promptId"],
            "promptIndex": p["promptIndex"],
            "top2Gap": p["top2Gap"],
            "f16Gap": p["f16BitsGap"],
            "f16BitsGap": p["f16BitsGap"],
            "f16Tie": p["f16Tie"],
            "frontierLayer": p["frontierLayer"],
        }
        for p in seed_points
    ]

    prompt_candidates: list[dict[str, str]] = []
    metadata_by_prompt_id: dict[str, dict[str, Any]] = {}
    for seed in seed_points:
        budget = int(seed.get("mutationBudget", args.mutations_per_seed))
        for mutation in mutation_variants(seed)[:budget]:
            prompt_id = f"{seed['promptId']}--{mutation['id_suffix']}"
            if prompt_id in metadata_by_prompt_id:
                continue
            prompt_candidates.append({"id": prompt_id, "text": mutation["text"]})
            metadata_by_prompt_id[prompt_id] = {
                "seedPromptId": seed["promptId"],
                "seedPromptIndex": seed["promptIndex"],
                "mutation": mutation["id_suffix"],
                "frontierTop2Gap": float(seed["top2Gap"]),
                "frontierF16BitsGap": int(seed["f16BitsGap"]),
                "frontierLayer": int(seed.get("frontierLayer", 0)),
            }

    if args.max_source_prompts and len(prompt_candidates) > args.max_source_prompts:
        prompt_candidates = prompt_candidates[:args.max_source_prompts]

    if not prompt_candidates:
        print(json.dumps({"status": "no-mutations-produced-candidates", "frontierSize": len(seed_points)}))
        return 0

    source_fixture_path = resolve_repo_path(args.source_logit_fixture)
    lm_fixture = resolve_repo_path(args.lm_head_scenario_fixture)
    _, mutated_source_path, _ = build_mutated_logit_fixture(
        source_fixture_path,
        prompt_candidates=prompt_candidates,
    )
    lm_head_fixture_path = build_mutated_lm_fixture(
        lm_fixture,
        source_fixture_path=mutated_source_path,
        prompt_count=len(prompt_candidates),
    )

    run_stamp = timestamp_label(args.timestamp)
    output_root = resolve_repo_path(args.output_root) / run_stamp
    output_root.mkdir(parents=True, exist_ok=True)
    sweep_result = run_frontier_sweep(
        fixture_path=lm_head_fixture_path,
        runs=args.runs,
        top_candidates=args.top_candidates,
        output_root=output_root,
        timestamp=run_stamp,
    )
    sweep_report = sweep_result["report"]
    output = {
        "status": "ok",
        "frontierSize": len(frontier),
        "seedSelection": frontier_report[: args.frontier_limit],
        "generatedPromptCount": len(prompt_candidates),
        "reportPath": relative_or_absolute(sweep_result["report_path"]),
        "report": sweep_report["summary"],
        "mutations": metadata_by_prompt_id,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
