#!/usr/bin/env python3
"""Blocking substantiation gate for release claim trend evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import output_paths


@dataclass(frozen=True)
class ReleaseEvidencePolicy:
    min_reports: int
    min_claimable_comparable_reports: int
    required_comparison_status: str
    required_claim_status: str
    min_unique_left_profiles: int
    target_unique_left_profiles: int | None
    enforce_target_unique_left_profiles: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        default="config/substantiation-policy.json",
        help="Substantiation policy JSON path.",
    )
    parser.add_argument(
        "--summary",
        action="append",
        default=[],
        help=(
            "release-claim-windows summary artifact path. "
            "May be repeated."
        ),
    )
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        help="Comparison report path. May be repeated.",
    )
    parser.add_argument(
        "--out",
        default="bench/out/substantiation_report.json",
        help="Gate output report path.",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for output report path (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp output report path with a UTC timestamp suffix.",
    )
    parser.add_argument(
        "--enforce-target-unique-left-profiles",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Override policy behavior for targetUniqueLeftProfiles enforcement. "
            "By default, follows releaseEvidence.enforceTargetUniqueLeftProfiles."
        ),
    )
    return parser.parse_args()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def load_policy(path: Path) -> ReleaseEvidencePolicy:
    payload = load_json_object(path)
    release_evidence = payload.get("releaseEvidence")
    if not isinstance(release_evidence, dict):
        raise ValueError("invalid policy: missing object field releaseEvidence")

    target_unique_left_profiles = release_evidence.get("targetUniqueLeftProfiles")
    if target_unique_left_profiles is not None and not isinstance(target_unique_left_profiles, int):
        raise ValueError("invalid policy: targetUniqueLeftProfiles must be int when present")
    enforce_target_unique_left_profiles = release_evidence.get("enforceTargetUniqueLeftProfiles")
    if not isinstance(enforce_target_unique_left_profiles, bool):
        raise ValueError("invalid policy: enforceTargetUniqueLeftProfiles must be boolean")

    return ReleaseEvidencePolicy(
        min_reports=int(release_evidence.get("minReports", 0)),
        min_claimable_comparable_reports=int(release_evidence.get("minClaimableComparableReports", 0)),
        required_comparison_status=str(release_evidence.get("requiredComparisonStatus", "")),
        required_claim_status=str(release_evidence.get("requiredClaimStatus", "")),
        min_unique_left_profiles=int(release_evidence.get("minUniqueLeftProfiles", 0)),
        target_unique_left_profiles=target_unique_left_profiles,
        enforce_target_unique_left_profiles=enforce_target_unique_left_profiles,
    )


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect_report_paths(summaries: list[str], reports: list[str]) -> tuple[list[Path], list[str]]:
    failures: list[str] = []
    discovered: list[Path] = []
    seen: set[str] = set()

    for report in reports:
        candidate = Path(report)
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        discovered.append(candidate)

    for summary in summaries:
        summary_path = Path(summary)
        if not summary_path.exists():
            failures.append(f"missing summary artifact: {summary_path}")
            continue
        try:
            summary_payload = load_json_object(summary_path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            failures.append(f"{summary_path}: failed to parse summary json: {exc}")
            continue

        windows = summary_payload.get("windows")
        if not isinstance(windows, list):
            failures.append(f"{summary_path}: invalid summary format (missing list field windows)")
            continue

        for window_idx, window in enumerate(windows):
            if not isinstance(window, dict):
                failures.append(f"{summary_path}: windows[{window_idx}] is not an object")
                continue
            report_path = window.get("reportPath")
            if not isinstance(report_path, str) or not report_path.strip():
                failures.append(f"{summary_path}: windows[{window_idx}] missing non-empty reportPath")
                continue
            candidate = Path(report_path)
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            discovered.append(candidate)

    return discovered, failures


def extract_profile_from_meta(meta: dict[str, Any]) -> str | None:
    profile = meta.get("profile")
    if not isinstance(profile, dict):
        return None
    vendor = profile.get("vendor")
    api = profile.get("api")
    driver = profile.get("driver")
    if not isinstance(vendor, str) or not vendor.strip():
        return None
    if not isinstance(api, str) or not api.strip():
        return None
    if not isinstance(driver, str) or not driver.strip():
        return None
    family = profile.get("deviceFamily")
    family_value = ""
    if isinstance(family, str):
        family_value = family.strip()
    return "|".join([vendor.strip(), api.strip(), family_value, driver.strip()])


def extract_left_profile_ids(report_payload: dict[str, Any]) -> set[str]:
    profile_ids: set[str] = set()
    workloads = report_payload.get("workloads")
    if not isinstance(workloads, list):
        return profile_ids

    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        left = workload.get("left")
        if not isinstance(left, dict):
            continue
        samples = left.get("commandSamples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            return_code = sample.get("returnCode")
            if not isinstance(return_code, int) or return_code != 0:
                continue
            trace_meta = sample.get("traceMeta")
            if not isinstance(trace_meta, dict):
                continue
            profile_id = extract_profile_from_meta(trace_meta)
            if profile_id is not None:
                profile_ids.add(profile_id)
    return profile_ids


def main() -> int:
    args = parse_args()

    policy_path = Path(args.policy)
    if not policy_path.exists():
        print(f"FAIL: missing policy: {policy_path}")
        return 1

    try:
        policy = load_policy(policy_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: invalid policy: {exc}")
        return 1

    if policy.min_reports <= 0:
        print(f"FAIL: invalid policy minReports={policy.min_reports} expected > 0")
        return 1
    if policy.min_claimable_comparable_reports <= 0:
        print(
            "FAIL: invalid policy minClaimableComparableReports="
            f"{policy.min_claimable_comparable_reports} expected > 0"
        )
        return 1
    if not policy.required_comparison_status:
        print("FAIL: invalid policy requiredComparisonStatus must be non-empty")
        return 1
    if not policy.required_claim_status:
        print("FAIL: invalid policy requiredClaimStatus must be non-empty")
        return 1
    if policy.min_unique_left_profiles <= 0:
        print(
            "FAIL: invalid policy minUniqueLeftProfiles="
            f"{policy.min_unique_left_profiles} expected > 0"
        )
        return 1
    if (
        policy.target_unique_left_profiles is not None
        and policy.target_unique_left_profiles < policy.min_unique_left_profiles
    ):
        print(
            "FAIL: invalid policy targetUniqueLeftProfiles must be >= minUniqueLeftProfiles "
            f"(target={policy.target_unique_left_profiles} min={policy.min_unique_left_profiles})"
        )
        return 1
    effective_enforce_target_unique_left_profiles = (
        policy.enforce_target_unique_left_profiles
        if args.enforce_target_unique_left_profiles is None
        else bool(args.enforce_target_unique_left_profiles)
    )

    report_paths, collection_failures = collect_report_paths(args.summary, args.report)
    failures: list[str] = list(collection_failures)
    warnings: list[str] = []
    report_summaries: list[dict[str, Any]] = []

    qualifying_reports = 0
    aggregated_left_profiles: set[str] = set()
    for report_path in report_paths:
        if not report_path.exists():
            failures.append(f"missing comparison report: {report_path}")
            continue
        try:
            report_payload = load_json_object(report_path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            failures.append(f"{report_path}: failed to parse comparison report: {exc}")
            continue

        comparison_status = report_payload.get("comparisonStatus")
        claim_status = report_payload.get("claimStatus")
        status_pass = (
            comparison_status == policy.required_comparison_status
            and claim_status == policy.required_claim_status
        )
        if status_pass:
            qualifying_reports += 1

        left_profiles = extract_left_profile_ids(report_payload)
        aggregated_left_profiles.update(left_profiles)
        report_summaries.append(
            {
                "path": str(report_path),
                "comparisonStatus": comparison_status,
                "claimStatus": claim_status,
                "statusPass": status_pass,
                "leftProfileCount": len(left_profiles),
                "leftProfiles": sorted(left_profiles),
            }
        )

    if len(report_paths) < policy.min_reports:
        failures.append(
            "insufficient reports for substantiation: "
            f"required>={policy.min_reports} actual={len(report_paths)}"
        )
    if qualifying_reports < policy.min_claimable_comparable_reports:
        failures.append(
            "insufficient claimable+comparable reports: "
            f"required>={policy.min_claimable_comparable_reports} actual={qualifying_reports}"
        )
    if len(aggregated_left_profiles) < policy.min_unique_left_profiles:
        failures.append(
            "insufficient unique left profiles for device/driver confidence: "
            f"required>={policy.min_unique_left_profiles} actual={len(aggregated_left_profiles)}"
        )
    if (
        policy.target_unique_left_profiles is not None
        and len(aggregated_left_profiles) < policy.target_unique_left_profiles
    ):
        target_failure = (
            "target unique left profile diversity not reached: "
            f"target={policy.target_unique_left_profiles} actual={len(aggregated_left_profiles)}"
        )
        if effective_enforce_target_unique_left_profiles:
            failures.append(target_failure)
        else:
            warnings.append(target_failure)

    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )
    out_path = output_paths.with_timestamp(
        args.out,
        output_timestamp,
        enabled=args.timestamp_output,
    )
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "outputTimestamp": output_timestamp,
        "policyPath": str(policy_path),
        "policy": {
            "minReports": policy.min_reports,
            "minClaimableComparableReports": policy.min_claimable_comparable_reports,
            "requiredComparisonStatus": policy.required_comparison_status,
            "requiredClaimStatus": policy.required_claim_status,
            "minUniqueLeftProfiles": policy.min_unique_left_profiles,
            "targetUniqueLeftProfiles": policy.target_unique_left_profiles,
            "enforceTargetUniqueLeftProfiles": policy.enforce_target_unique_left_profiles,
            "effectiveEnforceTargetUniqueLeftProfiles": effective_enforce_target_unique_left_profiles,
        },
        "reportCount": len(report_paths),
        "qualifyingReportCount": qualifying_reports,
        "uniqueLeftProfileCount": len(aggregated_left_profiles),
        "uniqueLeftProfiles": sorted(aggregated_left_profiles),
        "reports": report_summaries,
        "warnings": warnings,
        "failures": failures,
        "pass": len(failures) == 0,
    }
    write_report(out_path, payload)
    output_paths.write_run_manifest_for_outputs(
        [out_path],
        {
            "runType": "substantiation_gate",
            "config": {
                "policy": str(policy_path),
                "summaryCount": len(args.summary),
                "reportCount": len(args.report),
                "effectiveEnforceTargetUniqueLeftProfiles": effective_enforce_target_unique_left_profiles,
            },
            "fullRun": True,
            "claimGateRan": False,
            "dropinGateRan": False,
            "reportPath": str(out_path),
            "status": "passed" if payload["pass"] else "failed",
        },
    )

    if failures:
        print("FAIL: substantiation gate")
        for failure in failures:
            print(f"  {failure}")
        if warnings:
            print("WARN:")
            for warning in warnings:
                print(f"  {warning}")
        print(f"report: {out_path}")
        return 1

    print("PASS: substantiation gate")
    if warnings:
        print("WARN:")
        for warning in warnings:
            print(f"  {warning}")
    print(f"report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
