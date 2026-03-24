#!/usr/bin/env python3
"""Report CTS baseline trend from multiple snapshots.

Reads all timestamped baseline snapshots from bench/out/cts-baseline/ and
reports whether Doe CTS conformance is improving, regressing, or stable
over the snapshot window.

Usage:
    python3 bench/cts_baseline_trend.py
    python3 bench/cts_baseline_trend.py --dir bench/out/cts-baseline/ --policy config/cts-baseline-policy.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TIMESTAMP_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report CTS baseline trend from multiple snapshots."
    )
    parser.add_argument(
        "--dir",
        default="bench/out/cts-baseline",
        help="Directory containing timestamped baseline snapshot JSON files.",
    )
    parser.add_argument(
        "--policy",
        default="config/cts-baseline-policy.json",
        help="CTS baseline policy JSON for trend window configuration.",
    )
    parser.add_argument(
        "--out",
        default="bench/out/cts-baseline/trend.json",
        help="Output path for the trend report.",
    )
    return parser.parse_args()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def collect_snapshots(directory: Path) -> list[tuple[str, Path]]:
    """Collect timestamped snapshot files sorted chronologically."""
    entries: list[tuple[str, Path]] = []
    if not directory.is_dir():
        return entries
    for child in sorted(directory.iterdir()):
        if child.suffix != ".json":
            continue
        stem = child.stem
        if TIMESTAMP_PATTERN.match(stem):
            entries.append((stem, child))
    return entries


def extract_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    summary = snapshot.get("summary", {})
    if not isinstance(summary, dict):
        return {"queryCount": 0, "passCount": 0, "failCount": 0, "skipCount": 0, "passRate": 0.0}
    return {
        "queryCount": summary.get("queryCount", 0),
        "passCount": summary.get("passCount", 0),
        "failCount": summary.get("failCount", 0),
        "skipCount": summary.get("skipCount", 0),
        "passRate": summary.get("passRate", 0.0),
    }


def classify_trend(pass_counts: list[int]) -> str:
    """Classify trend direction from a sequence of pass counts.

    Returns one of: 'improving', 'regressing', 'stable', 'insufficient_data'.
    """
    if len(pass_counts) < 2:
        return "insufficient_data"

    deltas = [pass_counts[i] - pass_counts[i - 1] for i in range(1, len(pass_counts))]

    positive = sum(1 for d in deltas if d > 0)
    negative = sum(1 for d in deltas if d < 0)
    zero = sum(1 for d in deltas if d == 0)

    if negative == 0 and positive > 0:
        return "improving"
    if positive == 0 and negative > 0:
        return "regressing"
    if positive > negative:
        return "improving"
    if negative > positive:
        return "regressing"
    return "stable"


def main() -> int:
    args = parse_args()
    snapshot_dir = Path(args.dir)

    policy_path = Path(args.policy)
    min_snapshots = 2
    window_size = 5

    if policy_path.exists():
        try:
            policy = load_json_object(policy_path)
            trend_policy = policy.get("trendPolicy", {})
            if isinstance(trend_policy, dict):
                raw_min = trend_policy.get("minSnapshots", 2)
                raw_window = trend_policy.get("regressionWindowSize", 5)
                if isinstance(raw_min, int) and raw_min >= 2:
                    min_snapshots = raw_min
                if isinstance(raw_window, int) and raw_window >= 2:
                    window_size = raw_window
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"WARN: failed to load policy: {exc}")

    entries = collect_snapshots(snapshot_dir)

    if len(entries) < min_snapshots:
        report: dict[str, Any] = {
            "schemaVersion": 1,
            "generatedAtUtc": utc_now(),
            "snapshotDir": str(snapshot_dir),
            "snapshotCount": len(entries),
            "minSnapshotsRequired": min_snapshots,
            "trend": "insufficient_data",
            "snapshots": [],
            "notes": f"Need at least {min_snapshots} snapshots; found {len(entries)}.",
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    snapshot_summaries: list[dict[str, Any]] = []
    for timestamp, path in entries:
        try:
            snapshot = load_json_object(path)
            summary = extract_summary(snapshot)
            snapshot_summaries.append({
                "timestamp": timestamp,
                "path": str(path),
                "generatedAtUtc": snapshot.get("generatedAtUtc", ""),
                "backend": snapshot.get("backend", ""),
                **summary,
            })
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"WARN: skipping {path}: {exc}")

    if len(snapshot_summaries) < min_snapshots:
        print(f"WARN: only {len(snapshot_summaries)} valid snapshots; need {min_snapshots}")

    window = snapshot_summaries[-window_size:] if len(snapshot_summaries) > window_size else snapshot_summaries
    pass_counts = [s["passCount"] for s in window]
    trend = classify_trend(pass_counts)

    first = snapshot_summaries[0] if snapshot_summaries else {}
    last = snapshot_summaries[-1] if snapshot_summaries else {}
    total_delta = (last.get("passCount", 0) - first.get("passCount", 0)) if first and last else 0

    report = {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "snapshotDir": str(snapshot_dir),
        "snapshotCount": len(snapshot_summaries),
        "windowSize": len(window),
        "minSnapshotsRequired": min_snapshots,
        "trend": trend,
        "totalPassDelta": total_delta,
        "firstSnapshot": {
            "timestamp": first.get("timestamp", ""),
            "passCount": first.get("passCount", 0),
            "queryCount": first.get("queryCount", 0),
        },
        "lastSnapshot": {
            "timestamp": last.get("timestamp", ""),
            "passCount": last.get("passCount", 0),
            "queryCount": last.get("queryCount", 0),
        },
        "snapshots": snapshot_summaries,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"CTS Baseline Trend: {trend.upper()}")
    print(f"  Snapshots: {len(snapshot_summaries)} (window: {len(window)})")
    if first and last:
        print(
            f"  First: {first.get('timestamp', '?')} "
            f"({first.get('passCount', 0)}/{first.get('queryCount', 0)} pass)"
        )
        print(
            f"  Last:  {last.get('timestamp', '?')} "
            f"({last.get('passCount', 0)}/{last.get('queryCount', 0)} pass)"
        )
        print(f"  Total pass delta: {total_delta:+d}")
    print(f"  Report: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
