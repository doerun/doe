#!/usr/bin/env python3
"""Build machine-readable Track B rehearsal artifacts from a compare report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import report_conformance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-doe.json",
        help="Comparison report produced by compare_dawn_vs_doe.py",
    )
    parser.add_argument(
        "--out-prefix",
        default="",
        help=(
            "Artifact path prefix. Defaults to <report-without-suffix>.claim-rehearsal"
        ),
    )
    parser.add_argument(
        "--claim-gate-script",
        default="bench/claim_gate.py",
        help="claim_gate.py path used to emit canonical claim gate result artifact.",
    )
    parser.add_argument(
        "--skip-claim-gate-run",
        action="store_true",
        help="Do not run claim_gate.py; still emit all non-gate rehearsal artifacts.",
    )
    parser.add_argument(
        "--require-comparison-status",
        default="comparable",
        help="Forwarded to claim_gate.py.",
    )
    parser.add_argument(
        "--require-claim-status",
        default="claimable",
        help="Forwarded to claim_gate.py.",
    )
    parser.add_argument(
        "--require-claimability-mode",
        default="release",
        help="Forwarded to claim_gate.py.",
    )
    parser.add_argument(
        "--require-min-timed-samples",
        type=int,
        default=15,
        help="Forwarded to claim_gate.py.",
    )
    parser.add_argument(
        "--expected-workload-contract",
        default="",
        help="Optional expected workload contract path forwarded to claim_gate.py.",
    )
    parser.add_argument(
        "--require-workload-contract-hash",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Forward --require-workload-contract-hash to claim_gate.py (default: on).",
    )
    parser.add_argument(
        "--require-workload-id-set-match",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Forward --require-workload-id-set-match to claim_gate.py (default: on).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned outputs without writing artifacts.",
    )
    return parser.parse_args()


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_out_prefix(report_path: Path) -> Path:
    if report_path.suffix:
        return Path(f"{report_path.with_suffix('')}.claim-rehearsal")
    return Path(f"{report_path}.claim-rehearsal")


def list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            out.append(item)
    return out


def tail_health_table(report: dict[str, Any]) -> dict[str, Any]:
    workloads = report.get("workloads")
    if not isinstance(workloads, list):
        workloads = []

    claimability_policy = report.get("claimabilityPolicy")
    required_percentiles = list_strings(
        claimability_policy.get("requiredPositivePercentiles")
        if isinstance(claimability_policy, dict)
        else []
    )
    delta_keys = ["p50Percent", "p95Percent", "p99Percent"]
    rows: list[dict[str, Any]] = []
    non_positive_counts = {key: 0 for key in delta_keys}
    claimable_rows = 0
    all_required_positive_rows = 0

    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        workload_id = workload.get("id")
        if not isinstance(workload_id, str) or not workload_id:
            workload_id = "unknown"
        delta = workload.get("deltaPercent")
        claimability = workload.get("claimability")
        if not isinstance(delta, dict):
            delta = {}
        if not isinstance(claimability, dict):
            claimability = {}
        claimable = claimability.get("claimable") is True
        if claimable:
            claimable_rows += 1

        positive_flags: dict[str, bool | None] = {}
        for key in delta_keys:
            value = parse_float(delta.get(key))
            if value is None:
                positive_flags[key] = None
                non_positive_counts[key] += 1
            else:
                is_positive = value > 0.0
                positive_flags[key] = is_positive
                if not is_positive:
                    non_positive_counts[key] += 1

        all_required_positive = all(
            positive_flags.get(key) is True for key in required_percentiles
        )
        if all_required_positive:
            all_required_positive_rows += 1

        rows.append(
            {
                "workloadId": workload_id,
                "claimable": claimable,
                "requiredPositivePercentiles": required_percentiles,
                "deltaPercent": {
                    key: parse_float(delta.get(key))
                    for key in delta_keys
                },
                "positiveTailFlags": positive_flags,
                "allRequiredPositive": all_required_positive,
            }
        )

    return {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "reportPath": report.get("outPath", ""),
        "requiredPositivePercentiles": required_percentiles,
        "workloadCount": len(rows),
        "claimableWorkloadCount": claimable_rows,
        "allRequiredPositiveCount": all_required_positive_rows,
        "nonPositiveCounts": non_positive_counts,
        "rows": rows,
    }


def timing_invariant_audit(report: dict[str, Any]) -> dict[str, Any]:
    workloads = report.get("workloads")
    if not isinstance(workloads, list):
        workloads = []

    comparability_policy = report.get("comparabilityPolicy")
    required_timing_class = (
        comparability_policy.get("requiredTimingClass")
        if isinstance(comparability_policy, dict)
        else ""
    )
    if not isinstance(required_timing_class, str):
        required_timing_class = ""

    rows: list[dict[str, Any]] = []
    failure_counts = {
        "leftSingleTimingClass": 0,
        "rightSingleTimingClass": 0,
        "leftRightTimingClassMatch": 0,
        "requiredTimingClassSatisfied": 0,
        "normalizationDivisorsPositive": 0,
        "commandRepeatPositive": 0,
        "ignoreFirstNonNegative": 0,
        "submitCadencePositive": 0,
    }

    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        workload_id = workload.get("id")
        if not isinstance(workload_id, str) or not workload_id:
            workload_id = "unknown"
        left = workload.get("left")
        right = workload.get("right")
        normalization = workload.get("timingNormalization")
        comparability = workload.get("comparability")
        if not isinstance(left, dict):
            left = {}
        if not isinstance(right, dict):
            right = {}
        if not isinstance(normalization, dict):
            normalization = {}
        if not isinstance(comparability, dict):
            comparability = {}

        left_classes = list_strings(left.get("timingClasses"))
        right_classes = list_strings(right.get("timingClasses"))
        left_sources = list_strings(left.get("timingSources"))
        right_sources = list_strings(right.get("timingSources"))

        left_single_timing_class = bool(left_classes) and len(set(left_classes)) == 1
        right_single_timing_class = bool(right_classes) and len(set(right_classes)) == 1
        left_right_timing_class_match = (
            bool(left_classes)
            and bool(right_classes)
            and set(left_classes) == set(right_classes)
        )
        required_timing_class_satisfied = (
            required_timing_class in ("", "any")
            or (
                bool(left_classes or right_classes)
                and all(
                    cls == required_timing_class
                    for cls in [*left_classes, *right_classes]
                )
            )
        )

        left_divisor = parse_float(normalization.get("leftDivisor"))
        right_divisor = parse_float(normalization.get("rightDivisor"))
        left_repeat = parse_int(normalization.get("leftCommandRepeat"))
        right_repeat = parse_int(normalization.get("rightCommandRepeat"))
        left_ignore_first = parse_int(normalization.get("leftIgnoreFirstOps"))
        right_ignore_first = parse_int(normalization.get("rightIgnoreFirstOps"))
        left_submit_every = parse_int(normalization.get("leftUploadSubmitEvery"))
        right_submit_every = parse_int(normalization.get("rightUploadSubmitEvery"))

        normalization_divisors_positive = (
            left_divisor is not None
            and left_divisor > 0.0
            and right_divisor is not None
            and right_divisor > 0.0
        )
        command_repeat_positive = (
            left_repeat is not None
            and left_repeat >= 1
            and right_repeat is not None
            and right_repeat >= 1
        )
        ignore_first_non_negative = (
            left_ignore_first is not None
            and left_ignore_first >= 0
            and right_ignore_first is not None
            and right_ignore_first >= 0
        )
        submit_cadence_positive = (
            left_submit_every is not None
            and left_submit_every >= 1
            and right_submit_every is not None
            and right_submit_every >= 1
        )

        invariants = {
            "leftSingleTimingClass": left_single_timing_class,
            "rightSingleTimingClass": right_single_timing_class,
            "leftRightTimingClassMatch": left_right_timing_class_match,
            "requiredTimingClassSatisfied": required_timing_class_satisfied,
            "normalizationDivisorsPositive": normalization_divisors_positive,
            "commandRepeatPositive": command_repeat_positive,
            "ignoreFirstNonNegative": ignore_first_non_negative,
            "submitCadencePositive": submit_cadence_positive,
        }
        for key, passes in invariants.items():
            if not passes:
                failure_counts[key] += 1

        rows.append(
            {
                "workloadId": workload_id,
                "comparable": comparability.get("comparable"),
                "requiredTimingClass": required_timing_class,
                "leftTimingClasses": left_classes,
                "rightTimingClasses": right_classes,
                "leftTimingSources": left_sources,
                "rightTimingSources": right_sources,
                "timingNormalization": {
                    "leftDivisor": left_divisor,
                    "rightDivisor": right_divisor,
                    "leftCommandRepeat": left_repeat,
                    "rightCommandRepeat": right_repeat,
                    "leftIgnoreFirstOps": left_ignore_first,
                    "rightIgnoreFirstOps": right_ignore_first,
                    "leftUploadSubmitEvery": left_submit_every,
                    "rightUploadSubmitEvery": right_submit_every,
                },
                "invariants": invariants,
            }
        )

    return {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "requiredTimingClass": required_timing_class,
        "workloadCount": len(rows),
        "failureCounts": failure_counts,
        "rows": rows,
    }


def contract_hash_manifest(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    workload_contract = report.get("workloadContract")
    benchmark_policy = report.get("benchmarkPolicy")
    config_contract = report.get("configContract")
    claim_row_hash_chain = report.get("claimRowHashChain")
    run_parameters = report.get("runParameters")
    claimability_policy = report.get("claimabilityPolicy")
    comparability_policy = report.get("comparabilityPolicy")
    workloads = report.get("workloads")
    if not isinstance(workloads, list):
        workloads = []

    if not isinstance(workload_contract, dict):
        workload_contract = {}
    if not isinstance(benchmark_policy, dict):
        benchmark_policy = {}
    if not isinstance(config_contract, dict):
        config_contract = {}
    if not isinstance(claim_row_hash_chain, dict):
        claim_row_hash_chain = {}
    if not isinstance(run_parameters, dict):
        run_parameters = {}
    if not isinstance(claimability_policy, dict):
        claimability_policy = {}
    if not isinstance(comparability_policy, dict):
        comparability_policy = {}

    trace_hashes: list[dict[str, Any]] = []
    claim_row_hashes: list[dict[str, Any]] = []
    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        workload_id = workload.get("id")
        if not isinstance(workload_id, str) or not workload_id:
            workload_id = "unknown"
        trace_meta_hashes = workload.get("traceMetaHashes")
        claim_row_hash = workload.get("claimRowHash")
        if not isinstance(trace_meta_hashes, dict):
            trace_meta_hashes = {}
        if not isinstance(claim_row_hash, dict):
            claim_row_hash = {}
        left_trace_hashes = list_strings(
            [
                row.get("sha256")
                for row in trace_meta_hashes.get("left", [])
                if isinstance(row, dict)
            ]
            if isinstance(trace_meta_hashes.get("left"), list)
            else []
        )
        right_trace_hashes = list_strings(
            [
                row.get("sha256")
                for row in trace_meta_hashes.get("right", [])
                if isinstance(row, dict)
            ]
            if isinstance(trace_meta_hashes.get("right"), list)
            else []
        )
        trace_hashes.append(
            {
                "workloadId": workload_id,
                "leftTraceMetaSha256": left_trace_hashes,
                "rightTraceMetaSha256": right_trace_hashes,
            }
        )
        claim_row_hashes.append(
            {
                "workloadId": workload_id,
                "previousHash": claim_row_hash.get("previousHash", ""),
                "hash": claim_row_hash.get("hash", ""),
            }
        )

    active_contract_hash = report_conformance.json_sha256(
        {
            "workloadContractSha256": workload_contract.get("sha256", ""),
            "configContractSha256": config_contract.get("sha256", ""),
            "benchmarkPolicySha256": benchmark_policy.get("sha256", ""),
            "runParameters": {
                "iterations": run_parameters.get("iterations"),
                "warmup": run_parameters.get("warmup"),
            },
            "comparabilityPolicy": {
                "mode": comparability_policy.get("mode"),
                "requiredTimingClass": comparability_policy.get("requiredTimingClass"),
            },
            "claimabilityPolicy": {
                "mode": claimability_policy.get("mode"),
                "minTimedSamples": claimability_policy.get("minTimedSamples"),
                "requiredPositivePercentiles": claimability_policy.get(
                    "requiredPositivePercentiles"
                ),
            },
        }
    )

    return {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "reportPath": str(report_path),
        "reportSha256": report_conformance.file_sha256(report_path),
        "activeContractHash": active_contract_hash,
        "workloadContract": {
            "path": workload_contract.get("path", ""),
            "sha256": workload_contract.get("sha256", ""),
        },
        "configContract": {
            "path": config_contract.get("path", ""),
            "sha256": config_contract.get("sha256", ""),
        },
        "benchmarkPolicy": {
            "path": benchmark_policy.get("path", ""),
            "sha256": benchmark_policy.get("sha256", ""),
        },
        "runParameters": {
            "iterations": run_parameters.get("iterations"),
            "warmup": run_parameters.get("warmup"),
        },
        "claimRowHashChain": {
            "algorithm": claim_row_hash_chain.get("algorithm", ""),
            "count": claim_row_hash_chain.get("count", 0),
            "startPreviousHash": claim_row_hash_chain.get("startPreviousHash", ""),
            "finalHash": claim_row_hash_chain.get("finalHash", ""),
        },
        "workloadTraceMetaHashes": trace_hashes,
        "workloadClaimRowHashes": claim_row_hashes,
    }


def run_claim_gate(
    *,
    args: argparse.Namespace,
    report_path: Path,
) -> dict[str, Any]:
    if args.skip_claim_gate_run:
        return {
            "schemaVersion": 1,
            "generatedAtUtc": utc_now(),
            "executed": False,
            "passed": None,
            "returnCode": None,
            "command": [],
            "stdout": "",
            "stderr": "",
        }

    claim_gate_script = Path(args.claim_gate_script)
    command = [
        sys.executable,
        str(claim_gate_script),
        "--report",
        str(report_path),
        "--require-comparison-status",
        args.require_comparison_status,
        "--require-claim-status",
        args.require_claim_status,
        "--require-claimability-mode",
        args.require_claimability_mode,
        "--require-min-timed-samples",
        str(args.require_min_timed_samples),
    ]
    if args.expected_workload_contract.strip():
        command.extend(["--expected-workload-contract", args.expected_workload_contract])
    if args.require_workload_contract_hash:
        command.append("--require-workload-contract-hash")
    if args.require_workload_id_set_match:
        command.append("--require-workload-id-set-match")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "executed": True,
        "passed": completed.returncode == 0,
        "returnCode": completed.returncode,
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    args = parse_args()
    if args.require_min_timed_samples < 0:
        print(
            "FAIL: invalid --require-min-timed-samples="
            f"{args.require_min_timed_samples} expected >= 0"
        )
        return 1

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"FAIL: missing report: {report_path}")
        return 1

    out_prefix = (
        Path(args.out_prefix)
        if isinstance(args.out_prefix, str) and args.out_prefix.strip()
        else default_out_prefix(report_path)
    )
    claim_gate_result_path = Path(f"{out_prefix}.claim-gate-result.json")
    tail_health_path = Path(f"{out_prefix}.tail-health.json")
    timing_audit_path = Path(f"{out_prefix}.timing-invariant-audit.json")
    contract_manifest_path = Path(f"{out_prefix}.contract-hash-manifest.json")
    rehearsal_manifest_path = Path(f"{out_prefix}.manifest.json")

    if args.dry_run:
        print(f"[dry-run] report: {report_path}")
        print(f"[dry-run] claim gate result: {claim_gate_result_path}")
        print(f"[dry-run] tail health: {tail_health_path}")
        print(f"[dry-run] timing invariant audit: {timing_audit_path}")
        print(f"[dry-run] contract hash manifest: {contract_manifest_path}")
        print(f"[dry-run] rehearsal manifest: {rehearsal_manifest_path}")
        return 0

    try:
        report = load_json(report_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1

    tail_health_payload = tail_health_table(report)
    timing_audit_payload = timing_invariant_audit(report)
    contract_manifest_payload = contract_hash_manifest(report, report_path)
    claim_gate_result_payload = run_claim_gate(args=args, report_path=report_path)

    write_json(tail_health_path, tail_health_payload)
    write_json(timing_audit_path, timing_audit_payload)
    write_json(contract_manifest_path, contract_manifest_payload)
    write_json(claim_gate_result_path, claim_gate_result_payload)

    rehearsal_manifest_payload = {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "reportPath": str(report_path),
        "strictComparableReportPath": str(report_path),
        "claimGateResultPath": str(claim_gate_result_path),
        "tailHealthPath": str(tail_health_path),
        "timingInvariantAuditPath": str(timing_audit_path),
        "contractHashManifestPath": str(contract_manifest_path),
        "claimGatePassed": claim_gate_result_payload.get("passed"),
        "claimGateReturnCode": claim_gate_result_payload.get("returnCode"),
    }
    write_json(rehearsal_manifest_path, rehearsal_manifest_payload)

    print("PASS: claim rehearsal artifacts generated")
    print(f"manifest: {rehearsal_manifest_path}")

    if claim_gate_result_payload.get("executed") and claim_gate_result_payload.get("returnCode") != 0:
        return int(claim_gate_result_payload["returnCode"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
