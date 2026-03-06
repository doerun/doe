#!/usr/bin/env python3
"""Build a normalized benchmark cube from backend and package compare reports."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from statistics import median
from typing import Any

import jsonschema

import benchmark_cube_dashboard_html
import output_paths
import report_conformance


STATUS_ORDER = {
    "unsupported": 0,
    "unimplemented": 1,
    "diagnostic": 2,
    "comparable": 3,
    "claimable": 4,
}


def degrade_status_for_conformance(status: str, source_conformance: str) -> str:
    if source_conformance == "legacy_nonconformant" and status in {"comparable", "claimable"}:
        return "diagnostic"
    return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend-report-glob",
        action="append",
        default=[],
        help=(
            "Glob for backend Dawn-vs-Doe compare reports. May be repeated. "
            "Default: bench/out/**/dawn-vs-doe*.json"
        ),
    )
    parser.add_argument(
        "--backend-report",
        action="append",
        default=[],
        help="Explicit backend compare report path. May be repeated.",
    )
    parser.add_argument(
        "--node-report-glob",
        action="append",
        default=[],
        help=(
            "Glob for Node package compare reports. May be repeated. "
            "Default: bench/out/node-doe-vs-dawn/*.json"
        ),
    )
    parser.add_argument(
        "--node-report",
        action="append",
        default=[],
        help="Explicit Node package compare report path. May be repeated.",
    )
    parser.add_argument(
        "--bun-report-glob",
        action="append",
        default=[],
        help=(
            "Glob for Bun package compare reports. May be repeated. "
            "Default: bench/out/bun-doe-vs-webgpu/*.json"
        ),
    )
    parser.add_argument(
        "--bun-report",
        action="append",
        default=[],
        help="Explicit Bun package compare report path. May be repeated.",
    )
    parser.add_argument(
        "--policy",
        default="config/benchmark-cube-policy.json",
        help="Benchmark cube policy contract.",
    )
    parser.add_argument(
        "--comparability-obligations",
        default="config/comparability-obligations.json",
        help="Canonical comparability obligation contract for backend report conformance.",
    )
    parser.add_argument(
        "--summary-out",
        default="bench/out/cube/cube.summary.json",
        help="Output JSON summary path.",
    )
    parser.add_argument(
        "--rows-out",
        default="bench/out/cube/cube.rows.json",
        help="Output JSON rows path.",
    )
    parser.add_argument(
        "--matrix-md-out",
        default="bench/out/cube/cube.matrix.md",
        help="Output markdown matrix path.",
    )
    parser.add_argument(
        "--dashboard-html-out",
        default="bench/out/cube/cube.dashboard.html",
        help="Output HTML dashboard path.",
    )
    parser.add_argument(
        "--latest-summary",
        default="bench/out/cube/latest/cube.summary.json",
        help="Stable latest summary path.",
    )
    parser.add_argument(
        "--latest-rows",
        default="bench/out/cube/latest/cube.rows.json",
        help="Stable latest rows path.",
    )
    parser.add_argument(
        "--latest-matrix-md",
        default="bench/out/cube/latest/cube.matrix.md",
        help="Stable latest markdown matrix path.",
    )
    parser.add_argument(
        "--latest-dashboard-html",
        default="bench/out/cube/latest/cube.dashboard.html",
        help="Stable latest HTML dashboard path.",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for timestamped outputs (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp output artifact paths with a UTC timestamp suffix.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_object(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def parse_utc_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_report_timestamp(payload: dict[str, Any], source_path: Path) -> datetime:
    generated_at = parse_utc_iso(payload.get("generatedAt"))
    if generated_at is not None:
        return generated_at
    timestamp = parse_utc_iso(payload.get("timestamp"))
    if timestamp is not None:
        return timestamp
    output_timestamp = payload.get("outputTimestamp")
    if isinstance(output_timestamp, str) and output_timestamp:
        return datetime.strptime(output_timestamp, output_paths.TIMESTAMP_FORMAT).replace(
            tzinfo=timezone.utc
        )
    parts = source_path.stem.split(".")
    if parts:
        candidate = parts[-1]
        if len(candidate) == len("20260306T195054Z"):
            try:
                return datetime.strptime(candidate, output_paths.TIMESTAMP_FORMAT).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass
    return datetime.fromtimestamp(source_path.stat().st_mtime, tz=timezone.utc)


def run_id_from_timestamp(value: datetime) -> str:
    return value.strftime(output_paths.TIMESTAMP_FORMAT)


def safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def collect_paths(patterns: list[str], explicit_paths: list[str]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for raw in explicit_paths:
        path = Path(raw)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(path)
    for pattern in patterns:
        for raw in sorted(glob(pattern, recursive=True)):
            path = Path(raw)
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path)
    return candidates


def is_scratch_namespace_path(path: Path) -> bool:
    parts = path.parts
    for idx in range(len(parts) - 2):
        if parts[idx] == "bench" and parts[idx + 1] == "out" and parts[idx + 2] == "scratch":
            return True
    return False


def validate_schema(schema_path: Path, payload: Any) -> None:
    schema_payload = load_json(schema_path)
    validator = jsonschema.Draft202012Validator(schema_payload)
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if not errors:
        return
    first = errors[0]
    location = ".".join(str(part) for part in first.absolute_path) if first.absolute_path else "<root>"
    raise ValueError(f"{schema_path}: {location}: {first.message}")


def validate_backend_report_shape(payload: dict[str, Any], *, report_label: str) -> tuple[bool, str]:
    if report_conformance.parse_int(payload.get("schemaVersion")) != report_conformance.REPORT_SCHEMA_VERSION:
        return (
            False,
            f"{report_label}: schemaVersion must be {report_conformance.REPORT_SCHEMA_VERSION}",
        )
    workloads = payload.get("workloads")
    if not isinstance(workloads, list) or not workloads:
        return False, f"{report_label}: workloads must be a non-empty list"
    return True, ""


def load_policy(root: Path, policy_path: Path) -> dict[str, Any]:
    payload = load_json_object(policy_path)
    validate_schema(root / "config" / "benchmark-cube-policy.schema.json", payload)
    host_profiles = {item["id"]: item for item in payload["hostProfiles"]}
    provider_pairs = {item["id"]: item for item in payload["providerPairs"]}
    workload_sets = {item["id"]: item for item in payload["workloadSets"]}
    surfaces = {item["id"]: item for item in payload["surfaces"]}

    for surface in payload["surfaces"]:
        for host_profile in surface["expectedHostProfiles"]:
            if host_profile not in host_profiles:
                raise ValueError(f"unknown host profile in surface policy: {host_profile}")
        for provider_pair in surface["providerPairs"]:
            if provider_pair not in provider_pairs:
                raise ValueError(f"unknown provider pair in surface policy: {provider_pair}")
        for workload_set in surface["workloadSets"]:
            if workload_set not in workload_sets:
                raise ValueError(f"unknown workload set in surface policy: {workload_set}")

    return {
        "raw": payload,
        "hostProfiles": host_profiles,
        "providerPairs": provider_pairs,
        "workloadSets": workload_sets,
        "surfaces": surfaces,
    }


def workload_set_for_domain(policy: dict[str, Any], domain: str) -> str:
    for workload_set in policy["raw"]["workloadSets"]:
        if domain in workload_set["domains"]:
            return workload_set["id"]
    return "overhead"


def detect_backend_host(payload: dict[str, Any], source_path: Path) -> dict[str, str]:
    for workload in payload.get("workloads", []):
        if not isinstance(workload, dict):
            continue
        for side in ("left", "right"):
            side_payload = workload.get(side)
            if not isinstance(side_payload, dict):
                continue
            last_meta = side_payload.get("lastMeta")
            if not isinstance(last_meta, dict):
                continue
            profile = last_meta.get("profile")
            if not isinstance(profile, dict):
                continue
            vendor = str(profile.get("vendor") or "").lower()
            api = str(profile.get("api") or "").lower()
            if vendor == "apple" and api == "metal":
                return {
                    "profileId": "mac_apple_silicon",
                    "os": "darwin",
                    "arch": "arm64",
                    "backend": "metal",
                    "gpuVendor": "apple",
                }
            if vendor == "amd" and api == "vulkan":
                return {
                    "profileId": "linux_amd_vulkan",
                    "os": "linux",
                    "arch": "x64",
                    "backend": "vulkan",
                    "gpuVendor": "amd",
                }
            if api == "d3d12":
                return {
                    "profileId": "windows_d3d12",
                    "os": "win32",
                    "arch": "x64",
                    "backend": "d3d12",
                    "gpuVendor": vendor or "unknown",
                }

    path_text = str(source_path).lower()
    if "apple-metal" in path_text or ".metal" in source_path.name.lower():
        return {
            "profileId": "mac_apple_silicon",
            "os": "darwin",
            "arch": "arm64",
            "backend": "metal",
            "gpuVendor": "apple",
        }
    if "amd-vulkan" in path_text or ".vulkan" in source_path.name.lower():
        return {
            "profileId": "linux_amd_vulkan",
            "os": "linux",
            "arch": "x64",
            "backend": "vulkan",
            "gpuVendor": "amd",
        }
    return {
        "profileId": "linux_x64",
        "os": "linux",
        "arch": "x64",
    }


def detect_package_host(payload: dict[str, Any]) -> dict[str, str]:
    platform = str(payload.get("platform") or "")
    arch = str(payload.get("arch") or "")
    if platform == "darwin" and arch == "arm64":
        return {
            "profileId": "mac_apple_silicon",
            "os": "darwin",
            "arch": "arm64",
        }
    if platform == "win32":
        return {
            "profileId": "windows_x64",
            "os": "win32",
            "arch": arch or "x64",
        }
    return {
        "profileId": "linux_x64",
        "os": platform or "linux",
        "arch": arch or "x64",
    }


def normalize_backend_report(
    *,
    payload: dict[str, Any],
    source_path: Path,
    generated_at: datetime,
    policy: dict[str, Any],
    maturity: str,
    source_conformance: str,
    source_conformance_reason: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    host = detect_backend_host(payload, source_path)
    run_id = run_id_from_timestamp(generated_at)
    rows: list[dict[str, Any]] = []

    for workload in payload.get("workloads", []):
        if not isinstance(workload, dict):
            continue
        domain = str(workload.get("domain") or "overhead")
        workload_set = workload_set_for_domain(policy, domain)
        comparability = workload.get("comparability")
        claimability = workload.get("claimability")
        comparable = isinstance(comparability, dict) and comparability.get("comparable") is True
        claimable = isinstance(claimability, dict) and claimability.get("claimable") is True
        left_payload = workload.get("left") if isinstance(workload.get("left"), dict) else {}
        right_payload = workload.get("right") if isinstance(workload.get("right"), dict) else {}
        left_stats = left_payload.get("stats") if isinstance(left_payload.get("stats"), dict) else {}
        right_stats = right_payload.get("stats") if isinstance(right_payload.get("stats"), dict) else {}
        delta_percent = workload.get("deltaPercent") if isinstance(workload.get("deltaPercent"), dict) else {}

        rows.append(
            {
                "schemaVersion": 1,
                "runId": run_id,
                "generatedAt": iso_utc(generated_at),
                "sourceReportType": "backend_compare_report",
                "sourceReportPath": str(source_path),
                "sourceConformance": source_conformance,
                "sourceConformanceReason": source_conformance_reason,
                "host": host,
                "surface": "backend_native",
                "providerPair": "doe_vs_dawn",
                "workloadSet": workload_set,
                "workloadId": str(workload.get("id") or ""),
                "workloadDomain": domain,
                "comparisonStatus": "comparable" if comparable else "diagnostic",
                "claimStatus": "claimable" if claimable else "diagnostic",
                "maturity": maturity,
                "metrics": {
                    "leftP50Ms": safe_float(left_stats.get("p50Ms")),
                    "rightP50Ms": safe_float(right_stats.get("p50Ms")),
                    "deltaP50Percent": safe_float(delta_percent.get("p50Percent")),
                    "leftP95Ms": safe_float(left_stats.get("p95Ms")),
                    "rightP95Ms": safe_float(right_stats.get("p95Ms")),
                    "leftP99Ms": safe_float(left_stats.get("p99Ms")),
                    "rightP99Ms": safe_float(right_stats.get("p99Ms")),
                    "leftSampleCount": parse_int(left_stats.get("count")),
                    "rightSampleCount": parse_int(right_stats.get("count")),
                },
            }
        )

    return rows, {
        "surface": "backend_native",
        "providerPair": "doe_vs_dawn",
        "hostProfile": host["profileId"],
        "runId": run_id,
        "generatedAt": iso_utc(generated_at),
        "sourceReportPath": str(source_path),
        "sourceConformance": source_conformance,
        "sourceConformanceReason": source_conformance_reason,
        "comparisonStatus": str(payload.get("comparisonStatus") or "diagnostic"),
        "claimStatus": str(payload.get("claimStatus") or "diagnostic"),
        "rowCount": len(rows),
        "deltaP50MedianPercent": median_non_null(
            [row["metrics"]["deltaP50Percent"] for row in rows]
        ),
    }


def validate_package_report(payload: dict[str, Any], *, report_label: str) -> tuple[bool, str]:
    if payload.get("type") != "comparison_report":
        return False, f"{report_label}: type must be comparison_report"
    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        return False, f"{report_label}: comparisons must be a non-empty list"
    return True, ""


def normalize_package_report(
    *,
    payload: dict[str, Any],
    source_path: Path,
    generated_at: datetime,
    policy: dict[str, Any],
    maturity: str,
    surface: str,
    provider_pair: str,
    source_report_type: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    host = detect_package_host(payload)
    run_id = run_id_from_timestamp(generated_at)
    rows: list[dict[str, Any]] = []

    for comparison in payload.get("comparisons", []):
        if not isinstance(comparison, dict):
            continue
        domain = str(comparison.get("domain") or "overhead")
        workload_set = workload_set_for_domain(policy, domain)
        compared = comparison.get("status") == "compared"
        comparable = compared and comparison.get("comparable") is not False
        claimable = comparison.get("claimable") is True
        rows.append(
            {
                "schemaVersion": 1,
                "runId": run_id,
                "generatedAt": iso_utc(generated_at),
                "sourceReportType": source_report_type,
                "sourceReportPath": str(source_path),
                "sourceConformance": "canonical",
                "sourceConformanceReason": "",
                "host": host,
                "surface": surface,
                "providerPair": provider_pair,
                "workloadSet": workload_set,
                "workloadId": str(comparison.get("workload") or ""),
                "workloadDomain": domain,
                "comparisonStatus": "comparable" if comparable else "diagnostic",
                "claimStatus": "claimable" if claimable else "diagnostic",
                "maturity": maturity,
                "metrics": {
                    "leftP50Ms": safe_float(comparison.get("doeMedianMs")),
                    "rightP50Ms": safe_float(comparison.get("dawnMedianMs")),
                    "deltaP50Percent": safe_float(comparison.get("pctFaster")),
                    "leftP95Ms": safe_float(comparison.get("doeP95Ms")),
                    "rightP95Ms": safe_float(comparison.get("dawnP95Ms")),
                    "leftP99Ms": safe_float(comparison.get("doeP99Ms")),
                    "rightP99Ms": safe_float(comparison.get("dawnP99Ms")),
                    "leftSampleCount": None,
                    "rightSampleCount": None,
                },
            }
        )

    compared_rows = [row for row in rows if row["comparisonStatus"] == "comparable"]
    claimable_rows = [row for row in rows if row["claimStatus"] == "claimable"]
    comparison_status = "comparable" if rows and len(compared_rows) == len(rows) else "diagnostic"
    claim_status = "claimable" if compared_rows and len(claimable_rows) == len(compared_rows) else "diagnostic"

    return rows, {
        "surface": surface,
        "providerPair": provider_pair,
        "hostProfile": host["profileId"],
        "runId": run_id,
        "generatedAt": iso_utc(generated_at),
        "sourceReportPath": str(source_path),
        "sourceConformance": "canonical",
        "sourceConformanceReason": "",
        "comparisonStatus": comparison_status,
        "claimStatus": claim_status,
        "rowCount": len(rows),
        "deltaP50MedianPercent": median_non_null(
            [row["metrics"]["deltaP50Percent"] for row in rows]
        ),
    }


def median_non_null(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return float(median(filtered))


def summarize_row_group(rows: list[dict[str, Any]]) -> tuple[str, str, float | None]:
    if not rows:
        return "unimplemented", "unimplemented", None
    source_conformance = rows[0].get("sourceConformance", "canonical")
    comparison_status = (
        "comparable"
        if all(row["comparisonStatus"] == "comparable" for row in rows)
        else "diagnostic"
    )
    claim_status = (
        "claimable"
        if rows and all(row["claimStatus"] == "claimable" for row in rows)
        else "diagnostic"
    )
    comparison_status = degrade_status_for_conformance(comparison_status, source_conformance)
    claim_status = degrade_status_for_conformance(claim_status, source_conformance)
    current_status = claim_status if claim_status == "claimable" else comparison_status
    return current_status, claim_status, median_non_null(
        [row["metrics"]["deltaP50Percent"] for row in rows]
    )


def render_matrix_markdown(summary: dict[str, Any], policy: dict[str, Any]) -> str:
    host_profiles = policy["hostProfiles"]
    workload_sets = policy["workloadSets"]
    cells = {
        (
            cell["surface"],
            cell["hostProfile"],
            cell["workloadSet"],
        ): cell
        for cell in summary["cells"]
    }
    lines = [
        "# Benchmark Cube",
        "",
        f"Generated: `{summary['generatedAt']}`",
        "",
        f"Rows: `{summary['rowCount']}`",
        "",
    ]

    for surface in policy["raw"]["surfaces"]:
        lines.append(f"## {surface['displayName']}")
        lines.append("")
        lines.append(
            f"Maturity: `{surface['maturity']}`. Primary support: `{surface['primarySupport']}`."
        )
        lines.append("")
        header = ["Workload Set", *[host_profiles[item]["displayName"] for item in surface["expectedHostProfiles"]]]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for workload_set_id in surface["workloadSets"]:
            row = [workload_sets[workload_set_id]["displayName"]]
            for host_profile_id in surface["expectedHostProfiles"]:
                cell = cells[(surface["id"], host_profile_id, workload_set_id)]
                if cell["reportCount"] == 0:
                    row.append(cell["status"])
                else:
                    row.append(f"{cell['status']} ({cell['rowCount']} rows)")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
        for note in surface["notes"]:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)


def make_placeholder_cell(surface: dict[str, Any], host_profile: str, provider_pair: str, workload_set: str) -> dict[str, Any]:
    return {
        "surface": surface["id"],
        "providerPair": provider_pair,
        "hostProfile": host_profile,
        "workloadSet": workload_set,
        "scopeType": "full_matrix" if workload_set == "full_comparable" else "workload_set",
        "maturity": surface["maturity"],
        "primarySupport": surface["primarySupport"],
        "status": surface["defaultMissingStatus"],
        "reportCount": 0,
        "rowCount": 0,
        "notes": surface["notes"],
    }


def build_cells(
    *,
    policy: dict[str, Any],
    rows: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_report: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    report_counts: Counter[tuple[str, str, str, str]] = Counter()
    latest_report_for_tuple: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for row in rows:
        key = (
            row["surface"],
            row["providerPair"],
            row["host"]["profileId"],
            row["workloadSet"],
            row["sourceReportPath"],
        )
        rows_by_report[key].append(row)

    for key in rows_by_report:
        short_key = key[:4]
        report_counts[short_key] += 1

    for report in reports:
        full_key = (
            report["surface"],
            report["providerPair"],
            report["hostProfile"],
            "full_comparable",
        )
        existing = latest_report_for_tuple.get(full_key)
        if existing is None or existing["generatedAt"] < report["generatedAt"]:
            latest_report_for_tuple[full_key] = report

    latest_row_report: dict[tuple[str, str, str, str], tuple[str, list[dict[str, Any]], str]] = {}
    for key, grouped_rows in rows_by_report.items():
        short_key = key[:4]
        generated_at = grouped_rows[0]["generatedAt"]
        existing = latest_row_report.get(short_key)
        if existing is None or existing[2] < generated_at:
            latest_row_report[short_key] = (key[4], grouped_rows, generated_at)

    cells: list[dict[str, Any]] = []
    for surface in policy["raw"]["surfaces"]:
        for provider_pair in surface["providerPairs"]:
            for host_profile in surface["expectedHostProfiles"]:
                for workload_set in surface["workloadSets"]:
                    tuple_key = (surface["id"], provider_pair, host_profile, workload_set)
                    if workload_set == "full_comparable":
                        latest = latest_report_for_tuple.get(tuple_key)
                        if latest is None:
                            cells.append(
                                make_placeholder_cell(surface, host_profile, provider_pair, workload_set)
                            )
                            continue
                        status = latest["claimStatus"]
                        if status != "claimable":
                            status = latest["comparisonStatus"]
                        comparison_status = degrade_status_for_conformance(
                            latest["comparisonStatus"],
                            latest.get("sourceConformance", "canonical"),
                        )
                        claim_status = degrade_status_for_conformance(
                            latest["claimStatus"],
                            latest.get("sourceConformance", "canonical"),
                        )
                        status = claim_status if claim_status == "claimable" else comparison_status
                        cells.append(
                            {
                                "surface": surface["id"],
                                "providerPair": provider_pair,
                                "hostProfile": host_profile,
                                "workloadSet": workload_set,
                                "scopeType": "full_matrix",
                                "maturity": surface["maturity"],
                                "primarySupport": surface["primarySupport"],
                                "status": status,
                                "reportCount": sum(
                                    1
                                    for report in reports
                                    if report["surface"] == surface["id"]
                                    and report["providerPair"] == provider_pair
                                    and report["hostProfile"] == host_profile
                                ),
                                "rowCount": latest["rowCount"],
                                "latestRunId": latest["runId"],
                                "latestGeneratedAt": latest["generatedAt"],
                                "latestReportPath": latest["sourceReportPath"],
                                "sourceConformance": latest.get("sourceConformance", "canonical"),
                                "sourceConformanceReason": latest.get("sourceConformanceReason", ""),
                                "comparisonStatus": comparison_status,
                                "claimStatus": claim_status,
                                "deltaP50MedianPercent": latest["deltaP50MedianPercent"],
                                "notes": surface["notes"],
                            }
                        )
                        continue

                    latest_rows_info = latest_row_report.get(tuple_key)
                    if latest_rows_info is None:
                        cells.append(
                            make_placeholder_cell(surface, host_profile, provider_pair, workload_set)
                        )
                        continue
                    latest_report_path, latest_rows, latest_generated_at = latest_rows_info
                    status, claim_status, delta_percent = summarize_row_group(latest_rows)
                    comparison_status = (
                        "comparable"
                        if all(row["comparisonStatus"] == "comparable" for row in latest_rows)
                        else "diagnostic"
                    )
                    comparison_status = degrade_status_for_conformance(
                        comparison_status,
                        latest_rows[0].get("sourceConformance", "canonical"),
                    )
                    cells.append(
                        {
                            "surface": surface["id"],
                            "providerPair": provider_pair,
                            "hostProfile": host_profile,
                            "workloadSet": workload_set,
                            "scopeType": "workload_set",
                            "maturity": surface["maturity"],
                            "primarySupport": surface["primarySupport"],
                            "status": status,
                            "reportCount": report_counts[tuple_key],
                            "rowCount": len(latest_rows),
                            "latestRunId": latest_rows[0]["runId"],
                            "latestGeneratedAt": latest_generated_at,
                            "latestReportPath": latest_report_path,
                            "sourceConformance": latest_rows[0].get("sourceConformance", "canonical"),
                            "sourceConformanceReason": latest_rows[0].get("sourceConformanceReason", ""),
                            "comparisonStatus": comparison_status,
                            "claimStatus": claim_status,
                            "deltaP50MedianPercent": delta_percent,
                            "notes": surface["notes"],
                        }
                    )

    cells.sort(
        key=lambda cell: (
            cell["surface"],
            cell["hostProfile"],
            cell["workloadSet"],
            cell["providerPair"],
        )
    )
    return cells


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    timestamp = output_paths.resolve_timestamp(args.timestamp)

    policy_path = (repo_root / args.policy).resolve()
    obligation_path = (repo_root / args.comparability_obligations).resolve()
    policy = load_policy(repo_root, policy_path)
    obligation_schema_version, obligation_ids = report_conformance.load_obligation_contract(
        obligation_path
    )

    backend_patterns = args.backend_report_glob or ["bench/out/**/dawn-vs-doe*.json"]
    node_patterns = args.node_report_glob or ["bench/out/node-doe-vs-dawn/*.json"]
    bun_patterns = args.bun_report_glob or ["bench/out/bun-doe-vs-webgpu/*.json"]

    backend_paths = collect_paths(backend_patterns, args.backend_report)
    node_paths = collect_paths(node_patterns, args.node_report)
    bun_paths = collect_paths(bun_patterns, args.bun_report)

    rows: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    source_counts = {
        "backendReports": {
            "discovered": len(backend_paths),
            "included": 0,
            "canonicalIncluded": 0,
            "legacyIncluded": 0,
            "skipped": 0,
        },
        "nodeReports": {
            "discovered": len(node_paths),
            "included": 0,
            "canonicalIncluded": 0,
            "legacyIncluded": 0,
            "skipped": 0,
        },
        "bunReports": {
            "discovered": len(bun_paths),
            "included": 0,
            "canonicalIncluded": 0,
            "legacyIncluded": 0,
            "skipped": 0,
        },
    }

    for path in backend_paths:
        if is_scratch_namespace_path(path):
            source_counts["backendReports"]["skipped"] += 1
            continue
        try:
            payload = load_json_object(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            source_counts["backendReports"]["skipped"] += 1
            continue
        include, reason = validate_backend_report_shape(payload, report_label=str(path))
        if not include:
            source_counts["backendReports"]["skipped"] += 1
            continue
        is_canonical, canonical_reason = report_conformance.validate_report_conformance(
            payload=payload,
            report_path=path,
            repo_root=repo_root,
            expected_obligation_schema_version=obligation_schema_version,
            expected_obligation_ids=obligation_ids,
        )
        generated_at = parse_report_timestamp(payload, path)
        surface_policy = policy["surfaces"]["backend_native"]
        normalized_rows, report_info = normalize_backend_report(
            payload=payload,
            source_path=path,
            generated_at=generated_at,
            policy=policy,
            maturity=surface_policy["maturity"],
            source_conformance="canonical" if is_canonical else "legacy_nonconformant",
            source_conformance_reason="" if is_canonical else canonical_reason,
        )
        rows.extend(normalized_rows)
        reports.append(report_info)
        source_counts["backendReports"]["included"] += 1
        if is_canonical:
            source_counts["backendReports"]["canonicalIncluded"] += 1
        else:
            source_counts["backendReports"]["legacyIncluded"] += 1

    for path in node_paths:
        if is_scratch_namespace_path(path):
            source_counts["nodeReports"]["skipped"] += 1
            continue
        try:
            payload = load_json_object(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            source_counts["nodeReports"]["skipped"] += 1
            continue
        include, _reason = validate_package_report(payload, report_label=str(path))
        if not include:
            source_counts["nodeReports"]["skipped"] += 1
            continue
        generated_at = parse_report_timestamp(payload, path)
        surface_policy = policy["surfaces"]["node_package"]
        normalized_rows, report_info = normalize_package_report(
            payload=payload,
            source_path=path,
            generated_at=generated_at,
            policy=policy,
            maturity=surface_policy["maturity"],
            surface="node_package",
            provider_pair="doe_node_vs_dawn_node",
            source_report_type="node_package_compare_report",
        )
        rows.extend(normalized_rows)
        reports.append(report_info)
        source_counts["nodeReports"]["included"] += 1
        source_counts["nodeReports"]["canonicalIncluded"] += 1

    for path in bun_paths:
        if is_scratch_namespace_path(path):
            source_counts["bunReports"]["skipped"] += 1
            continue
        try:
            payload = load_json_object(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            source_counts["bunReports"]["skipped"] += 1
            continue
        include, _reason = validate_package_report(payload, report_label=str(path))
        if not include:
            source_counts["bunReports"]["skipped"] += 1
            continue
        generated_at = parse_report_timestamp(payload, path)
        surface_policy = policy["surfaces"]["bun_package"]
        normalized_rows, report_info = normalize_package_report(
            payload=payload,
            source_path=path,
            generated_at=generated_at,
            policy=policy,
            maturity=surface_policy["maturity"],
            surface="bun_package",
            provider_pair="doe_bun_vs_bun_webgpu",
            source_report_type="bun_package_compare_report",
        )
        rows.extend(normalized_rows)
        reports.append(report_info)
        source_counts["bunReports"]["included"] += 1
        source_counts["bunReports"]["canonicalIncluded"] += 1

    row_schema_path = repo_root / "config" / "benchmark-cube-row.schema.json"
    for row in rows:
        validate_schema(row_schema_path, row)

    summary_out = output_paths.with_timestamp(
        args.summary_out,
        timestamp,
        enabled=args.timestamp_output,
        group="cube",
    )
    rows_out = output_paths.with_timestamp(
        args.rows_out,
        timestamp,
        enabled=args.timestamp_output,
        group="cube",
    )
    matrix_md_out = output_paths.with_timestamp(
        args.matrix_md_out,
        timestamp,
        enabled=args.timestamp_output,
        group="cube",
    )
    dashboard_html_out = output_paths.with_timestamp(
        args.dashboard_html_out,
        timestamp,
        enabled=args.timestamp_output,
        group="cube",
    )

    cells = build_cells(policy=policy, rows=rows, reports=reports)
    status_counts = Counter(cell["status"] for cell in cells)
    for status in STATUS_ORDER:
        status_counts.setdefault(status, 0)

    summary_payload = {
        "schemaVersion": 1,
        "generatedAt": iso_utc(datetime.now(timezone.utc)),
        "policy": {
            "path": str(policy_path.relative_to(repo_root)),
            "sha256": report_conformance.file_sha256(policy_path),
        },
        "artifacts": {
            "rowsPath": str(rows_out),
            "matrixMarkdownPath": str(matrix_md_out),
            "dashboardHtmlPath": str(dashboard_html_out),
        },
        "sourceCounts": source_counts,
        "rowCount": len(rows),
        "cells": cells,
        "statusCounts": {status: status_counts[status] for status in STATUS_ORDER},
    }
    validate_schema(repo_root / "config" / "benchmark-cube.schema.json", summary_payload)

    matrix_markdown = render_matrix_markdown(summary_payload, policy)
    dashboard_html = benchmark_cube_dashboard_html.build_dashboard_html(summary_payload, policy)
    write_json(rows_out, rows)
    write_json(summary_out, summary_payload)
    write_text(matrix_md_out, matrix_markdown + "\n")
    write_text(dashboard_html_out, dashboard_html + "\n")
    write_json(Path(args.latest_rows), rows)
    write_json(Path(args.latest_summary), summary_payload)
    write_text(Path(args.latest_matrix_md), matrix_markdown + "\n")
    write_text(Path(args.latest_dashboard_html), dashboard_html + "\n")

    output_paths.write_run_manifest_for_outputs(
        [rows_out, summary_out, matrix_md_out, dashboard_html_out],
        {
            "runType": "benchmark-cube",
            "config": str(policy_path.relative_to(repo_root)),
            "status": "ok",
            "summaryPath": str(summary_out),
            "rowsPath": str(rows_out),
            "matrixMarkdownPath": str(matrix_md_out),
            "dashboardHtmlPath": str(dashboard_html_out),
        },
    )


if __name__ == "__main__":
    main()
