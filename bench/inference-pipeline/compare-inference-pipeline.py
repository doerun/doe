#!/usr/bin/env python3
"""Compare inference pipeline performance: Doe native vs Dawn delegate.

Runs the JS inference benchmark twice (once per backend) and produces
a comparison report with per-phase delta statistics.

Usage:
    python3 bench/inference-pipeline/compare-inference-pipeline.py \
        --config bench/inference-pipeline/inference-pipeline-config.json

Output:
    NDJSON comparison report in the configured output directory.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_VERSION = 1
DELTA_CONVENTION = "((rightMs / leftMs) - 1) * 100; positive = left (Doe) faster"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Config JSON path")
    parser.add_argument("--runtime", default="node", help="JS runtime: node or bun")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_config(path):
    with open(path) as f:
        return json.load(f)


def run_bench(runtime, config_path, backend, out_path, dry_run):
    """Run the inference benchmark for one backend."""
    bench_script = REPO_ROOT / "bench" / "inference-pipeline" / "run-inference-bench.js"
    cmd = [
        runtime,
        str(bench_script),
        "--config", config_path,
        "--out", str(out_path),
    ]
    if backend:
        cmd.extend(["--backend", backend])

    if dry_run:
        print(f"[dry-run] {' '.join(cmd)}")
        return []

    print(f"running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))

    if proc.returncode != 0:
        print(f"error: benchmark failed for backend={backend}", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return []

    records = []
    with open(out_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def extract_summaries(records):
    """Index summary records by phase."""
    return {
        r["phase"]: r
        for r in records
        if r.get("kind") == "inference_pipeline_bench_summary"
    }


def compute_delta(left_ms, right_ms):
    if left_ms == 0:
        return None
    return round(((right_ms / left_ms) - 1) * 100, 2)


def build_comparison(left_summaries, right_summaries, config):
    """Build per-phase comparison records."""
    records = []

    for phase in ("prefill", "decode", "e2e"):
        left = left_summaries.get(phase)
        right = right_summaries.get(phase)

        if not left or not right:
            records.append({
                "kind": "inference_pipeline_comparison",
                "schemaVersion": SCHEMA_VERSION,
                "phase": phase,
                "status": "skipped",
                "reason": "missing_left" if not left else "missing_right",
            })
            continue

        records.append({
            "kind": "inference_pipeline_comparison",
            "schemaVersion": SCHEMA_VERSION,
            "deltaPercentConvention": DELTA_CONVENTION,
            "phase": phase,
            "modelId": left.get("modelId"),
            "promptTokens": left.get("promptTokens"),
            "decodeTokens": left.get("decodeTokens"),
            "layers": left.get("layers"),
            "left": {
                "runtime": config["comparison"]["leftRuntime"],
                "p50_ms": left["p50_ms"],
                "p95_ms": left["p95_ms"],
                "p99_ms": left["p99_ms"],
                "iterations": left["iterations"],
            },
            "right": {
                "runtime": config["comparison"]["rightRuntime"],
                "p50_ms": right["p50_ms"],
                "p95_ms": right["p95_ms"],
                "p99_ms": right["p99_ms"],
                "iterations": right["iterations"],
            },
            "deltaPercent": {
                "p50": compute_delta(left["p50_ms"], right["p50_ms"]),
                "p95": compute_delta(left["p95_ms"], right["p95_ms"]),
                "p99": compute_delta(left["p99_ms"], right["p99_ms"]),
            },
            "status": "compared",
            "benchmarkClass": "directional",
            "directionalReason": "different_runtime_stacks_random_weights",
        })

    return records


def print_summary(records):
    compared = [r for r in records if r.get("status") == "compared"]
    if not compared:
        print("no comparable results")
        return

    print(f"\n{'phase':<12} {'doe p50(ms)':>12} {'dawn p50(ms)':>12} {'delta%':>10}")
    print("-" * 50)

    for r in compared:
        doe_ms = r["left"]["p50_ms"]
        dawn_ms = r["right"]["p50_ms"]
        delta = r["deltaPercent"]["p50"]
        sign = "+" if delta and delta > 0 else ""
        delta_str = f"{sign}{delta:.1f}%" if delta is not None else "n/a"
        print(f"{r['phase']:<12} {doe_ms:>12.2f} {dawn_ms:>12.2f} {delta_str:>10}")


def main():
    args = parse_args()
    config = load_config(args.config)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = REPO_ROOT / config["output"]["dir"] / ts
    os.makedirs(out_dir, exist_ok=True)

    left_out = out_dir / "left-doe.ndjson"
    right_out = out_dir / "right-dawn.ndjson"

    print(f"=== Left: {config['comparison']['leftRuntime']} ===")
    left_records = run_bench(
        args.runtime, args.config,
        config["comparison"]["leftRuntime"],
        left_out, args.dry_run,
    )

    print(f"\n=== Right: {config['comparison']['rightRuntime']} ===")
    right_records = run_bench(
        args.runtime, args.config,
        config["comparison"]["rightRuntime"],
        right_out, args.dry_run,
    )

    left_summaries = extract_summaries(left_records)
    right_summaries = extract_summaries(right_records)

    comparison = build_comparison(left_summaries, right_summaries, config)

    report_path = out_dir / f"{config['output']['reportPrefix']}.comparison.ndjson"
    with open(report_path, "w") as f:
        for record in comparison:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")

    print(f"\nwrote comparison to {report_path}")
    print_summary(comparison)


if __name__ == "__main__":
    main()
