#!/usr/bin/env python3
"""WGSL compilation speed comparison: Doe vs Tint.

Runs both compilers on the same named workload rows or a legacy shader
corpus and emits a comparison report with per-shader delta statistics.
Both sides measure the same scope: WGSL source -> target text/binary
(parse + sema + IR + emit).

Usage:
    python3 bench/native-compare/compare_doe_vs_tint_compilation.py \
        --config bench/native-compare/compare_doe_vs_tint.config.json

Requirements:
    - Doe compilation benchmark binary: zig-out/bin/doe-compilation-bench
    - Tint binary (Release build): bench/vendor/dawn/out/Release/tint
    - Both must be built before running.

Output:
    NDJSON comparison report at the configured output path.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

TARGET_MAP = {"msl": "msl", "spirv": "spv", "hlsl": "hlsl"}
SCHEMA_VERSION = 1
DELTA_PERCENT_CONVENTION = "((rightNs / leftNs) - 1) * 100; positive = left (Doe) faster"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        required=True,
        help="Path to comparison config JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing",
    )
    parser.add_argument(
        "--workload-id",
        action="append",
        default=[],
        help="Optional compilation workload id to run. Repeat to select multiple rows.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        help="Override timed iterations from config.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        help="Override warmup iterations from config.",
    )
    return parser.parse_args()


def load_config(path):
    with open(path) as f:
        return json.load(f)


def infer_tier_from_name(name):
    if name.startswith("compilation_inference_") or name.startswith("inference_"):
        return "inference"
    head = name.split("_", 1)[0]
    if head in {"trivial", "simple", "moderate", "complex", "stress"}:
        return head
    return "external"


def discover_corpus(corpus_dir, tiers):
    """Find .wgsl files in corpus_dir, optionally filtering by tier prefix."""
    corpus_path = REPO_ROOT / corpus_dir
    if not corpus_path.is_dir():
        print(f"error: corpus directory not found: {corpus_path}", file=sys.stderr)
        sys.exit(1)

    shaders = []
    for wgsl in sorted(corpus_path.glob("*.wgsl")):
        name = wgsl.stem
        tier = name.split("_")[0]  # trivial, simple, moderate, complex, stress
        if tiers and tier not in tiers:
            continue
        line_count = len(wgsl.read_text().splitlines())
        shaders.append(
            {"name": name, "tier": tier, "path": str(wgsl), "sourceLines": line_count}
        )

    if not shaders:
        print(f"error: no shaders found in {corpus_path}", file=sys.stderr)
        sys.exit(1)

    return shaders


def discover_workload_rows(workloads_path, workload_ids):
    workload_path = REPO_ROOT / workloads_path
    if not workload_path.is_file():
        print(f"error: workloads file not found: {workload_path}", file=sys.stderr)
        sys.exit(1)

    payload = json.loads(workload_path.read_text(encoding="utf-8"))
    rows = payload.get("workloads", [])
    requested_ids = list(workload_ids or [])
    requested_id_set = set(requested_ids)
    shaders = []

    for row in rows:
        if row.get("runnerType") != "compilation":
            continue
        workload_id = row.get("id", "")
        if requested_id_set and workload_id not in requested_id_set:
            continue
        shader_rel = row.get("shaderPath", "")
        shader_path = REPO_ROOT / shader_rel
        if not shader_path.is_file():
            print(
                f"error: shaderPath not found for workload {workload_id}: {shader_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        source_lines = len(shader_path.read_text(encoding="utf-8").splitlines())
        shaders.append(
            {
                "workloadId": workload_id,
                "name": workload_id,
                "tier": infer_tier_from_name(workload_id),
                "path": str(shader_path),
                "sourceLines": source_lines,
                "target": row.get("compilationTarget", "msl"),
                "sourceShader": shader_path.stem,
            }
        )

    if requested_id_set:
        found_ids = {shader["workloadId"] for shader in shaders}
        missing = [workload_id for workload_id in requested_ids if workload_id not in found_ids]
        if missing:
            print(
                f"error: workload ids not found in {workload_path}: {', '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(1)

    if not shaders:
        print(f"error: no compilation workloads found in {workload_path}", file=sys.stderr)
        sys.exit(1)

    return shaders


def run_doe_bench(cfg, shaders, target, out_path, dry_run):
    """Run Doe's compilation benchmark on the selected shader rows."""
    doe_bin = REPO_ROOT / cfg["left"]["binaryPath"]
    if not doe_bin.exists() and not dry_run:
        print(f"error: Doe binary not found: {doe_bin}", file=sys.stderr)
        print("  Build with: cd runtime/zig && zig build bench-compilation", file=sys.stderr)
        sys.exit(1)
    results = {}

    for shader in shaders:
        shader_target = shader.get("target", target)
        cmd = [
            str(doe_bin),
            "--target", shader_target,
            "--iterations", str(cfg["run"]["iterations"]),
            "--warmup", str(cfg["run"]["warmup"]),
            "--shader-path", shader["path"],
            "--shader-name", shader["name"],
            "--shader-tier", shader["tier"],
            "--out", str(out_path),
        ]

        if dry_run:
            print(f"[dry-run] {' '.join(cmd)}")
            results[shader["name"]] = {"p50_ns": 0, "p95_ns": 0, "p99_ns": 0}
            continue

        subprocess.run(cmd, check=True)
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("kind") == "compilation_bench" and record.get("shader") == shader["name"]:
                    results[shader["name"]] = record
                    break

    return results


