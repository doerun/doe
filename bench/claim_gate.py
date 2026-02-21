#!/usr/bin/env python3
"""
Release hard-gate for claimability and comparability status.

Validates that a compare_dawn_vs_fawn.py report is explicitly release-claimable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VALID_STATUSES = {"comparable", "unreliable"}
VALID_CLAIM_STATUSES = {"claimable", "diagnostic", "not-evaluated"}
VALID_CLAIMABILITY_MODES = {"off", "local", "release"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-fawn.json",
        help="Comparison report produced by compare_dawn_vs_fawn.py",
    )
    parser.add_argument(
        "--require-comparison-status",
        default="comparable",
        help="Required top-level comparisonStatus value",
    )
    parser.add_argument(
        "--require-claim-status",
        default="claimable",
        help="Required top-level claimStatus value",
    )
    parser.add_argument(
        "--require-claimability-mode",
        default="release",
        help="Required claimabilityPolicy.mode value",
    )
    parser.add_argument(
        "--require-min-timed-samples",
        type=int,
        default=15,
        help="Minimum claimabilityPolicy.minTimedSamples value",
    )
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"FAIL: {message}")


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid report format: expected object in {path}")
    return payload


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        fail(f"missing report: {report_path}")
        return 1

    if args.require_comparison_status not in VALID_STATUSES:
        fail(
            "invalid --require-comparison-status="
            f"{args.require_comparison_status} expected one of {sorted(VALID_STATUSES)}"
        )
        return 1
    if args.require_claim_status not in VALID_CLAIM_STATUSES:
        fail(
            "invalid --require-claim-status="
            f"{args.require_claim_status} expected one of {sorted(VALID_CLAIM_STATUSES)}"
        )
        return 1
    if args.require_claimability_mode not in VALID_CLAIMABILITY_MODES:
        fail(
            "invalid --require-claimability-mode="
            f"{args.require_claimability_mode} expected one of {sorted(VALID_CLAIMABILITY_MODES)}"
        )
        return 1
    if args.require_min_timed_samples < 0:
        fail(
            "invalid --require-min-timed-samples="
            f"{args.require_min_timed_samples} expected >= 0"
        )
        return 1

    try:
        report = load_report(report_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        fail(str(exc))
        return 1

    failures: list[str] = []

    comparison_status = report.get("comparisonStatus")
    claim_status = report.get("claimStatus")
    claimability_policy = report.get("claimabilityPolicy")
    claimability_summary = report.get("claimabilitySummary")
    workloads = report.get("workloads")

    if comparison_status != args.require_comparison_status:
        failures.append(
            "comparisonStatus mismatch: expected "
            f"{args.require_comparison_status}, got {comparison_status!r}"
        )
    if claim_status != args.require_claim_status:
        failures.append(
            f"claimStatus mismatch: expected {args.require_claim_status}, got {claim_status!r}"
        )

    if not isinstance(claimability_policy, dict):
        failures.append("missing or invalid claimabilityPolicy object")
    else:
        mode = claimability_policy.get("mode")
        if mode != args.require_claimability_mode:
            failures.append(
                "claimabilityPolicy.mode mismatch: expected "
                f"{args.require_claimability_mode}, got {mode!r}"
            )

        min_samples = parse_int(claimability_policy.get("minTimedSamples"))
        if min_samples is None:
            failures.append("claimabilityPolicy.minTimedSamples missing or invalid")
        elif min_samples < args.require_min_timed_samples:
            failures.append(
                "claimabilityPolicy.minTimedSamples below requirement: "
                f"required >= {args.require_min_timed_samples}, got {min_samples}"
            )

    if not isinstance(claimability_summary, dict):
        failures.append("missing or invalid claimabilitySummary object")
    else:
        non_claimable_count = parse_int(claimability_summary.get("nonClaimableCount"))
        if non_claimable_count is None:
            failures.append("claimabilitySummary.nonClaimableCount missing or invalid")
        elif args.require_claim_status == "claimable" and non_claimable_count != 0:
            failures.append(
                "claimabilitySummary.nonClaimableCount must be 0 for claimable reports "
                f"(got {non_claimable_count})"
            )
        elif args.require_claim_status == "diagnostic" and non_claimable_count == 0:
            failures.append(
                "claimabilitySummary.nonClaimableCount must be > 0 for diagnostic reports"
            )

    if not isinstance(workloads, list):
        failures.append("missing or invalid workloads list")
    elif not workloads:
        failures.append("workloads list is empty")
    else:
        for index, workload in enumerate(workloads):
            if not isinstance(workload, dict):
                failures.append(f"workloads[{index}] is not an object")
                continue
            workload_id = workload.get("id", f"workload[{index}]")
            workload_claimability = workload.get("claimability")
            if not isinstance(workload_claimability, dict):
                failures.append(f"{workload_id}: missing claimability object")
                continue
            evaluated = workload_claimability.get("evaluated")
            claimable = workload_claimability.get("claimable")
            if args.require_claim_status == "claimable":
                if evaluated is not True:
                    failures.append(f"{workload_id}: claimability.evaluated must be true")
                if claimable is not True:
                    failures.append(f"{workload_id}: claimability.claimable must be true")
            elif args.require_claim_status == "diagnostic":
                if evaluated is not True:
                    failures.append(f"{workload_id}: claimability.evaluated must be true")
                if claimable is not False:
                    failures.append(f"{workload_id}: claimability.claimable must be false")
            elif args.require_claim_status == "not-evaluated":
                if evaluated is not False:
                    failures.append(f"{workload_id}: claimability.evaluated must be false")
                if claimable is not None:
                    failures.append(f"{workload_id}: claimability.claimable must be null")

    if failures:
        fail("claim gate failed")
        for item in failures:
            print(item)
        return 1

    print(
        "PASS: claim gate satisfied "
        f"(requiredMode={args.require_claimability_mode}, "
        f"comparisonStatus={comparison_status}, claimStatus={claim_status})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
