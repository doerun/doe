#!/usr/bin/env python3
"""Multi-step autoregressive cascade divergence tracker.

Simulates N-step autoregressive decode, tracking at which step the f16
accumulation path first diverges from f32.  Tests whether a single
precision flip compounds into a different output sequence across
multiple decode steps.

Since no full model is available, the cascade is simulated:
  - Use the existing weight matrix and hidden state from fixture/harvest data.
  - At each step, compute f32 and f16 logits over all candidate rows,
    pick argmax for each path independently.
  - Perturb the hidden state by mixing in the selected token's weight row
    (proxy for its embedding).
  - Track whether/when the two paths diverge and whether they reconverge.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.runners.run_real_lm_head_slice_hunt import (
    TensorRowReader,
    decode_f32_buffer,
    f32,
    forward_dot_f16accum,
    forward_dot_f32,
    load_json,
    resolve_repo_path,
    resolve_tensor_name,
    scalar_argmax,
)

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "bench" / "out" / "cascade-divergence"
MAX_CASCADE_STEPS = 32
HIDDEN_STATE_MIX_ALPHA = 0.15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--harvest", required=True, nargs="+",
        help="Harvest JSON file(s) with prefill embeddings and top candidates.",
    )
    parser.add_argument("--model-root", required=True, help="Model artifact directory.")
    parser.add_argument(
        "--model-id", default="gemma-3-270m-it-q4k-ehf16-af32",
        help="Model ID for manifest lookup.",
    )
    parser.add_argument(
        "--steps", type=int, default=MAX_CASCADE_STEPS,
        help="Maximum number of autoregressive cascade steps.",
    )
    parser.add_argument(
        "--top-k", type=int, default=64,
        help="Number of top candidates to use as the vocabulary slice.",
    )
    parser.add_argument(
        "--mix-alpha", type=float, default=HIDDEN_STATE_MIX_ALPHA,
        help="Mixing coefficient for hidden state perturbation.",
    )
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--timestamp", default=None)
    parser.add_argument(
        "--answer-set-registry", default=None,
        help="Answer set registry JSON for focused candidate pairs.",
    )
    return parser.parse_args()


def timestamp_label(raw: str | None) -> str:
    if raw:
        return raw
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def collect_prompt_data(harvest_paths: list[str], top_k: int) -> list[dict[str, Any]]:
    """Load harvest files, deduplicate by prompt ID, keep prompts with embeddings."""
    prompts_by_id: dict[str, dict[str, Any]] = {}
    for path in harvest_paths:
        harvest = load_json(Path(path))
        for run in harvest.get("runs", []):
            for p in run.get("promptResults", []):
                if p["status"] != "ok":
                    continue
                pid = p.get("id", f"prompt-{p['promptIndex']:03d}")
                if pid in prompts_by_id:
                    continue
                emb = p.get("prefillEmbedding", {})
                if not emb.get("embeddingArtifactPath"):
                    continue
                candidates = p["steps"][0]["topCandidates"][:top_k]
                if len(candidates) < 2:
                    continue
                prompts_by_id[pid] = {
                    "promptId": pid,
                    "promptIndex": p["promptIndex"],
                    "promptText": p["text"],
                    "embeddingPath": emb["embeddingArtifactPath"],
                    "embeddingSha256": emb["embeddingSha256"],
                    "topCandidates": candidates,
                }
    return sorted(prompts_by_id.values(), key=lambda x: x["promptIndex"])


def perturb_hidden_state(
    hidden: list[float],
    token_weight_row: list[float],
    alpha: float,
) -> list[float]:
    """Mix the selected token's weight row into the hidden state.

    Uses a simple linear interpolation as a proxy for what a real model
    would do when feeding the selected token's embedding back as input.
    The weight row serves as a proxy for the token embedding (many small
    models tie embeddings to the output projection).
    """
    if len(hidden) != len(token_weight_row):
        raise ValueError(
            f"hidden state dimension {len(hidden)} != weight row dimension {len(token_weight_row)}"
        )
    return [
        f32((1.0 - alpha) * h + alpha * w)
        for h, w in zip(hidden, token_weight_row)
    ]


def compute_logit_gap(logits: list[float], selected_index: int) -> float:
    """Compute the gap between the selected (max) logit and the runner-up."""
    if len(logits) < 2:
        return float("inf")
    sorted_logits = sorted(logits, reverse=True)
    return sorted_logits[0] - sorted_logits[1]


def run_cascade_for_prompt(
    *,
    hidden_state: list[float],
    token_ids: list[int],
    token_texts: list[str],
    rows_by_token: dict[int, list[float]],
    max_steps: int,
    mix_alpha: float,
) -> dict[str, Any]:
    """Run the multi-step cascade for one prompt, tracking f32 vs f16 divergence."""

    f32_hidden = list(hidden_state)
    f16_hidden = list(hidden_state)

    steps: list[dict[str, Any]] = []
    first_divergence_step: int | None = None
    diverged_steps = 0
    reconverged_steps = 0
    longest_divergence_streak = 0
    current_divergence_streak = 0

    for step_index in range(max_steps):
        f32_logits = [
            forward_dot_f32(f32_hidden, rows_by_token[tid])
            for tid in token_ids
        ]
        f16_logits = [
            forward_dot_f16accum(f16_hidden, rows_by_token[tid])
            for tid in token_ids
        ]

        f32_argmax = scalar_argmax(f32_logits)
        f16_argmax = scalar_argmax(f16_logits)

        f32_token_id = token_ids[f32_argmax]
        f16_token_id = token_ids[f16_argmax]
        f32_token_text = token_texts[f32_argmax]
        f16_token_text = token_texts[f16_argmax]

        agree = f32_token_id == f16_token_id

        f32_gap = compute_logit_gap(f32_logits, f32_argmax)
        f16_gap = compute_logit_gap(f16_logits, f16_argmax)

        if not agree:
            diverged_steps += 1
            current_divergence_streak += 1
            longest_divergence_streak = max(
                longest_divergence_streak, current_divergence_streak
            )
            if first_divergence_step is None:
                first_divergence_step = step_index
        else:
            if current_divergence_streak > 0:
                reconverged_steps += 1
            current_divergence_streak = 0

        step_record = {
            "step": step_index,
            "f32TokenId": f32_token_id,
            "f32TokenText": f32_token_text,
            "f32LogitGap": round(f32_gap, 8),
            "f32TopLogit": round(f32_logits[f32_argmax], 8),
            "f16TokenId": f16_token_id,
            "f16TokenText": f16_token_text,
            "f16LogitGap": round(f16_gap, 8),
            "f16TopLogit": round(f16_logits[f16_argmax], 8),
            "agree": agree,
        }
        steps.append(step_record)

        # Feed each path's selected token back independently
        f32_hidden = perturb_hidden_state(
            f32_hidden, rows_by_token[f32_token_id], mix_alpha
        )
        f16_hidden = perturb_hidden_state(
            f16_hidden, rows_by_token[f16_token_id], mix_alpha
        )

    permanent_divergence = (
        first_divergence_step is not None and reconverged_steps == 0
    )

    return {
        "totalSteps": max_steps,
        "firstDivergenceStep": first_divergence_step,
        "divergedStepCount": diverged_steps,
        "reconvergedCount": reconverged_steps,
        "longestDivergenceStreak": longest_divergence_streak,
        "permanentDivergence": permanent_divergence,
        "steps": steps,
    }


def main() -> int:
    args = parse_args()
    t0 = time.time()

    prompts = collect_prompt_data(args.harvest, args.top_k)
    if not prompts:
        print("No usable prompts found in harvest files.", file=sys.stderr)
        return 1
    print(
        f"Loaded {len(prompts)} usable prompts from "
        f"{len(args.harvest)} harvest(s)",
        file=sys.stderr,
    )

    model_root = resolve_repo_path(args.model_root)
    manifest = load_json(model_root / "manifest.json")
    tensor_name = resolve_tensor_name(manifest)

    # Collect all token IDs needed across all prompts
    all_token_ids: set[int] = set()
    for prompt in prompts:
        for c in prompt["topCandidates"]:
            all_token_ids.add(int(c["token"]))

    print(
        f"Reading {len(all_token_ids)} weight rows from {tensor_name}...",
        file=sys.stderr,
    )
    row_reader = TensorRowReader(model_root, manifest, tensor_name)
    try:
        rows_by_token = row_reader.read_rows(sorted(all_token_ids))
    finally:
        row_reader.close()
    print(
        f"Weight rows loaded in {time.time() - t0:.1f}s",
        file=sys.stderr,
    )

    stamp = timestamp_label(args.timestamp)
    output_dir = resolve_repo_path(args.output_root) / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt_results: list[dict[str, Any]] = []
    total_diverged = 0
    total_permanent = 0

    for pi, prompt in enumerate(prompts):
        t1 = time.time()
        hidden = decode_f32_buffer(resolve_repo_path(prompt["embeddingPath"]))
        token_ids = [int(c["token"]) for c in prompt["topCandidates"]]
        token_texts = [
            c.get("tokenText", f"?{c['token']}") for c in prompt["topCandidates"]
        ]

        cascade = run_cascade_for_prompt(
            hidden_state=hidden,
            token_ids=token_ids,
            token_texts=token_texts,
            rows_by_token=rows_by_token,
            max_steps=args.steps,
            mix_alpha=args.mix_alpha,
        )

        prompt_entry = {
            "promptId": prompt["promptId"],
            "promptIndex": prompt["promptIndex"],
            "promptText": prompt["promptText"][:200],
            "embeddingSha256": prompt["embeddingSha256"],
            "candidateCount": len(token_ids),
            "cascade": cascade,
        }
        prompt_results.append(prompt_entry)

        if cascade["firstDivergenceStep"] is not None:
            total_diverged += 1
        if cascade["permanentDivergence"]:
            total_permanent += 1

        elapsed = time.time() - t1
        div_step = cascade["firstDivergenceStep"]
        status = (
            f"diverges@step{div_step}"
            if div_step is not None
            else "no divergence"
        )
        perm = " PERMANENT" if cascade["permanentDivergence"] else ""
        if div_step is not None or (pi + 1) % 10 == 0:
            print(
                f"  [{pi+1}/{len(prompts)}] {prompt['promptId']}: "
                f"{status}{perm} ({elapsed:.1f}s)",
                file=sys.stderr,
            )

    total_time = time.time() - t0

    # Build summary statistics
    divergence_steps = [
        r["cascade"]["firstDivergenceStep"]
        for r in prompt_results
        if r["cascade"]["firstDivergenceStep"] is not None
    ]
    divergence_step_histogram: dict[int, int] = {}
    for step in divergence_steps:
        divergence_step_histogram[step] = divergence_step_histogram.get(step, 0) + 1

    streak_lengths = [
        r["cascade"]["longestDivergenceStreak"]
        for r in prompt_results
        if r["cascade"]["longestDivergenceStreak"] > 0
    ]

    report = {
        "schemaVersion": 1,
        "source": "doe-cascade-divergence-tracker",
        "timestamp": stamp,
        "parameters": {
            "maxSteps": args.steps,
            "topK": args.top_k,
            "mixAlpha": args.mix_alpha,
            "modelId": args.model_id,
            "tensorName": tensor_name,
            "harvestPaths": args.harvest,
        },
        "summary": {
            "promptCount": len(prompt_results),
            "promptsWithDivergence": total_diverged,
            "promptsWithPermanentDivergence": total_permanent,
            "divergenceRate": round(
                total_diverged / max(len(prompt_results), 1), 4
            ),
            "permanentDivergenceRate": round(
                total_permanent / max(len(prompt_results), 1), 4
            ),
            "medianFirstDivergenceStep": (
                sorted(divergence_steps)[len(divergence_steps) // 2]
                if divergence_steps
                else None
            ),
            "minFirstDivergenceStep": (
                min(divergence_steps) if divergence_steps else None
            ),
            "maxFirstDivergenceStep": (
                max(divergence_steps) if divergence_steps else None
            ),
            "divergenceStepHistogram": dict(
                sorted(divergence_step_histogram.items())
            ),
            "medianLongestStreak": (
                sorted(streak_lengths)[len(streak_lengths) // 2]
                if streak_lengths
                else None
            ),
            "maxLongestStreak": (
                max(streak_lengths) if streak_lengths else None
            ),
        },
        "prompts": prompt_results,
        "totalTimeSeconds": round(total_time, 1),
    }

    report_path = output_dir / "cascade-divergence-report.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n{'=' * 72}", file=sys.stderr)
    print(
        f"Cascade divergence tracker complete: "
        f"{len(prompt_results)} prompts, {args.steps} steps each",
        file=sys.stderr,
    )
    print(
        f"  Prompts with divergence: {total_diverged}/{len(prompt_results)} "
        f"({report['summary']['divergenceRate'] * 100:.1f}%)",
        file=sys.stderr,
    )
    print(
        f"  Permanent divergence:    {total_permanent}/{len(prompt_results)} "
        f"({report['summary']['permanentDivergenceRate'] * 100:.1f}%)",
        file=sys.stderr,
    )
    if divergence_steps:
        print(
            f"  First divergence step:   "
            f"min={min(divergence_steps)}, "
            f"median={sorted(divergence_steps)[len(divergence_steps) // 2]}, "
            f"max={max(divergence_steps)}",
            file=sys.stderr,
        )
    if streak_lengths:
        print(
            f"  Longest streak:          "
            f"median={sorted(streak_lengths)[len(streak_lengths) // 2]}, "
            f"max={max(streak_lengths)}",
            file=sys.stderr,
        )
    print(f"  Total time:              {total_time:.1f}s", file=sys.stderr)
    print(f"  Report:                  {report_path}", file=sys.stderr)

    # stdout: report path for pipeline chaining
    print(str(report_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