def run_tint_bench(cfg, shaders, target, iterations, warmup, dry_run):
    """Time Tint compilation for each shader in the corpus."""
    tint_bin = REPO_ROOT / cfg["right"]["binaryPath"]
    tint_format = TARGET_MAP.get(target, target)

    if not tint_bin.exists() and not dry_run:
        print(f"error: Tint binary not found: {tint_bin}", file=sys.stderr)
        print(
            "  Build Dawn in Release mode, then copy tint binary to the configured path.",
            file=sys.stderr,
        )
        sys.exit(1)

    results = {}
    total_runs = iterations + warmup

    for shader in shaders:
        if dry_run:
            print(f"[dry-run] tint --format={tint_format} {shader['path']} x{total_runs}")
            results[shader["name"]] = {"p50_ns": 0, "p95_ns": 0, "p99_ns": 0}
            continue

        samples = []
        for i in range(total_runs):
            start = time.perf_counter_ns()
            proc = subprocess.run(
                [str(tint_bin), f"--format={tint_format}", shader["path"]],
                capture_output=True,
            )
            elapsed = time.perf_counter_ns() - start

            if proc.returncode != 0:
                print(
                    f"  warning: tint failed on {shader['name']}: {proc.stderr.decode()[:200]}",
                    file=sys.stderr,
                )
                break

            # skip warmup
            if i >= warmup:
                samples.append(elapsed)

        if not samples:
            print(f"  skipping {shader['name']}: no successful timed samples", file=sys.stderr)
            continue

        samples.sort()
        n = len(samples)
        results[shader["name"]] = {
            "p50_ns": samples[n // 2],
            "p95_ns": samples[int(n * 0.95)],
            "p99_ns": samples[min(int(n * 0.99), n - 1)],
            "min_ns": samples[0],
            "max_ns": samples[-1],
            "mean_ns": sum(samples) // n,
            "iterations": n,
            "timingNote": "process-level timing includes tint startup overhead",
        }

    return results


def compute_delta(left_ns, right_ns):
    """Positive = left (Doe) is faster."""
    if left_ns == 0:
        return None
    return ((right_ns / left_ns) - 1) * 100


def build_report(cfg, shaders, target, doe_results, tint_results):
    """Build comparison report records."""
    records = []

    for shader in shaders:
        name = shader["name"]
        doe = doe_results.get(name)
        tint = tint_results.get(name)

        if not doe or not tint:
            records.append(
                {
                    "kind": "compilation_comparison",
                    "schemaVersion": SCHEMA_VERSION,
                    "shader": name,
                    "workloadId": shader.get("workloadId", name),
                    "shaderPath": shader["path"],
                    "tier": shader["tier"],
                    "target": target,
                    "sourceLines": shader["sourceLines"],
                    "status": "skipped",
                    "reason": "missing_doe" if not doe else "missing_tint",
                }
            )
            continue

        left_p50 = doe.get("p50_ns", 0)
        right_p50 = tint.get("p50_ns", 0)
        left_p95 = doe.get("p95_ns", 0)
        right_p95 = tint.get("p95_ns", 0)
        left_p99 = doe.get("p99_ns", 0)
        right_p99 = tint.get("p99_ns", 0)

        records.append(
            {
                "kind": "compilation_comparison",
                "schemaVersion": SCHEMA_VERSION,
                "deltaPercentConvention": DELTA_PERCENT_CONVENTION,
                "shader": name,
                "workloadId": shader.get("workloadId", name),
                "shaderPath": shader["path"],
                "tier": shader["tier"],
                "target": target,
                "sourceLines": shader["sourceLines"],
                "left": {
                    "compiler": "doe_wgsl",
                    "p50_ns": left_p50,
                    "p95_ns": left_p95,
                    "p99_ns": left_p99,
                    "bytesOut": doe.get("bytesOut", 0),
                    "timingNote": "in-process measurement, no startup overhead",
                },
                "right": {
                    "compiler": "tint",
                    "p50_ns": right_p50,
                    "p95_ns": right_p95,
                    "p99_ns": right_p99,
                    "timingNote": tint.get(
                        "timingNote",
                        "process-level timing includes startup overhead",
                    ),
                },
                "deltaPercent": {
                    "p50": round(compute_delta(left_p50, right_p50), 2)
                    if left_p50 > 0 and right_p50 > 0
                    else None,
                    "p95": round(compute_delta(left_p95, right_p95), 2)
                    if left_p95 > 0 and right_p95 > 0
                    else None,
                    "p99": round(compute_delta(left_p99, right_p99), 2)
                    if left_p99 > 0 and right_p99 > 0
                    else None,
                },
                "status": "compared",
                "comparabilityNote": "Doe uses in-process timing; Tint uses process-level timing "
                "which includes OS process startup. For strict comparison, use tint-bench "
                "in-process harness when available.",
            }
        )

    return records


def write_report(records, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        for record in records:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    print(f"wrote {len(records)} records to {out_path}")


def print_summary(records, target):
    compared = [r for r in records if r.get("status") == "compared"]
    if not compared:
        print("no comparable results")
        return

    print(f"\n{'shader':<40} {'tier':<10} {'doe p50(us)':>12} {'tint p50(us)':>12} {'delta%':>10}")
    print("-" * 90)

    for r in compared:
        doe_us = r["left"]["p50_ns"] / 1000
        tint_us = r["right"]["p50_ns"] / 1000
        delta = r["deltaPercent"]["p50"]
        delta_str = f"+{delta:.1f}%" if delta and delta > 0 else f"{delta:.1f}%" if delta else "n/a"
        print(f"{r['shader']:<40} {r['tier']:<10} {doe_us:>12.1f} {tint_us:>12.1f} {delta_str:>10}")

    # aggregate
    doe_total = sum(r["left"]["p50_ns"] for r in compared)
    tint_total = sum(r["right"]["p50_ns"] for r in compared)
    overall_delta = compute_delta(doe_total, tint_total)
    print("-" * 90)
    print(
        f"{'TOTAL':<40} {'':<10} {doe_total/1000:>12.1f} {tint_total/1000:>12.1f} "
        f"{'+' if overall_delta and overall_delta > 0 else ''}"
        f"{overall_delta:.1f}%"
        if overall_delta
        else "n/a"
    )


def main():
    args = parse_args()
    cfg = load_config(args.config)

    corpus_dir = cfg.get("corpusDir", "bench/kernels/compilation-corpus")
    tiers = cfg["run"].get("tiers", [])
    targets = cfg["run"].get("targets", ["msl"])
    iterations = args.iterations if args.iterations is not None else cfg["run"]["iterations"]
    warmup = args.warmup if args.warmup is not None else cfg["run"]["warmup"]
    out_dir = cfg["run"].get("outDir", "bench/out/compilation")
    cfg["run"]["iterations"] = iterations
    cfg["run"]["warmup"] = warmup

    if "workloads" in cfg:
        workload_ids = args.workload_id or cfg.get("workloadIds", [])
        shaders = discover_workload_rows(cfg["workloads"], workload_ids)
        source_label = cfg["workloads"]
    else:
        shaders = discover_corpus(corpus_dir, tiers)
        source_label = corpus_dir

    print(f"shaders: {len(shaders)} selected from {source_label}")

    for target in targets:
        print(f"\n=== target: {target} ===")

        doe_out = REPO_ROOT / out_dir / f"doe-{target}.ndjson"
        os.makedirs(doe_out.parent, exist_ok=True)

        doe_results = run_doe_bench(cfg, shaders, target, doe_out, args.dry_run)
        tint_results = run_tint_bench(cfg, shaders, target, iterations, warmup, args.dry_run)

        records = build_report(cfg, shaders, target, doe_results, tint_results)

        report_path = REPO_ROOT / out_dir / f"doe-vs-tint.{target}.ndjson"
        write_report(records, report_path)
        print_summary(records, target)


if __name__ == "__main__":
    main()
