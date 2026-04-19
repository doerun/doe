#!/usr/bin/env python3
"""Lookahead-sensitivity sweep for the dry-run streaming executor.

Regenerates the E2B stream-graph + stream-execution-plan + dry-run
trace for each `lookaheadLayers` value in [1, 4], then diffs each
result against the lookahead=2 baseline. Emits a consolidated
sensitivity artifact that captures how ring-buffer occupancy + SRAM
fit tradeoff changes with prefetch depth.

Confirms the expected model: ringBufferOccupancyLayers ==
lookaheadLayers + 1, and ringBufferOccupancyBytes scales linearly.
All other per-PE / aggregate fields should stay constant.

Why this matters: before the real streaming executor lands, this
sweep answers "what happens if we set lookahead to 3 instead of 2?"
without any runtime experiment. Once the executor is up, the same
sweep's predicted shape is what observed traces should match.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--execution-manifest",
        default="runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json",
    )
    p.add_argument(
        "--memory-plan",
        default="bench/out/e2b-full-graph/memory-plan.json",
    )
    p.add_argument(
        "--model-receipt",
        default="bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    )
    p.add_argument(
        "--work-dir",
        default="bench/out/lookahead-sensitivity",
    )
    p.add_argument(
        "--baseline-lookahead",
        type=int,
        default=2,
    )
    p.add_argument(
        "--lookahead-range",
        default="1,2,3,4",
    )
    p.add_argument(
        "--out-json",
        default="bench/out/lookahead-sensitivity/e2b-lookahead-sensitivity.json",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def main() -> int:
    args = parse_args()
    work_dir = resolve(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    lookaheads = [int(x) for x in args.lookahead_range.split(",") if x.strip()]
    traces_by_lookahead: dict[int, str] = {}

    # Per-lookahead: regenerate stream-graph, execution-plan, dry-run trace.
    for la in lookaheads:
        tag = f"la{la}"
        graph_path = work_dir / f"stream-graph.{tag}.json"
        plan_path = work_dir / f"exec-plan.{tag}.json"
        trace_path = work_dir / f"dry-run-trace.{tag}.json"

        run([
            sys.executable, str(REPO_ROOT / "bench/tools/build_stream_graph.py"),
            "--execution-manifest", str(resolve(args.execution_manifest)),
            "--memory-plan", str(resolve(args.memory_plan)),
            "--lookahead-layers", str(la),
            "--out-json", str(graph_path),
        ])
        run([
            sys.executable, str(REPO_ROOT / "bench/tools/validate_stream_graph.py"),
            "--stream-graph", str(graph_path),
            "--out-json", str(plan_path),
        ])
        run([
            sys.executable, str(REPO_ROOT / "bench/tools/dry_run_streaming_executor.py"),
            "--execution-plan", str(plan_path),
            "--model-receipt", str(resolve(args.model_receipt)),
            "--out-json", str(trace_path),
        ])
        traces_by_lookahead[la] = str(trace_path)

    # Diff every non-baseline trace against the baseline.
    baseline_trace = traces_by_lookahead[args.baseline_lookahead]
    diffs = []
    for la, trace_path in traces_by_lookahead.items():
        if la == args.baseline_lookahead:
            continue
        diff_path = work_dir / f"diff-la{args.baseline_lookahead}-vs-la{la}.json"
        run([
            sys.executable, str(REPO_ROOT / "bench/tools/diff_dry_run_traces.py"),
            "--left", baseline_trace,
            "--right", trace_path,
            "--label-left", f"la{args.baseline_lookahead}",
            "--label-right", f"la{la}",
            "--out-json", str(diff_path),
        ])
        diffs.append({"lookahead": la, "diffPath": rel(diff_path)})

    # Collect sensitivity summary: pull the key fields from each dry-run.
    rows = []
    for la in lookaheads:
        trace = json.loads(resolve(traces_by_lookahead[la]).read_text(encoding="utf-8"))
        pp = trace["perPe"]
        rows.append({
            "lookaheadLayers": la,
            "ringBufferOccupancyLayers": pp["ringBufferOccupancyLayers"],
            "ringBufferOccupancyBytes": pp["ringBufferOccupancyBytes"],
            "fitsInPerPeSramBudget": pp["fitsInPerPeSramBudget"],
            "perLayerBytes": pp["perLayerBytes"],
            "setupBytes": pp["setupBytes"],
            "totalBytesTransferredPerPe": trace["aggregate"]["totalBytesTransferredPerPe"],
        })

    artifact = {
        "schemaVersion": 1,
        "artifactKind": "doe_lookahead_sensitivity",
        "target": "wse3",
        "modelId": json.loads(resolve(args.model_receipt).read_text(encoding="utf-8"))
            .get("modelId", ""),
        "baselineLookahead": args.baseline_lookahead,
        "lookaheadsTested": lookaheads,
        "rows": rows,
        "diffs": diffs,
    }

    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    fit_count = sum(1 for r in rows if r["fitsInPerPeSramBudget"])
    print(
        f"lookahead sensitivity: tested {lookaheads}, "
        f"fit: {fit_count}/{len(lookaheads)}, → {rel(out_path)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
