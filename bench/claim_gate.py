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

import report_conformance


VALID_STATUSES = {"comparable", "unreliable"}
VALID_CLAIM_STATUSES = {"claimable", "diagnostic", "not-evaluated"}
VALID_CLAIMABILITY_MODES = {"off", "local", "release"}
RELEASE_REQUIRED_POSITIVE_PERCENTILES = ["p50Percent", "p95Percent", "p99Percent"]
LOCAL_REQUIRED_POSITIVE_PERCENTILES = ["p50Percent", "p95Percent"]


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
    parser.add_argument(
        "--comparability-obligations",
        default="config/comparability-obligations.json",
        help="Canonical comparability obligation contract path.",
    )
    parser.add_argument(
        "--expected-workload-contract",
        default="",
        help=(
            "Optional workload contract JSON (for example bench/workloads.amd.vulkan.extended.json). "
            "When provided with hash/id checks, gate validates report workload contract hash and "
            "expected comparable workload ID set."
        ),
    )
    parser.add_argument(
        "--require-workload-contract-hash",
        action="store_true",
        help=(
            "Require report workloadContract.path/sha256 and verify it matches --expected-workload-contract."
        ),
    )
    parser.add_argument(
        "--require-workload-id-set-match",
        action="store_true",
        help=(
            "Require report workload IDs to exactly match comparable workload IDs from "
            "--expected-workload-contract."
        ),
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


def parse_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def parse_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            return None
        parsed.append(item)
    return parsed


def expected_positive_percentiles_for_mode(mode: str) -> list[str]:
    if mode == "release":
        return RELEASE_REQUIRED_POSITIVE_PERCENTILES
    if mode == "local":
        return LOCAL_REQUIRED_POSITIVE_PERCENTILES
    return []


def workload_runtime_hint(workload: dict[str, Any]) -> str:
    workload_id = str(workload.get("id", "unknown"))
    claimability = workload.get("claimability")
    delta = workload.get("deltaPercent")
    left = workload.get("left")
    right = workload.get("right")

    reasons: list[str] = []
    if isinstance(claimability, dict):
        raw_reasons = claimability.get("reasons")
        if isinstance(raw_reasons, list):
            reasons = [str(item) for item in raw_reasons if isinstance(item, str)]

    delta_p50 = None
    delta_p95 = None
    if isinstance(delta, dict):
        delta_p50 = parse_float(delta.get("p50Percent"))
        delta_p95 = parse_float(delta.get("p95Percent"))

    left_p50 = None
    right_p50 = None
    left_source = "unknown"
    right_source = "unknown"
    if isinstance(left, dict):
        stats = left.get("stats")
        if isinstance(stats, dict):
            left_p50 = parse_float(stats.get("p50Ms"))
        sources = left.get("timingSources")
        if isinstance(sources, list) and sources:
            left_source = str(sources[0])
    if isinstance(right, dict):
        stats = right.get("stats")
        if isinstance(stats, dict):
            right_p50 = parse_float(stats.get("p50Ms"))
        sources = right.get("timingSources")
        if isinstance(sources, list) and sources:
            right_source = str(sources[0])

    parts: list[str] = [f"{workload_id}"]
    if delta_p50 is not None:
        parts.append(f"deltaP50={delta_p50:.6f}%")
    if delta_p95 is not None:
        parts.append(f"deltaP95={delta_p95:.6f}%")
    if left_p50 is not None:
        parts.append(f"leftP50Ms={left_p50:.9f}")
    if right_p50 is not None:
        parts.append(f"rightP50Ms={right_p50:.9f}")
    parts.append(f"leftTiming={left_source}")
    parts.append(f"rightTiming={right_source}")
    if reasons:
        parts.append("reasons=" + " | ".join(reasons))
    return ", ".join(parts)


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid report format: expected object in {path}")
    return payload


def load_expected_comparable_workload_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid workload contract: expected object in {path}")
    raw_workloads = payload.get("workloads")
    if not isinstance(raw_workloads, list):
        raise ValueError(f"invalid workload contract: missing workloads[] in {path}")
    workload_ids: set[str] = set()
    for row in raw_workloads:
        if not isinstance(row, dict):
            continue
        workload_id = row.get("id")
        if not isinstance(workload_id, str) or not workload_id:
            continue
        if bool(row.get("comparable", False)):
            workload_ids.add(workload_id)
    if not workload_ids:
        raise ValueError(f"invalid workload contract: no comparable workload IDs in {path}")
    return workload_ids


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    report_path = Path(args.report)
    obligation_contract_path = Path(args.comparability_obligations)
    if not obligation_contract_path.is_absolute():
        obligation_contract_path = repo_root / obligation_contract_path
    expected_workload_contract_path = (
        Path(args.expected_workload_contract)
        if isinstance(args.expected_workload_contract, str) and args.expected_workload_contract.strip()
        else None
    )
    if expected_workload_contract_path is not None and not expected_workload_contract_path.is_absolute():
        expected_workload_contract_path = (repo_root / expected_workload_contract_path).resolve()
    if not report_path.exists():
        fail(f"missing report: {report_path}")
        return 1
    if not obligation_contract_path.exists():
        fail(f"missing comparability obligation contract: {obligation_contract_path}")
        return 1
    if (args.require_workload_contract_hash or args.require_workload_id_set_match) and (
        expected_workload_contract_path is None
    ):
        fail(
            "--require-workload-contract-hash/--require-workload-id-set-match requires "
            "--expected-workload-contract"
        )
        return 1
    if expected_workload_contract_path is not None and not expected_workload_contract_path.exists():
        fail(f"missing expected workload contract: {expected_workload_contract_path}")
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
    try:
        (
            expected_obligation_schema_version,
            expected_obligation_ids,
        ) = report_conformance.load_obligation_contract(obligation_contract_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        fail(str(exc))
        return 1
    expected_workload_hash = ""
    expected_workload_ids: set[str] = set()
    if expected_workload_contract_path is not None:
        try:
            expected_workload_hash = report_conformance.file_sha256(expected_workload_contract_path)
            expected_workload_ids = load_expected_comparable_workload_ids(
                expected_workload_contract_path
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            fail(str(exc))
            return 1

    failures: list[str] = []

    comparison_status = report.get("comparisonStatus")
    claim_status = report.get("claimStatus")
    claimability_policy = report.get("claimabilityPolicy")
    claimability_summary = report.get("claimabilitySummary")
    workloads = report.get("workloads")
    workload_contract = report.get("workloadContract")
    benchmark_policy = report.get("benchmarkPolicy")
    config_contract = report.get("configContract")
    run_parameters = report.get("runParameters")
    policy_required_positive_percentiles: list[str] = []
    policy_min_timed_samples: int | None = None

    if comparison_status != args.require_comparison_status:
        failures.append(
            "comparisonStatus mismatch: expected "
            f"{args.require_comparison_status}, got {comparison_status!r}"
        )
    if claim_status != args.require_claim_status:
        failures.append(
            f"claimStatus mismatch: expected {args.require_claim_status}, got {claim_status!r}"
        )

    if not isinstance(benchmark_policy, dict):
        failures.append("missing or invalid benchmarkPolicy object")
    else:
        benchmark_policy_path = benchmark_policy.get("path")
        benchmark_policy_sha = benchmark_policy.get("sha256")
        if not isinstance(benchmark_policy_path, str) or not benchmark_policy_path.strip():
            failures.append("benchmarkPolicy.path missing or invalid")
        if not report_conformance.is_sha256_hex(benchmark_policy_sha):
            failures.append("benchmarkPolicy.sha256 missing or invalid")

    if args.require_claimability_mode == "release":
        if not isinstance(config_contract, dict):
            failures.append(
                "missing configContract object (release claim lanes require config-backed methodology)"
            )
        else:
            config_path = config_contract.get("path")
            config_sha = config_contract.get("sha256")
            if not isinstance(config_path, str) or not config_path.strip():
                failures.append("configContract.path missing or invalid")
            if not report_conformance.is_sha256_hex(config_sha):
                failures.append("configContract.sha256 missing or invalid")

    if not isinstance(run_parameters, dict):
        failures.append("missing or invalid runParameters object")
    else:
        iterations = parse_int(run_parameters.get("iterations"))
        warmup = parse_int(run_parameters.get("warmup"))
        if iterations is None or iterations < 0:
            failures.append("runParameters.iterations missing or invalid")
        if warmup is None or warmup < 0:
            failures.append("runParameters.warmup missing or invalid")
        if (
            iterations is not None
            and warmup is not None
            and iterations - warmup < args.require_min_timed_samples
        ):
            failures.append(
                "runParameters timed sample budget below requirement: "
                f"iterations-warmup={iterations - warmup}, required >= {args.require_min_timed_samples}"
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
        policy_min_timed_samples = min_samples

        required_positive = parse_string_list(
            claimability_policy.get("requiredPositivePercentiles")
        )
        if required_positive is None:
            failures.append(
                "claimabilityPolicy.requiredPositivePercentiles missing or invalid"
            )
        else:
            expected_required = expected_positive_percentiles_for_mode(args.require_claimability_mode)
            if required_positive != expected_required:
                failures.append(
                    "claimabilityPolicy.requiredPositivePercentiles mismatch: "
                    f"expected {expected_required}, got {required_positive}"
                )
            policy_required_positive_percentiles = required_positive

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
                left_count = parse_int(
                    workload.get("left", {}).get("stats", {}).get("count")
                    if isinstance(workload.get("left"), dict)
                    else None
                )
                right_count = parse_int(
                    workload.get("right", {}).get("stats", {}).get("count")
                    if isinstance(workload.get("right"), dict)
                    else None
                )
                effective_min_timed_samples = (
                    policy_min_timed_samples
                    if policy_min_timed_samples is not None
                    else args.require_min_timed_samples
                )
                if left_count is None or left_count < effective_min_timed_samples:
                    failures.append(
                        f"{workload_id}: left.stats.count must be >= {effective_min_timed_samples}"
                    )
                if right_count is None or right_count < effective_min_timed_samples:
                    failures.append(
                        f"{workload_id}: right.stats.count must be >= {effective_min_timed_samples}"
                    )
                delta = workload.get("deltaPercent")
                if not isinstance(delta, dict):
                    failures.append(f"{workload_id}: missing deltaPercent object")
                else:
                    for percentile in policy_required_positive_percentiles:
                        value = parse_float(delta.get(percentile))
                        if value is None:
                            failures.append(
                                f"{workload_id}: deltaPercent.{percentile} missing or invalid"
                            )
                        elif value <= 0.0:
                            failures.append(
                                f"{workload_id}: deltaPercent.{percentile} must be > 0 "
                                "(positive means left faster)"
                            )
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

            workload_comparability = workload.get("comparability")
            if not isinstance(workload_comparability, dict):
                failures.append(f"{workload_id}: missing comparability object")
                continue
            comparable_flag = workload_comparability.get("comparable")
            if args.require_comparison_status == "comparable" and comparable_flag is not True:
                failures.append(f"{workload_id}: comparability.comparable must be true")
            if args.require_comparison_status == "unreliable" and comparable_flag is not False:
                failures.append(f"{workload_id}: comparability.comparable must be false")

            obligation_schema_version = parse_int(
                workload_comparability.get("obligationSchemaVersion")
            )
            if obligation_schema_version != expected_obligation_schema_version:
                failures.append(
                    f"{workload_id}: comparability.obligationSchemaVersion must be "
                    f"{expected_obligation_schema_version}"
                )

            obligations = workload_comparability.get("obligations")
            if not isinstance(obligations, list) or not obligations:
                failures.append(f"{workload_id}: comparability.obligations must be a non-empty list")
            else:
                for obligation_idx, obligation in enumerate(obligations):
                    if not isinstance(obligation, dict):
                        failures.append(
                            f"{workload_id}: comparability.obligations[{obligation_idx}] must be an object"
                        )
                        continue
                    obligation_id = obligation.get("id")
                    if not isinstance(obligation_id, str) or not obligation_id:
                        failures.append(
                            f"{workload_id}: comparability.obligations[{obligation_idx}].id must be a non-empty string"
                        )
                    elif obligation_id not in expected_obligation_ids:
                        failures.append(
                            f"{workload_id}: comparability.obligations[{obligation_idx}].id "
                            f"{obligation_id!r} is not in canonical obligation contract"
                        )
                    for field_name in ("blocking", "applicable", "passes"):
                        if not isinstance(obligation.get(field_name), bool):
                            failures.append(
                                f"{workload_id}: comparability.obligations[{obligation_idx}].{field_name} must be bool"
                            )

            blocking_failed = workload_comparability.get("blockingFailedObligations")
            if not isinstance(blocking_failed, list):
                failures.append(f"{workload_id}: comparability.blockingFailedObligations must be a list")
            else:
                for failed_idx, failed_obligation in enumerate(blocking_failed):
                    if not isinstance(failed_obligation, str) or not failed_obligation:
                        failures.append(
                            f"{workload_id}: comparability.blockingFailedObligations[{failed_idx}] "
                            "must be a non-empty string"
                        )
                    elif failed_obligation not in expected_obligation_ids:
                        failures.append(
                            f"{workload_id}: comparability.blockingFailedObligations[{failed_idx}] "
                            f"{failed_obligation!r} is not in canonical obligation contract"
                        )
                if comparable_flag is True and blocking_failed:
                    failures.append(
                        f"{workload_id}: comparable workload must not have blockingFailedObligations"
                    )

    if args.require_workload_contract_hash:
        if not isinstance(workload_contract, dict):
            failures.append("missing workloadContract object")
        else:
            report_contract_path = workload_contract.get("path")
            report_contract_hash = workload_contract.get("sha256")
            if (
                not isinstance(report_contract_path, str)
                or not report_contract_path.strip()
            ):
                failures.append("workloadContract.path missing or invalid")
            if (
                not isinstance(report_contract_hash, str)
                or not report_contract_hash.strip()
            ):
                failures.append("workloadContract.sha256 missing or invalid")
            elif report_contract_hash != expected_workload_hash:
                failures.append(
                    "workloadContract.sha256 mismatch: "
                    f"report={report_contract_hash} expected={expected_workload_hash}"
                )
            if expected_workload_contract_path is not None and isinstance(report_contract_path, str):
                resolved_report_path = report_conformance.resolve_contract_path(
                    report_path=report_path,
                    repo_root=repo_root,
                    raw_contract_path=report_contract_path,
                )
                if resolved_report_path != expected_workload_contract_path:
                    failures.append(
                        "workloadContract.path mismatch: "
                        f"report={resolved_report_path} expected={expected_workload_contract_path}"
                    )

    claim_row_hashes_ok, claim_row_hashes_error = report_conformance.validate_claim_row_hash_links(
        payload=report,
        require_config_contract=(args.require_claimability_mode == "release"),
        require_non_empty_trace_hashes=(args.require_claim_status == "claimable"),
    )
    if not claim_row_hashes_ok:
        failures.append(f"claim row hash-link validation failed: {claim_row_hashes_error}")

    if args.require_workload_id_set_match:
        report_workload_ids = {
            str(workload.get("id"))
            for workload in workloads
            if isinstance(workload, dict) and isinstance(workload.get("id"), str)
        } if isinstance(workloads, list) else set()
        missing_ids = sorted(expected_workload_ids - report_workload_ids)
        unexpected_ids = sorted(report_workload_ids - expected_workload_ids)
        if missing_ids:
            failures.append(
                "missing expected comparable workload IDs: " + ", ".join(missing_ids)
            )
        if unexpected_ids:
            failures.append(
                "unexpected comparable workload IDs in report: " + ", ".join(unexpected_ids)
            )

    if failures:
        fail("claim gate failed")
        for item in failures:
            print(item)
        if (
            args.require_claim_status == "claimable"
            and isinstance(workloads, list)
            and workloads
        ):
            print("non-claimable runtime details:")
            printed = False
            for workload in workloads:
                if not isinstance(workload, dict):
                    continue
                workload_claimability = workload.get("claimability")
                if not isinstance(workload_claimability, dict):
                    continue
                if workload_claimability.get("claimable") is True:
                    continue
                print(workload_runtime_hint(workload))
                printed = True
            if not printed:
                print("none")
        return 1

    print(
        "PASS: claim gate satisfied "
        f"(requiredMode={args.require_claimability_mode}, "
        f"comparisonStatus={comparison_status}, claimStatus={claim_status})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
