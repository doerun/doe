#!/usr/bin/env python3
"""Build a canonical tested-profile inventory and a simple matrix dashboard."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from glob import glob
from html import escape
from pathlib import Path
from typing import Any

import output_paths


TIMESTAMP_SUFFIX_RE = re.compile(r"\d{8}T\d{6}Z$")


@dataclass(frozen=True)
class SideProfile:
    profile_id: str
    vendor: str
    api: str
    device_family: str
    driver: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report-glob",
        action="append",
        default=[],
        help=(
            "Glob for compare reports. "
            "May be repeated. Default: bench/out/dawn-vs-fawn*.json"
        ),
    )
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        help="Explicit compare report path. May be repeated.",
    )
    parser.add_argument(
        "--inventory-out",
        default="bench/out/test-inventory.json",
        help="Output JSON inventory path.",
    )
    parser.add_argument(
        "--dashboard-out",
        default="bench/out/test-dashboard.html",
        help="Output HTML dashboard path.",
    )
    parser.add_argument(
        "--latest-inventory",
        default="bench/out/test-inventory.latest.json",
        help="Stable latest inventory JSON path (always overwritten).",
    )
    parser.add_argument(
        "--latest-dashboard",
        default="bench/out/test-dashboard.latest.html",
        help="Stable latest dashboard HTML path (always overwritten).",
    )
    parser.add_argument(
        "--max-recent-reports",
        type=int,
        default=30,
        help="Maximum number of recent reports shown in dashboard.",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for output artifact paths (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp inventory/dashboard output paths with a UTC timestamp suffix.",
    )
    return parser.parse_args()


def safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


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


def parse_report_timestamp(payload: dict[str, Any], source_path: Path) -> datetime | None:
    generated = parse_utc_iso(payload.get("generatedAt"))
    if generated is not None:
        return generated

    output_timestamp = payload.get("outputTimestamp")
    if isinstance(output_timestamp, str):
        try:
            return datetime.strptime(output_timestamp, output_paths.TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    stem = source_path.stem
    parts = stem.split(".")
    if parts and TIMESTAMP_SUFFIX_RE.fullmatch(parts[-1]):
        try:
            return datetime.strptime(parts[-1], output_paths.TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def iso_utc(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_matrix_id(payload: dict[str, Any], source_path: Path) -> str:
    path_hint = payload.get("outPath")
    if isinstance(path_hint, str) and path_hint.strip():
        stem = Path(path_hint).stem
    else:
        stem = source_path.stem

    parts = stem.split(".")
    if parts and TIMESTAMP_SUFFIX_RE.fullmatch(parts[-1]):
        parts = parts[:-1]
    normalized = ".".join(parts).strip()
    return normalized or stem


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def should_include_report(payload: dict[str, Any]) -> tuple[bool, str]:
    workloads = payload.get("workloads")
    if not isinstance(workloads, list):
        return False, "missing workloads list"
    comparison_status = payload.get("comparisonStatus")
    claim_status = payload.get("claimStatus")
    if not isinstance(comparison_status, str) or not comparison_status:
        return False, "missing comparisonStatus"
    if not isinstance(claim_status, str) or not claim_status:
        return False, "missing claimStatus"
    return True, ""


def side_name(payload: dict[str, Any], side: str) -> str:
    side_payload = payload.get(side)
    if isinstance(side_payload, dict):
        name = side_payload.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return side


def read_trace_meta(sample: dict[str, Any], cache: dict[str, dict[str, Any] | None]) -> dict[str, Any] | None:
    inline = sample.get("traceMeta")
    if isinstance(inline, dict):
        return inline

    trace_meta_path = sample.get("traceMetaPath")
    if not isinstance(trace_meta_path, str) or not trace_meta_path.strip():
        return None
    if trace_meta_path in cache:
        return cache[trace_meta_path]
    path = Path(trace_meta_path)
    if not path.exists():
        cache[trace_meta_path] = None
        return None
    try:
        parsed = load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        cache[trace_meta_path] = None
        return None
    cache[trace_meta_path] = parsed
    return parsed


def extract_side_profiles(
    payload: dict[str, Any],
    side: str,
    meta_cache: dict[str, dict[str, Any] | None],
) -> tuple[list[SideProfile], int]:
    workloads = payload.get("workloads")
    if not isinstance(workloads, list):
        return [], 0

    profiles: dict[str, SideProfile] = {}
    sample_count = 0
    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        side_payload = workload.get(side)
        if not isinstance(side_payload, dict):
            continue
        samples = side_payload.get("commandSamples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            return_code = sample.get("returnCode")
            if not isinstance(return_code, int) or return_code != 0:
                continue
            trace_meta = read_trace_meta(sample, meta_cache)
            if not isinstance(trace_meta, dict):
                continue
            profile = trace_meta.get("profile")
            if not isinstance(profile, dict):
                continue
            vendor = profile.get("vendor")
            api = profile.get("api")
            driver = profile.get("driver")
            if not isinstance(vendor, str) or not vendor.strip():
                continue
            if not isinstance(api, str) or not api.strip():
                continue
            if not isinstance(driver, str) or not driver.strip():
                continue
            family_raw = profile.get("deviceFamily")
            family = family_raw.strip() if isinstance(family_raw, str) else ""
            profile_id = f"{vendor.strip()}|{api.strip()}|{family}|{driver.strip()}"
            profiles[profile_id] = SideProfile(
                profile_id=profile_id,
                vendor=vendor.strip(),
                api=api.strip(),
                device_family=family,
                driver=driver.strip(),
            )
            sample_count += 1
    return sorted(profiles.values(), key=lambda item: item.profile_id), sample_count


def derive_overall_delta_p50(payload: dict[str, Any]) -> float | None:
    overall = payload.get("overall")
    if not isinstance(overall, dict):
        return None
    delta = overall.get("deltaPercent")
    if isinstance(delta, dict):
        parsed = safe_float(delta.get("p50Approx"))
        if parsed is not None:
            return parsed
    left = overall.get("left")
    right = overall.get("right")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    left_p50 = safe_float(left.get("p50Ms"))
    right_p50 = safe_float(right.get("p50Ms"))
    if left_p50 is None or right_p50 is None or right_p50 <= 0.0:
        return None
    return ((right_p50 - left_p50) / right_p50) * 100.0


def get_count(summary: Any, key: str) -> int:
    if not isinstance(summary, dict):
        return 0
    value = summary.get(key)
    return value if isinstance(value, int) and value >= 0 else 0


def count_non_comparable(payload: dict[str, Any]) -> int:
    comparability_summary = payload.get("comparabilitySummary")
    from_summary = get_count(comparability_summary, "nonComparableCount")
    if from_summary > 0:
        return from_summary
    workloads = payload.get("workloads")
    if not isinstance(workloads, list):
        return 0
    count = 0
    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        comparability = workload.get("comparability")
        if isinstance(comparability, dict) and comparability.get("comparable") is False:
            count += 1
    return count


def count_non_claimable(payload: dict[str, Any]) -> int:
    claimability_summary = payload.get("claimabilitySummary")
    from_summary = get_count(claimability_summary, "nonClaimableCount")
    if from_summary > 0:
        return from_summary
    workloads = payload.get("workloads")
    if not isinstance(workloads, list):
        return 0
    count = 0
    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        claimability = workload.get("claimability")
        if isinstance(claimability, dict) and claimability.get("claimable") is False:
            count += 1
    return count


def status_class(status: str, *, kind: str) -> str:
    if kind == "comparison":
        if status == "comparable":
            return "good"
        if status in {"unreliable", "non-comparable"}:
            return "bad"
        return "warn"
    if kind == "claim":
        if status == "claimable":
            return "good"
        if status == "diagnostic":
            return "warn"
        return "bad"
    return "warn"


def format_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def build_dashboard_html(inventory: dict[str, Any], *, max_recent_reports: int) -> str:
    summary = inventory.get("summary", {})
    matrices = inventory.get("matrices", [])
    profiles = inventory.get("profiles", [])
    reports = inventory.get("reports", [])
    generated_at = escape(str(inventory.get("generatedAtUtc", "")))
    inventory_path = escape(str(inventory.get("inventoryPath", "")))

    matrix_rows: list[str] = []
    for matrix in matrices:
        if not isinstance(matrix, dict):
            continue
        latest = matrix.get("latest", {})
        if not isinstance(latest, dict):
            latest = {}
        comparison_status = str(latest.get("comparisonStatus", "unknown"))
        claim_status = str(latest.get("claimStatus", "unknown"))
        matrix_rows.append(
            "<tr>"
            f"<td><code>{escape(str(matrix.get('matrixId', 'unknown')))}</code></td>"
            f"<td>{escape(str(latest.get('generatedAtUtc', '')))}</td>"
            f"<td><span class='badge {status_class(comparison_status, kind='comparison')}'>{escape(comparison_status)}</span></td>"
            f"<td><span class='badge {status_class(claim_status, kind='claim')}'>{escape(claim_status)}</span></td>"
            f"<td>{escape(str(latest.get('workloadCount', 0)))}</td>"
            f"<td>{escape(str(latest.get('nonComparableCount', 0)))}</td>"
            f"<td>{escape(str(latest.get('nonClaimableCount', 0)))}</td>"
            f"<td>{escape(format_delta(safe_float(latest.get('overallP50DeltaPercent'))))}</td>"
            "</tr>"
        )

    profile_rows: list[str] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        family = str(profile.get("deviceFamily", ""))
        profile_rows.append(
            "<tr>"
            f"<td><code>{escape(str(profile.get('vendor', '')))} / {escape(str(profile.get('api', '')))}"
            f" / {escape(family or '-')} / {escape(str(profile.get('driver', '')))}</code></td>"
            f"<td>{escape(str(profile.get('reportCount', 0)))}</td>"
            f"<td>{escape(str(profile.get('sampleCount', 0)))}</td>"
            f"<td>{escape(', '.join(str(x) for x in profile.get('sides', [])))}</td>"
            f"<td>{escape(str(profile.get('matrixCount', 0)))}</td>"
            f"<td>{escape(str(profile.get('firstSeenUtc', '')))}</td>"
            f"<td>{escape(str(profile.get('lastSeenUtc', '')))}</td>"
            "</tr>"
        )

    recent_rows: list[str] = []
    recent_count = 0
    for report in reports:
        if recent_count >= max_recent_reports:
            break
        if not isinstance(report, dict):
            continue
        comparison_status = str(report.get("comparisonStatus", "unknown"))
        claim_status = str(report.get("claimStatus", "unknown"))
        recent_rows.append(
            "<tr>"
            f"<td>{escape(str(report.get('generatedAtUtc', '')))}</td>"
            f"<td><code>{escape(str(report.get('matrixId', 'unknown')))}</code></td>"
            f"<td><span class='badge {status_class(comparison_status, kind='comparison')}'>{escape(comparison_status)}</span></td>"
            f"<td><span class='badge {status_class(claim_status, kind='claim')}'>{escape(claim_status)}</span></td>"
            f"<td>{escape(format_delta(safe_float(report.get('overallP50DeltaPercent'))))}</td>"
            f"<td>{escape(str(report.get('workloadCount', 0)))}</td>"
            f"<td><code>{escape(str(report.get('sourcePath', '')))}</code></td>"
            "</tr>"
        )
        recent_count += 1

    return (
        "<!doctype html>"
        "<html lang='en'>"
        "<head>"
        "<meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>Fawn Test Inventory Dashboard</title>"
        "<style>"
        "body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:24px;color:#0f172a;background:#f8fafc;}"
        "h1,h2{margin:0 0 12px 0;} h2{margin-top:28px;}"
        ".meta{color:#475569;font-size:14px;margin-bottom:16px;}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;}"
        ".card{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:12px;}"
        ".card .k{font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;}"
        ".card .v{font-size:20px;font-weight:700;margin-top:6px;}"
        "table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;}"
        "th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #f1f5f9;font-size:13px;vertical-align:top;}"
        "th{background:#f1f5f9;color:#334155;font-weight:600;}"
        "tr:last-child td{border-bottom:none;}"
        ".badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;}"
        ".badge.good{background:#dcfce7;color:#166534;}"
        ".badge.warn{background:#fef9c3;color:#854d0e;}"
        ".badge.bad{background:#fee2e2;color:#991b1b;}"
        "code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;}"
        "</style>"
        "</head>"
        "<body>"
        "<h1>Fawn Test Inventory Dashboard</h1>"
        f"<div class='meta'>generated: {generated_at} | inventory: <code>{inventory_path}</code></div>"
        "<div class='cards'>"
        f"<div class='card'><div class='k'>Reports</div><div class='v'>{escape(str(summary.get('includedReports', 0)))}</div></div>"
        f"<div class='card'><div class='k'>Matrices</div><div class='v'>{escape(str(summary.get('matrixCount', 0)))}</div></div>"
        f"<div class='card'><div class='k'>Profiles</div><div class='v'>{escape(str(summary.get('uniqueProfileCount', 0)))}</div></div>"
        f"<div class='card'><div class='k'>Comparable Reports</div><div class='v'>{escape(str(summary.get('comparableReportCount', 0)))}</div></div>"
        f"<div class='card'><div class='k'>Claimable Reports</div><div class='v'>{escape(str(summary.get('claimableReportCount', 0)))}</div></div>"
        "</div>"
        "<h2>Matrix Status (Latest)</h2>"
        "<table><thead><tr><th>Matrix</th><th>Latest UTC</th><th>Comparison</th><th>Claim</th><th>Workloads</th><th>Non-Comparable</th><th>Non-Claimable</th><th>p50 Delta</th></tr></thead><tbody>"
        + ("".join(matrix_rows) if matrix_rows else "<tr><td colspan='8'>No matrix rows.</td></tr>")
        + "</tbody></table>"
        "<h2>Tested Hardware/Driver Profiles</h2>"
        "<table><thead><tr><th>Profile</th><th>Reports</th><th>Samples</th><th>Sides</th><th>Matrices</th><th>First Seen</th><th>Last Seen</th></tr></thead><tbody>"
        + ("".join(profile_rows) if profile_rows else "<tr><td colspan='7'>No profile rows.</td></tr>")
        + "</tbody></table>"
        "<h2>Recent Reports</h2>"
        "<table><thead><tr><th>Generated UTC</th><th>Matrix</th><th>Comparison</th><th>Claim</th><th>p50 Delta</th><th>Workloads</th><th>Source</th></tr></thead><tbody>"
        + ("".join(recent_rows) if recent_rows else "<tr><td colspan='7'>No reports.</td></tr>")
        + "</tbody></table>"
        "</body></html>"
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
        for raw in sorted(glob(pattern)):
            path = Path(raw)
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path)

    return candidates


def main() -> int:
    args = parse_args()
    if args.max_recent_reports < 0:
        print(f"FAIL: --max-recent-reports must be >= 0 (received {args.max_recent_reports})")
        return 1

    report_patterns = args.report_glob if args.report_glob else ["bench/out/dawn-vs-fawn*.json"]
    sources = collect_paths(report_patterns, args.report)
    if not sources:
        print("FAIL: no report files matched")
        return 1

    meta_cache: dict[str, dict[str, Any] | None] = {}
    skipped_files: list[dict[str, str]] = []
    report_entries: list[dict[str, Any]] = []

    profile_agg: dict[str, dict[str, Any]] = {}
    matrix_agg: dict[str, list[dict[str, Any]]] = {}

    for source_path in sources:
        if not source_path.exists():
            skipped_files.append({"path": str(source_path), "reason": "missing"})
            continue
        try:
            payload = load_json(source_path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            skipped_files.append({"path": str(source_path), "reason": f"parse failed: {exc}"})
            continue

        include, reason = should_include_report(payload)
        if not include:
            skipped_files.append({"path": str(source_path), "reason": reason})
            continue

        generated_at = parse_report_timestamp(payload, source_path)
        generated_at_utc = iso_utc(generated_at)
        matrix_id = normalize_matrix_id(payload, source_path)
        workloads = payload.get("workloads")
        workload_count = len(workloads) if isinstance(workloads, list) else 0
        comparison_status = str(payload.get("comparisonStatus", "unknown"))
        claim_status = str(payload.get("claimStatus", "unknown"))
        overall_p50_delta = derive_overall_delta_p50(payload)
        non_comparable_count = count_non_comparable(payload)
        non_claimable_count = count_non_claimable(payload)
        left_name = side_name(payload, "left")
        right_name = side_name(payload, "right")

        left_profiles, left_samples = extract_side_profiles(payload, "left", meta_cache)
        right_profiles, right_samples = extract_side_profiles(payload, "right", meta_cache)

        entry = {
            "sourcePath": str(source_path),
            "outPath": payload.get("outPath", ""),
            "matrixId": matrix_id,
            "generatedAtUtc": generated_at_utc,
            "comparisonStatus": comparison_status,
            "claimStatus": claim_status,
            "workloadCount": workload_count,
            "nonComparableCount": non_comparable_count,
            "nonClaimableCount": non_claimable_count,
            "overallP50DeltaPercent": overall_p50_delta,
            "leftName": left_name,
            "rightName": right_name,
            "leftProfiles": [profile.profile_id for profile in left_profiles],
            "rightProfiles": [profile.profile_id for profile in right_profiles],
            "leftProfileSampleCount": left_samples,
            "rightProfileSampleCount": right_samples,
        }
        report_entries.append(entry)
        matrix_agg.setdefault(matrix_id, []).append(entry)

        for side_label, runtime_name, side_profiles, sample_count in (
            ("left", left_name, left_profiles, left_samples),
            ("right", right_name, right_profiles, right_samples),
        ):
            per_profile_samples = sample_count // max(len(side_profiles), 1) if side_profiles else 0
            for profile in side_profiles:
                agg = profile_agg.get(profile.profile_id)
                if agg is None:
                    agg = {
                        "profileId": profile.profile_id,
                        "vendor": profile.vendor,
                        "api": profile.api,
                        "deviceFamily": profile.device_family,
                        "driver": profile.driver,
                        "reportPaths": set(),
                        "matrixIds": set(),
                        "sides": set(),
                        "runtimes": set(),
                        "sampleCount": 0,
                        "firstSeen": generated_at,
                        "lastSeen": generated_at,
                    }
                    profile_agg[profile.profile_id] = agg
                agg["reportPaths"].add(str(source_path))
                agg["matrixIds"].add(matrix_id)
                agg["sides"].add(side_label)
                agg["runtimes"].add(runtime_name)
                agg["sampleCount"] += max(per_profile_samples, 1)
                first_seen = agg.get("firstSeen")
                last_seen = agg.get("lastSeen")
                if isinstance(generated_at, datetime):
                    if not isinstance(first_seen, datetime) or generated_at < first_seen:
                        agg["firstSeen"] = generated_at
                    if not isinstance(last_seen, datetime) or generated_at > last_seen:
                        agg["lastSeen"] = generated_at

    if not report_entries:
        print("FAIL: no comparable-report artifacts found after filtering")
        return 1

    report_entries.sort(key=lambda item: item.get("generatedAtUtc", ""), reverse=True)

    matrix_entries: list[dict[str, Any]] = []
    for matrix_id, entries in matrix_agg.items():
        entries_sorted = sorted(entries, key=lambda item: str(item.get("generatedAtUtc", "")), reverse=True)
        latest = entries_sorted[0]
        comparison_counts = Counter(str(item.get("comparisonStatus", "unknown")) for item in entries_sorted)
        claim_counts = Counter(str(item.get("claimStatus", "unknown")) for item in entries_sorted)
        matrix_entries.append(
            {
                "matrixId": matrix_id,
                "reportCount": len(entries_sorted),
                "comparisonStatusCounts": dict(sorted(comparison_counts.items())),
                "claimStatusCounts": dict(sorted(claim_counts.items())),
                "latest": latest,
            }
        )
    matrix_entries.sort(key=lambda item: str(item.get("matrixId", "")))

    profile_entries: list[dict[str, Any]] = []
    for agg in profile_agg.values():
        report_paths = agg["reportPaths"]
        matrix_ids = agg["matrixIds"]
        sides = agg["sides"]
        runtimes = agg["runtimes"]
        profile_entries.append(
            {
                "profileId": agg["profileId"],
                "vendor": agg["vendor"],
                "api": agg["api"],
                "deviceFamily": agg["deviceFamily"],
                "driver": agg["driver"],
                "reportCount": len(report_paths),
                "matrixCount": len(matrix_ids),
                "sampleCount": agg["sampleCount"],
                "sides": sorted(sides),
                "runtimes": sorted(runtimes),
                "firstSeenUtc": iso_utc(agg.get("firstSeen")),
                "lastSeenUtc": iso_utc(agg.get("lastSeen")),
                "reportPaths": sorted(report_paths),
                "matrixIds": sorted(matrix_ids),
            }
        )
    profile_entries.sort(key=lambda item: str(item.get("profileId", "")))

    comparison_counter = Counter(str(item.get("comparisonStatus", "unknown")) for item in report_entries)
    claim_counter = Counter(str(item.get("claimStatus", "unknown")) for item in report_entries)
    summary = {
        "totalMatchedFiles": len(sources),
        "includedReports": len(report_entries),
        "skippedFiles": len(skipped_files),
        "matrixCount": len(matrix_entries),
        "uniqueProfileCount": len(profile_entries),
        "comparableReportCount": comparison_counter.get("comparable", 0),
        "claimableReportCount": claim_counter.get("claimable", 0),
        "comparisonStatusCounts": dict(sorted(comparison_counter.items())),
        "claimStatusCounts": dict(sorted(claim_counter.items())),
    }

    generated_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )
    inventory_out = output_paths.with_timestamp(
        args.inventory_out,
        output_timestamp,
        enabled=args.timestamp_output,
    )
    dashboard_out = output_paths.with_timestamp(
        args.dashboard_out,
        output_timestamp,
        enabled=args.timestamp_output,
    )
    latest_inventory = Path(args.latest_inventory)
    latest_dashboard = Path(args.latest_dashboard)

    inventory_payload = {
        "schemaVersion": 1,
        "generatedAtUtc": generated_at_utc,
        "outputTimestamp": output_timestamp,
        "inventoryPath": str(inventory_out),
        "source": {
            "reportGlobs": report_patterns,
            "explicitReports": args.report,
        },
        "summary": summary,
        "matrices": matrix_entries,
        "profiles": profile_entries,
        "reports": report_entries,
        "skippedFiles": skipped_files,
    }
    dashboard_html = build_dashboard_html(
        inventory_payload,
        max_recent_reports=args.max_recent_reports,
    )

    write_json(inventory_out, inventory_payload)
    write_text(dashboard_out, dashboard_html)
    write_json(latest_inventory, inventory_payload)
    write_text(latest_dashboard, dashboard_html)

    print("PASS: built test inventory + dashboard")
    print(f"inventory: {inventory_out}")
    print(f"dashboard: {dashboard_out}")
    print(f"latest inventory: {latest_inventory}")
    print(f"latest dashboard: {latest_dashboard}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
