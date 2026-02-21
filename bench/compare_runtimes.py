#!/usr/bin/env python3
"""
Side-by-side runtime benchmark runner for non-placeholder replacement.

Runs two command invocations over the same workload command line and reports
wall-time deltas plus metadata summary if provided.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left-label", required=True)
    parser.add_argument("--left-cmd", required=True)
    parser.add_argument("--right-label", required=True)
    parser.add_argument("--right-cmd", required=True)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--left-meta", default="")
    parser.add_argument("--right-meta", default="")
    parser.add_argument("--out", default="fawn/bench/out/runtime-comparison.json")
    return parser.parse_args()


def run_once(command: str) -> float:
    start = time.perf_counter()
    proc = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {command}")
    return elapsed_ms


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int((len(sorted_values) - 1) * p)
    return sorted_values[idx]


def percent_delta(left: float, right: float) -> float:
    if right <= 0:
        return 0.0
    return ((right - left) / right) * 100.0


def read_meta(path: str) -> dict[str, object]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def summarize(name: str, command: str, iterations: int, warmup: int, meta_path: str) -> dict[str, object]:
    for _ in range(max(warmup, 0)):
        run_once(command)
    timings = [run_once(command) for _ in range(max(iterations, 1))]
    return {
        "runtime": name,
        "command": command,
        "iterations": iterations,
        "timingsMs": timings,
        "p5Ms": percentile(timings, 0.05),
        "p50Ms": percentile(timings, 0.5),
        "p95Ms": percentile(timings, 0.95),
        "p99Ms": percentile(timings, 0.99),
        "meanMs": statistics.fmean(timings),
        "medianMs": statistics.median(timings),
        "minMs": min(timings),
        "maxMs": max(timings),
        "meta": read_meta(meta_path),
    }


def main() -> int:
    args = parse_args()
    left = summarize(args.left_label, args.left_cmd, args.iterations, args.warmup, args.left_meta)
    right = summarize(args.right_label, args.right_cmd, args.iterations, args.warmup, args.right_meta)

    left_p5 = left["p5Ms"] if isinstance(left["p5Ms"], float) else 0.0
    right_p5 = right["p5Ms"] if isinstance(right["p5Ms"], float) else 0.0
    left_p50 = left["p50Ms"] if isinstance(left["p50Ms"], float) else 0.0
    right_p50 = right["p50Ms"] if isinstance(right["p50Ms"], float) else 0.0
    left_p95 = left["p95Ms"] if isinstance(left["p95Ms"], float) else 0.0
    right_p95 = right["p95Ms"] if isinstance(right["p95Ms"], float) else 0.0
    left_p99 = left["p99Ms"] if isinstance(left["p99Ms"], float) else 0.0
    right_p99 = right["p99Ms"] if isinstance(right["p99Ms"], float) else 0.0
    left_mean = left["meanMs"] if isinstance(left["meanMs"], float) else 0.0
    right_mean = right["meanMs"] if isinstance(right["meanMs"], float) else 0.0

    report = {
        "schemaVersion": 3,
        "left": left,
        "right": right,
        "deltaPercentConvention": {
            "baseline": "right",
            "formula": "((rightMs - leftMs) / rightMs) * 100",
            "positive": "left faster",
            "negative": "left slower",
            "zero": "parity",
        },
        "delta": {
            "p5Percent": percent_delta(left_p5, right_p5),
            "p50Percent": percent_delta(left_p50, right_p50),
            "p95Percent": percent_delta(left_p95, right_p95),
            "p99Percent": percent_delta(left_p99, right_p99),
            "meanPercent": percent_delta(left_mean, right_mean),
            "p50LeftMs": left_p50,
            "p50RightMs": right_p50,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(out),
                "p5DeltaPercent": report["delta"]["p5Percent"],
                "p50DeltaPercent": report["delta"]["p50Percent"],
                "p95DeltaPercent": report["delta"]["p95Percent"],
                "p99DeltaPercent": report["delta"]["p99Percent"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
