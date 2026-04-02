#!/usr/bin/env python3
"""Simulate sampled decode sensitivity from persisted greedy logits.

Takes Layer 2 real-logit-hunt output (with --persist-logits), applies softmax
at varying temperatures with top-k filtering, and computes the probability that
sampling would select a different token between repeated runs — given only the
observed logit drift between repeats.

No GPU needed. Pure offline analysis.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--harvest",
        required=True,
        nargs="+",
        help="Real-logit-hunt output JSON file(s) (the .real-logit-hunt.json files)",
    )
    parser.add_argument(
        "--temperatures",
        type=float,
        nargs="+",
        default=[0.0, 0.3, 0.5, 0.7, 1.0, 1.5],
        help="Temperatures to simulate (0.0 = greedy)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Top-k filter applied after temperature scaling (default: 4)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: stdout)",
    )
    return parser.parse_args()


def softmax_topk(logits: list[float], temperature: float, top_k: int) -> list[tuple[int, float]]:
    """Apply temperature scaling, top-k filter, then softmax. Returns [(token, prob), ...]."""
    if temperature <= 0:
        # Greedy: return 1.0 for the argmax
        max_idx = max(range(len(logits)), key=lambda i: logits[i])
        return [(max_idx, 1.0)]

    # Sort by logit descending, take top-k
    indexed = sorted(enumerate(logits), key=lambda x: -x[1])[:top_k]

    # Temperature-scale
    scaled = [(idx, logit / temperature) for idx, logit in indexed]

    # Softmax (numerically stable)
    max_val = max(v for _, v in scaled)
    exps = [(idx, math.exp(v - max_val)) for idx, v in scaled]
    total = sum(e for _, e in exps)
    return [(idx, e / total) for idx, e in exps]


def greedy_token(candidates: list[dict[str, Any]]) -> int:
    """Extract greedy token from top candidates list."""
    return max(candidates, key=lambda c: c["logit"])["token"]


def candidates_to_logits(candidates: list[dict[str, Any]]) -> list[float]:
    """Convert topCandidates list to a simple [logit, ...] list preserving token indices."""
    return [(c["token"], c["logit"]) for c in candidates]


def analyze_step(
    step_data_by_repeat: list[dict[str, Any]],
    temperatures: list[float],
    top_k: int,
) -> dict[str, Any]:
    """Analyze a single decode step across repeats.

    For each temperature, compute:
    - Whether the greedy token flips between repeats
    - The dominant sampled token and its probability under each repeat
    - Whether sampling would produce different tokens across repeats
    """
    n_repeats = len(step_data_by_repeat)
    if n_repeats < 2:
        return {"skipped": True, "reason": "fewer than 2 repeats"}

    # Extract top candidates per repeat
    candidates_per_repeat = []
    for step in step_data_by_repeat:
        candidates_per_repeat.append(step.get("topCandidates", []))

    result: dict[str, Any] = {"repeatCount": n_repeats}
    temp_results = []

    for temp in temperatures:
        # For each repeat, compute the sampling distribution
        distributions = []
        for candidates in candidates_per_repeat:
            pairs = [(c["token"], c["logit"]) for c in candidates]
            if not pairs:
                continue
            tokens = [t for t, _ in pairs]
            logits = [l for _, l in pairs]
            dist = softmax_topk(logits, temp, min(top_k, len(logits)))
            # Map back to token IDs
            token_probs = {}
            for i, (idx, prob) in enumerate(dist):
                token_id = tokens[idx] if idx < len(tokens) else idx
                token_probs[token_id] = prob
            distributions.append(token_probs)

        if len(distributions) < 2:
            temp_results.append({"temperature": temp, "skipped": True})
            continue

        # Find the most-probable token in each repeat
        top_tokens = [max(d, key=d.get) for d in distributions]
        top_probs = [d[t] for d, t in zip(distributions, top_tokens)]

        # Do all repeats agree on the top token?
        unique_tops = set(top_tokens)
        token_flip = len(unique_tops) > 1

        # Compute P(disagreement) = 1 - P(all repeats pick the same token)
        # For each candidate token, P(all pick it) = product of P(pick it | repeat_i)
        all_tokens = set()
        for d in distributions:
            all_tokens.update(d.keys())

        p_agreement = 0.0
        for token in all_tokens:
            p_all_pick = 1.0
            for d in distributions:
                p_all_pick *= d.get(token, 0.0)
            p_agreement += p_all_pick

        p_disagreement = 1.0 - p_agreement

        # Dominant token across repeats (mode)
        token_counts = collections.Counter(top_tokens)
        dominant_token, dominant_count = token_counts.most_common(1)[0]

        temp_results.append({
            "temperature": temp,
            "topTokenPerRepeat": top_tokens,
            "topProbPerRepeat": [round(p, 6) for p in top_probs],
            "tokenFlip": token_flip,
            "uniqueTopTokens": len(unique_tops),
            "pDisagreement": round(p_disagreement, 6),
            "dominantToken": dominant_token,
            "dominantRate": dominant_count / n_repeats,
        })

    result["temperatures"] = temp_results
    return result


def load_harvest(path: str) -> dict[str, Any]:
    """Load a real-logit-hunt JSON, extract the harvest portion."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("harvest", data)


