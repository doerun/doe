#!/usr/bin/env python3
"""Compare a new CTS run against a stored baseline and detect regressions.

Reads a baseline snapshot and a new snapshot (both conforming to
config/cts-baseline.schema.json), compares per-query results, and emits
a structured comparison report with regression/improvement details.

Usage:
    python3 bench/cts_baseline_compare.py \
        --baseline bench/out/cts-baseline/20260323T120000Z.json \
        --current bench/out/cts-baseline/20260323T180000Z.json

    # Or use --current-dir to auto-select the latest snapshot:
    python3 bench/cts_baseline_compare.py \
        --baseline bench/out/cts-baseline/20260323T120000Z.json \
        --current-dir bench/out/cts-baseline/

Gate integration:
    python3 bench/cts_baseline_compare.py \
        --baseline bench/out/cts-baseline/20260323T120000Z.json \
        --current bench/out/cts-baseline/20260323T180000Z.json \
        --policy config/cts-baseline-policy.json \
        --gate
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TIMESTAMP_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare a CTS run against a baseline for regression detection."
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="Path to the baseline snapshot JSON.",
    )
    parser.add_argument(
        "--current",
        default="",
        help="Path to the current run snapshot JSON.",
    )
    parser.add_argument(
        "--current-dir",
        default="",
        help="Directory of snapshots; the latest file is selected as current.",
    )
    parser.add_argument(
        "--policy",
        default="config/cts-baseline-policy.json",
        help="CTS baseline policy JSON for gate thresholds.",
    )
    parser.add_argument(
        "--out",
        default="bench/out/cts-baseline/comparison.json",
        help="Output path for the comparison report.",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Run in gate mode: exit non-zero on regression above policy thresholds.",
    )
    return parser.parse_args()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def find_latest_snapshot(directory: Path) -> Path | None:
    candidates: list[Path] = []
    for child in sorted(directory.iterdir()):
        if child.suffix != ".json":
            continue
        stem = child.stem
        if TIMESTAMP_PATTERN.match(stem):
            candidates.append(child)
    return candidates[-1] if candidates else None


def build_status_map(snapshot: dict[str, Any]) -> dict[str, str]:
    results = snapshot.get("results", [])
    if not isinstance(results, list):
        return {}
    status_map: dict[str, str] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        query_id = row.get("id")
        status = row.get("status")
        if isinstance(query_id, str) and isinstance(status, str):
            status_map[query_id] = status
    return status_map


def compare_snapshots(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    baseline_map = build_status_map(baseline)
    current_map = build_status_map(current)

    all_ids = sorted(set(baseline_map.keys()) | set(current_map.keys()))

    new_passes: list[dict[str, str]] = []
    new_failures: list[dict[str, str]] = []
    stable_pass: list[str] = []
    stable_fail: list[str] = []
    new_queries: list[dict[str, str]] = []
    removed_queries: list[dict[str, str]] = []

    for query_id in all_ids:
        base_status = baseline_map.get(query_id)
        curr_status = current_map.get(query_id)

        if base_status is None and curr_status is not None:
            new_queries.append({"id": query_id, "status": curr_status})
            continue
        if base_status is not None and curr_status is None:
            removed_queries.append({"id": query_id, "baselineStatus": base_status})
            continue

        if base_status == curr_status:
            if curr_status == "pass":
                stable_pass.append(query_id)
            else:
                stable_fail.append(query_id)
            continue

        if base_status != "pass" and curr_status == "pass":
            new_passes.append({"id": query_id, "baselineStatus": base_status or "unknown"})
        elif base_status == "pass" and curr_status != "pass":
            new_failures.append({"id": query_id, "currentStatus": curr_status or "unknown"})
        elif base_status == "skip" and curr_status == "fail":
            new_failures.append({"id": query_id, "currentStatus": curr_status})
        elif base_status == "fail" and curr_status == "skip":
            pass

    baseline_summary = baseline.get("summary", {})
    current_summary = current.get("summary", {})

    baseline_pass = baseline_summary.get("passCount", 0) if isinstance(baseline_summary, dict) else 0
    current_pass = current_summary.get("passCount", 0) if isinstance(current_summary, dict) else 0
    baseline_total = baseline_summary.get("queryCount", 0) if isinstance(baseline_summary, dict) else 0
    current_total = current_summary.get("queryCount", 0) if isinstance(current_summary, dict) else 0

    delta_pass = current_pass - baseline_pass
    delta_total = current_total - baseline_total

    return {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "baselinePath": baseline.get("configPath", ""),
        "baselineGeneratedAtUtc": baseline.get("generatedAtUtc", ""),
        "currentGeneratedAtUtc": current.get("generatedAtUtc", ""),
        "baselineSummary": {
            "queryCount": baseline_total,
            "passCount": baseline_pass,
        },
        "currentSummary": {
            "queryCount": current_total,
            "passCount": current_pass,
        },
        "delta": {
            "passCountDelta": delta_pass,
            "queryCountDelta": delta_total,
        },
        "newPasses": new_passes,
        "newFailures": new_failures,
        "stablePassCount": len(stable_pass),
        "stableFailCount": len(stable_fail),
        "newQueries": new_queries,
        "removedQueries": removed_queries,
        "regressionCount": len(new_failures),
        "improvementCount": len(new_passes),
    }


def evaluate_gate(
    comparison: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Evaluate gate pass/fail against policy thresholds.

    Returns (passed, messages).
    """
    messages: list[str] = []
    passed = True

    regression_policy = policy.get("regressionPolicy", {})
    if not isinstance(regression_policy, dict):
        messages.append("WARN: missing or invalid regressionPolicy in policy config")
        return passed, messages

    gate_mode = regression_policy.get("gateMode", "advisory")
    max_new_failures = regression_policy.get("maxNewFailures", 0)
    require_no_regressions = regression_policy.get("requireNoRegressions", True)

    regression_count = comparison.get("regressionCount", 0)
    new_failures = comparison.get("newFailures", [])

    if require_no_regressions and regression_count > 0:
        msg = f"REGRESSION: {regression_count} test(s) regressed from pass to fail"
        for entry in new_failures:
            if isinstance(entry, dict):
                msg += f"\n  - {entry.get('id', '?')}: now {entry.get('currentStatus', '?')}"
        messages.append(msg)
        if gate_mode == "blocking":
            passed = False

    if regression_count > max_new_failures:
        messages.append(
            f"REGRESSION: {regression_count} new failures exceeds policy max of {max_new_failures}"
        )
        if gate_mode == "blocking":
            passed = False

    improvement_count = comparison.get("improvementCount", 0)
    if improvement_count > 0:
        messages.append(f"IMPROVEMENT: {improvement_count} test(s) newly passing")

    if passed and regression_count == 0:
        messages.append("PASS: no regressions detected")

    return passed, messages


