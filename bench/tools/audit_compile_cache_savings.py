#!/usr/bin/env python3
"""Compile-cache savings audit (SdkLayout hardening gap 1 evidence).

Scans runner traces, groups them by `executedCompile.cacheKey`, and
reports wall-time that a content-addressed compile cache would have
saved — i.e. every invocation after the first for a given cacheKey is
recompile cost a cache would amortize to zero.

Note: this tool does NOT enable the cache. It only inventories present
traces to make the cost of the missing cache visible. A future tick will
wire lookup/insert into the runner.

Usage:
  python3 bench/tools/audit_compile_cache_savings.py \\
    --trace-glob "bench/out/streaming-executor/*trace*.json" \\
    --trace-glob "bench/out/scratch/**/*trace*.json" \\
    --out-json bench/out/compile-cache-audit.json

Exit 0 if at least one trace was scanned; 1 if no traces found.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--trace-glob", action="append", default=[],
        help="Glob pattern for runner traces (may be repeated).",
    )
    p.add_argument(
        "--out-json", default="",
        help="Optional path for machine-readable audit artifact.",
    )
    return p.parse_args()


def resolve_glob(pat: str) -> list[Path]:
    base = REPO_ROOT / pat if not Path(pat).is_absolute() else Path(pat)
    return [Path(p) for p in glob.glob(str(base), recursive=True)]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    if not args.trace_glob:
        args.trace_glob = [
            "bench/out/streaming-executor/*trace*.json",
            "bench/out/scratch/**/*trace*.json",
        ]

    candidate_paths: list[Path] = []
    for pat in args.trace_glob:
        candidate_paths.extend(resolve_glob(pat))
    candidate_paths = sorted({p for p in candidate_paths if p.is_file()})

    scanned: list[dict] = []
    groups: dict[str | None, list[dict]] = defaultdict(list)
    skipped_no_cache_key = 0

    for path in candidate_paths:
        try:
            trace = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if trace.get("artifactKind") != "doe_streaming_executor_trace":
            continue
        ec = trace.get("executedCompile") or {}
        cache_key = ec.get("cacheKey")
        elapsed_ms = ec.get("elapsedMs")
        entry = {
            "tracePath": rel(path),
            "cacheKey": cache_key,
            "compileElapsedMs": elapsed_ms,
            "target": trace.get("target"),
            "modelId": trace.get("modelId"),
            "cacheKeyComponents": ec.get("cacheKeyComponents"),
        }
        scanned.append(entry)
        if not cache_key:
            skipped_no_cache_key += 1
            continue
        groups[cache_key].append(entry)

    group_records = []
    total_ms = 0.0
    savings_ms = 0.0
    for cache_key, entries in sorted(groups.items()):
        ordered = sorted(
            entries,
            key=lambda e: (e["compileElapsedMs"] or 0.0, e["tracePath"]),
        )
        elapsed_values = [
            e["compileElapsedMs"] for e in ordered
            if isinstance(e["compileElapsedMs"], (int, float))
        ]
        group_total = sum(elapsed_values)
        group_min = min(elapsed_values) if elapsed_values else 0.0
        # Cache would pay the smallest compile once; every other
        # invocation in the same key group would be a cache hit (~0ms).
        group_savings = max(0.0, group_total - group_min)
        total_ms += group_total
        savings_ms += group_savings
        group_records.append({
            "cacheKey": cache_key,
            "traceCount": len(entries),
            "target": ordered[0]["target"] if ordered else None,
            "modelId": ordered[0]["modelId"] if ordered else None,
            "cacheKeyComponents": ordered[0]["cacheKeyComponents"] if ordered else None,
            "compileElapsedMsTotal": group_total,
            "compileElapsedMsMin": group_min,
            "compileElapsedMsSavingsIfCached": group_savings,
            "tracePaths": [e["tracePath"] for e in ordered],
        })

    verdict = {
        "schemaVersion": 1,
        "artifactKind": "doe_compile_cache_savings_audit",
        "tracesScanned": len(scanned),
        "tracesWithoutCacheKey": skipped_no_cache_key,
        "tracesWithCacheKey": sum(len(v) for v in groups.values()),
        "distinctCacheKeys": len(groups),
        "compileElapsedMsTotalScanned": total_ms,
        "compileElapsedMsSavingsIfCached": savings_ms,
        "groups": group_records,
    }

    if args.out_json:
        out_path = REPO_ROOT / args.out_json if not Path(args.out_json).is_absolute() else Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {rel(out_path)}")

    if len(scanned) == 0:
        print("FAIL: no streaming-executor traces found in glob set.")
        return 1

    print(
        f"scanned {len(scanned)} traces "
        f"({verdict['tracesWithCacheKey']} carry cacheKey, "
        f"{verdict['tracesWithoutCacheKey']} pre-cacheKey) "
        f"across {verdict['distinctCacheKeys']} distinct cache keys. "
        f"Cache-hit savings: {savings_ms:.1f} ms of {total_ms:.1f} ms total "
        f"compile time scanned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