def main() -> None:
    args = parse_args()

    # Collect all runs across harvest files
    # Group by (promptId, stepIndex) -> list of step data across repeats
    steps_by_key: dict[tuple[str, int], list[dict[str, Any]]] = collections.defaultdict(list)
    prompt_texts: dict[str, str] = {}

    for harvest_path in args.harvest:
        harvest = load_harvest(harvest_path)
        for run in harvest.get("runs", []):
            for prompt_result in run.get("promptResults", []):
                if prompt_result.get("status") != "ok":
                    continue
                pid = prompt_result.get("id", f"prompt-{prompt_result.get('promptIndex', 0):03d}")
                prompt_texts.setdefault(pid, prompt_result.get("text", ""))
                for step in prompt_result.get("steps", []):
                    step_idx = step.get("stepIndex", 0)
                    steps_by_key[(pid, step_idx)].append(step)

    # Analyze each (prompt, step) pair
    prompt_ids = sorted(set(pid for pid, _ in steps_by_key))
    step_indices = sorted(set(si for _, si in steps_by_key))

    per_prompt_results = []
    for pid in prompt_ids:
        step_results = []
        for si in step_indices:
            key = (pid, si)
            if key not in steps_by_key:
                continue
            analysis = analyze_step(steps_by_key[key], args.temperatures, args.top_k)
            analysis["stepIndex"] = si
            step_results.append(analysis)
        per_prompt_results.append({
            "promptId": pid,
            "promptText": prompt_texts.get(pid, ""),
            "steps": step_results,
        })

    # Aggregate: for each temperature, compute flip rates across all prompts × steps
    summary_by_temp: dict[float, dict[str, Any]] = {}
    for temp in args.temperatures:
        total_steps = 0
        flip_count = 0
        total_p_disagreement = 0.0
        flip_by_step: dict[int, int] = collections.defaultdict(int)
        total_by_step: dict[int, int] = collections.defaultdict(int)

        for pr in per_prompt_results:
            for step in pr["steps"]:
                for tr in step.get("temperatures", []):
                    if tr.get("skipped") or abs(tr["temperature"] - temp) > 1e-9:
                        continue
                    si = step["stepIndex"]
                    total_steps += 1
                    total_by_step[si] += 1
                    total_p_disagreement += tr["pDisagreement"]
                    if tr["tokenFlip"]:
                        flip_count += 1
                        flip_by_step[si] += 1

        summary_by_temp[temp] = {
            "temperature": temp,
            "topK": args.top_k,
            "totalSteps": total_steps,
            "flipCount": flip_count,
            "flipRate": round(flip_count / max(total_steps, 1), 6),
            "meanPDisagreement": round(total_p_disagreement / max(total_steps, 1), 6),
            "flipRateByStep": {
                si: round(flip_by_step.get(si, 0) / max(total_by_step.get(si, 1), 1), 6)
                for si in sorted(total_by_step)
            },
        }

    report = {
        "schemaVersion": 1,
        "source": "simulate-sampled-sensitivity",
        "temperatures": args.temperatures,
        "topK": args.top_k,
        "promptCount": len(prompt_ids),
        "stepCount": len(step_indices),
        "summary": [summary_by_temp[t] for t in args.temperatures],
        "prompts": per_prompt_results,
    }

    output_text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Written: {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output_text)


if __name__ == "__main__":
    main()
