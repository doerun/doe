#!/usr/bin/env python3
"""Validate full-matrix claim readiness from a compare_dawn_vs_fawn report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def sum_trace_meta(workload: dict[str, Any], side: str, field: str) -> int:
    samples = workload.get(side, {}).get("commandSamples", [])
    total = 0
    for sample in samples:
        trace_meta = sample.get("traceMeta")
        if isinstance(trace_meta, dict):
            raw = trace_meta.get(field, 0)
            if isinstance(raw, (int, float)):
                total += int(raw)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check full matrix comparability/claimability/correctness counters."
    )
    parser.add_argument("--report", required=True, help="Path to compare report JSON.")
    parser.add_argument(
        "--expected-workloads",
        type=int,
        default=39,
        help="Expected comparable workload count (default: 39).",
    )
    parser.add_argument(
        "--allow-diagnostic-claim",
        action="store_true",
        help="Allow claimStatus=diagnostic (for non-claim probe runs).",
    )
    parser.add_argument(
        "--show-top-tail-regressions",
        type=int,
        default=10,
        help="Print up to N workloads with worst p95/p99 deltas (default: 10).",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    workloads = payload.get("workloads", [])
    workload_count = len(workloads) if isinstance(workloads, list) else 0
    comparison_status = payload.get("comparisonStatus")
    claim_status = payload.get("claimStatus")
    non_comparable = (
        payload.get("comparabilitySummary", {}) or {}
    ).get("nonComparableCount")
    non_claimable = (payload.get("claimabilitySummary", {}) or {}).get("nonClaimableCount")

    left_success_total = 0
    left_unsupported_total = 0
    left_error_total = 0
    left_success_zero = 0
    left_unsupported_workloads = 0
    left_error_workloads = 0
    tail_sorted: list[dict[str, Any]] = []
    non_claimable_details: list[dict[str, Any]] = []

    for workload in workloads:
        workload_id = workload.get("id", "<unknown>")
        success = sum_trace_meta(workload, "left", "executionSuccessCount")
        unsupported = sum_trace_meta(workload, "left", "executionUnsupportedCount")
        error = sum_trace_meta(workload, "left", "executionErrorCount")
        left_success_total += success
        left_unsupported_total += unsupported
        left_error_total += error
        if success <= 0:
            left_success_zero += 1
        if unsupported > 0:
            left_unsupported_workloads += 1
        if error > 0:
            left_error_workloads += 1

        delta = workload.get("deltaPercent") or {}
        p95 = delta.get("p95Percent")
        p99 = delta.get("p99Percent")
        if isinstance(p95, (int, float)) and isinstance(p99, (int, float)):
            tail_sorted.append({"id": workload_id, "p95": float(p95), "p99": float(p99)})

        claimability = workload.get("claimability")
        if isinstance(claimability, dict) and claimability.get("claimable") is False:
            reasons = claimability.get("reasons")
            if not isinstance(reasons, list):
                reasons = []
            non_claimable_details.append(
                {
                    "id": workload_id,
                    "reasons": [str(item) for item in reasons],
                    "p95": p95,
                    "p99": p99,
                }
            )

    print(f"report={report_path}")
    print(f"workloads={workload_count} expected={args.expected_workloads}")
    print(f"comparisonStatus={comparison_status} nonComparableCount={non_comparable}")
    print(f"claimStatus={claim_status} nonClaimableCount={non_claimable}")
    print(
        "left_totals "
        f"success={left_success_total} unsupported={left_unsupported_total} error={left_error_total}"
    )
    print(
        "left_workloads "
        f"success_zero={left_success_zero} unsupported_nonzero={left_unsupported_workloads} "
        f"error_nonzero={left_error_workloads}"
    )
    if tail_sorted:
        tail_sorted.sort(key=lambda row: (row["p95"], row["p99"]))
        limit = max(0, args.show_top_tail_regressions)
        if limit > 0:
            print("worst_tail_regressions:")
            for row in tail_sorted[:limit]:
                print(f"- {row['id']} p95={row['p95']}% p99={row['p99']}%")
    if non_claimable_details:
        print("non_claimable_workloads:")
        for row in non_claimable_details:
            reasons = " | ".join(row["reasons"]) if row["reasons"] else "no reasons listed"
            print(f"- {row['id']} p95={row['p95']} p99={row['p99']} reasons={reasons}")

    failures: list[str] = []
    if workload_count != args.expected_workloads:
        failures.append(f"workload count mismatch: {workload_count} != {args.expected_workloads}")
    if comparison_status != "comparable":
        failures.append(f"comparisonStatus is {comparison_status!r}, expected 'comparable'")
    if non_comparable != 0:
        failures.append(f"nonComparableCount is {non_comparable!r}, expected 0")
    if not args.allow_diagnostic_claim and claim_status != "claimable":
        failures.append(f"claimStatus is {claim_status!r}, expected 'claimable'")
    if left_success_zero != 0:
        failures.append(f"{left_success_zero} workload(s) have zero left executionSuccessCount")
    if left_unsupported_workloads != 0 or left_unsupported_total != 0:
        failures.append("left unsupported counters are non-zero")
    if left_error_workloads != 0 or left_error_total != 0:
        failures.append("left error counters are non-zero")

    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        return 2

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
