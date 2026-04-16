#!/usr/bin/env python3
"""Subgroup-vs-tree-reduction kernel micro-benchmark.

Times rmsnorm.wgsl (workgroup tree reduction) against rmsnorm_subgroup.wgsl
(subgroupAdd) on AMD Vulkan via doe-zig-runtime. Each run dispatches the
kernel 100 times and reads the GPU timestamp from the trace JSONL. Repeats
N times to get p50/p95/p99 distribution.

Emits a sibling .claim.json gated on:
  - >= 15 timed samples per side (release floor; >= 7 for local)
  - positive p50 + p95 + p99 deltas (for release; p50 + p95 for local)

Usage:
  python3 bench/native-compare/compare_subgroup_kernels.py [--iterations N]
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_BIN = REPO_ROOT / "runtime/zig/zig-out/bin/doe-zig-runtime"
QUIRKS_PATH = REPO_ROOT / "examples/quirks/amd_radv_noop_list.json"
KERNEL_ROOT = REPO_ROOT / "bench/kernels"
OUT_DIR = REPO_ROOT / "bench/out/subgroup-kernels"
CLAIM_LOCAL_MIN_SAMPLES = 7
CLAIM_RELEASE_MIN_SAMPLES = 15

PAIRS = [
    {
        "label": "rmsnorm",
        "tree_commands": REPO_ROOT / "examples/rmsnorm_tree_commands.json",
        "subgroup_commands": REPO_ROOT / "examples/rmsnorm_subgroup_commands.json",
    },
    {
        "label": "matmul_gemv",
        "tree_commands": REPO_ROOT / "examples/matmul_gemv_tree_commands.json",
        "subgroup_commands": REPO_ROOT / "examples/matmul_gemv_subgroup_commands.json",
    },
]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--claim-mode", choices=("local", "release"), default="release")
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_one(commands_path: Path, run_index: int) -> dict:
    trace_jsonl = OUT_DIR / "trace" / f"trace_{commands_path.stem}_{run_index}.jsonl"
    trace_meta = OUT_DIR / "trace" / f"trace_{commands_path.stem}_{run_index}.meta.json"
    trace_jsonl.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(RUNTIME_BIN),
        "--quirks", str(QUIRKS_PATH),
        "--commands", str(commands_path),
        "--backend", "native",
        "--backend-lane", "vulkan_doe_release",
        "--vendor", "amd",
        "--api", "vulkan",
        "--family", "gfx11",
        "--driver", "26.0.3",
        "--execute",
        "--trace",
        "--kernel-root", str(KERNEL_ROOT),
        "--trace-jsonl", str(trace_jsonl),
        "--trace-meta", str(trace_meta),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-2000:])
        sys.stderr.write(proc.stderr[-2000:])
        raise RuntimeError(f"doe-zig-runtime failed for {commands_path}: rc={proc.returncode}")
    gpu_ns = None
    dispatch_count = 0
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        rec = json.loads(line)
        if rec.get("command") == "kernel_dispatch":
            gpu_ns = int(rec.get("executionGpuTimestampNs", 0))
            dispatch_count = int(rec.get("executionDispatchCount", 0))
    if gpu_ns is None or dispatch_count == 0:
        raise RuntimeError(f"no kernel_dispatch trace from {commands_path}")
    return {"gpu_ns_total": gpu_ns, "gpu_ns_per_dispatch": gpu_ns / dispatch_count, "dispatch_count": dispatch_count}


def stats(values: list[float]) -> dict:
    sorted_values = sorted(values)
    n = len(sorted_values)
    def pct(p: float) -> float:
        return sorted_values[int((n - 1) * p)]
    return {
        "count": n,
        "min_ns": sorted_values[0],
        "max_ns": sorted_values[-1],
        "p10_ns": pct(0.10),
        "p50_ns": pct(0.50),
        "p95_ns": pct(0.95),
        "p99_ns": pct(0.99),
        "mean_ns": statistics.fmean(sorted_values),
        "stdev_ns": statistics.pstdev(sorted_values) if n > 1 else 0.0,
    }


def delta_percent(baseline_ns: float, comparison_ns: float) -> float | None:
    if baseline_ns <= 0 or comparison_ns <= 0:
        return None
    return ((comparison_ns / baseline_ns) - 1) * 100


def gate_one(label: str, tree: list[dict], subgroup: list[dict], claim_mode: str) -> dict:
    min_samples = CLAIM_RELEASE_MIN_SAMPLES if claim_mode == "release" else CLAIM_LOCAL_MIN_SAMPLES
    required_pcts = ["p50", "p95", "p99"] if claim_mode == "release" else ["p50", "p95"]
    tree_per = [r["gpu_ns_per_dispatch"] for r in tree]
    sg_per = [r["gpu_ns_per_dispatch"] for r in subgroup]
    tree_stats = stats(tree_per)
    sg_stats = stats(sg_per)
    delta_p50 = delta_percent(sg_stats["p50_ns"], tree_stats["p50_ns"])
    delta_p95 = delta_percent(sg_stats["p95_ns"], tree_stats["p95_ns"])
    delta_p99 = delta_percent(sg_stats["p99_ns"], tree_stats["p99_ns"])
    deltas = {"p50": delta_p50, "p95": delta_p95, "p99": delta_p99}
    reasons = []
    if len(tree) < min_samples:
        reasons.append(f"tree sample count {len(tree)} < {claim_mode} floor {min_samples}")
    if len(subgroup) < min_samples:
        reasons.append(f"subgroup sample count {len(subgroup)} < {claim_mode} floor {min_samples}")
    for pct in required_pcts:
        v = deltas[pct]
        if v is None:
            reasons.append(f"delta.{pct} unavailable")
        elif v <= 0:
            reasons.append(f"delta.{pct} {v:+.2f}% not positive")
    return {
        "label": label,
        "claimable": not reasons,
        "reasons": reasons,
        "requiredPositivePercentiles": required_pcts,
        "tree": tree_stats,
        "subgroup": sg_stats,
        "deltaPercent": {"p50": delta_p50, "p95": delta_p95, "p99": delta_p99},
    }


def main():
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not RUNTIME_BIN.exists():
        sys.exit(f"error: doe-zig-runtime not built at {RUNTIME_BIN}")

    workloads = []
    for pair in PAIRS:
        print(f"\n=== {pair['label']}: tree x{args.iterations} ===")
        try:
            tree_runs = [run_one(pair["tree_commands"], i) for i in range(args.iterations)]
        except RuntimeError as exc:
            print(f"  SKIP: tree side failed: {exc}")
            workloads.append({"label": pair["label"], "claimable": False, "reasons": [f"tree dispatch failed: {exc}"]})
            continue
        print(f"=== {pair['label']}: subgroup x{args.iterations} ===")
        try:
            sg_runs = [run_one(pair["subgroup_commands"], i) for i in range(args.iterations)]
        except RuntimeError as exc:
            print(f"  SKIP: subgroup side failed: {exc}")
            workloads.append({"label": pair["label"], "claimable": False, "reasons": [f"subgroup dispatch failed: {exc}"]})
            continue
        gate = gate_one(pair["label"], tree_runs, sg_runs, args.claim_mode)
        print(
            f"  tree   p50/p95/p99 ns/dispatch: "
            f"{gate['tree']['p50_ns']:.0f} / {gate['tree']['p95_ns']:.0f} / {gate['tree']['p99_ns']:.0f}"
        )
        print(
            f"  subgroup p50/p95/p99 ns/dispatch: "
            f"{gate['subgroup']['p50_ns']:.0f} / {gate['subgroup']['p95_ns']:.0f} / {gate['subgroup']['p99_ns']:.0f}"
        )
        d = gate['deltaPercent']
        print(f"  delta% (subgroup faster): p50={d['p50']:+.2f}% p95={d['p95']:+.2f}% p99={d['p99']:+.2f}%")
        print(f"  claimable ({args.claim_mode}): {gate['claimable']}")
        if gate['reasons']:
            for r in gate['reasons']:
                print(f"    - {r}")
        workloads.append(gate)

    pass_all = all(w["claimable"] for w in workloads)
    claim_report = {
        "schemaVersion": 1,
        "artifactKind": "claim-report",
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "claimMode": args.claim_mode,
        "claimPolicy": {
            "minTimedSamples": CLAIM_RELEASE_MIN_SAMPLES if args.claim_mode == "release" else CLAIM_LOCAL_MIN_SAMPLES,
            "requiredPositivePercentiles": ["p50", "p95", "p99"] if args.claim_mode == "release" else ["p50", "p95"],
            "policySource": "config/benchmark-methodology-thresholds.json (claimabilityDefaults)",
            "deltaPercentConvention": "((tree_ns / subgroup_ns) - 1) * 100; positive = subgroup faster",
            "timingSource": "executionGpuTimestampNs (Vulkan timestamp queries)",
        },
        "binaryProvenance": {
            "doeZigRuntime": {
                "path": str(RUNTIME_BIN),
                "sha256": file_sha256(RUNTIME_BIN),
            },
        },
        "host": {
            "vendor": "amd",
            "device": "Radeon 8060S Graphics (RADV STRIX_HALO)",
            "driver": "Mesa 26.0.3",
            "api": "vulkan",
        },
        "comparisonStatus": "comparable",
        "claimStatus": "claimable" if pass_all else "not_claimable",
        "pass": pass_all,
        "reasons": [] if pass_all else [f"{sum(1 for w in workloads if not w['claimable'])} of {len(workloads)} rows not claimable"],
        "workloads": workloads,
    }
    out_path = OUT_DIR / "subgroup-vs-tree.claim.json"
    with open(out_path, "w") as f:
        json.dump(claim_report, f, indent=2)
        f.write("\n")
    print(f"\nclaim status: {claim_report['claimStatus']} pass: {claim_report['pass']}")
    print(f"wrote: {out_path}")
    return 0 if pass_all else 1


if __name__ == "__main__":
    sys.exit(main())