def main() -> int:
    args = parse_args()

    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"FAIL: missing baseline: {baseline_path}")
        return 1

    if args.current:
        current_path = Path(args.current)
    elif args.current_dir:
        current_dir = Path(args.current_dir)
        if not current_dir.is_dir():
            print(f"FAIL: --current-dir is not a directory: {current_dir}")
            return 1
        found = find_latest_snapshot(current_dir)
        if found is None:
            print(f"FAIL: no timestamped snapshots found in: {current_dir}")
            return 1
        current_path = found
        if current_path == baseline_path:
            print(f"FAIL: latest snapshot is the same as baseline: {current_path}")
            return 1
    else:
        print("FAIL: provide --current or --current-dir")
        return 1

    if not current_path.exists():
        print(f"FAIL: missing current snapshot: {current_path}")
        return 1

    try:
        baseline = load_json_object(baseline_path)
        current = load_json_object(current_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1

    comparison = compare_snapshots(baseline, current)
    comparison["baselineSnapshotPath"] = str(baseline_path)
    comparison["currentSnapshotPath"] = str(current_path)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Comparison report written to: {out_path}")

    if args.gate:
        policy_path = Path(args.policy)
        if not policy_path.exists():
            print(f"FAIL: missing policy config: {policy_path}")
            return 1
        try:
            policy = load_json_object(policy_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"FAIL: policy load error: {exc}")
            return 1

        passed, messages = evaluate_gate(comparison, policy)
        for msg in messages:
            print(msg)

        summary_line = (
            f"Baseline: {comparison['baselineSummary']['passCount']}/{comparison['baselineSummary']['queryCount']} pass | "
            f"Current: {comparison['currentSummary']['passCount']}/{comparison['currentSummary']['queryCount']} pass | "
            f"Regressions: {comparison['regressionCount']} | "
            f"Improvements: {comparison['improvementCount']}"
        )
        print(summary_line)

        if not passed:
            print("FAIL: CTS baseline gate")
            return 1
        print("PASS: CTS baseline gate")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
