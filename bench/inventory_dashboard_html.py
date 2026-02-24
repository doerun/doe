#!/usr/bin/env python3
"""HTML rendering helpers for test inventory dashboard."""

from __future__ import annotations

from html import escape
from typing import Any


def safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


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


def infer_matrix_lane(matrix_id: str) -> str:
    token = matrix_id.lower()
    if ".release" in token:
        return "release"
    if ".directional" in token:
        return "directional"
    if ".smoke" in token:
        return "smoke"
    if ".macro" in token:
        return "macro"
    if ".extended.comparable" in token:
        return "extended-comparable"
    if ".extended" in token:
        return "extended"
    return "default"


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
        matrix_id = str(matrix.get("matrixId", "unknown"))
        comparison_status = str(latest.get("comparisonStatus", "unknown"))
        claim_status = str(latest.get("claimStatus", "unknown"))
        lane = str(matrix.get("lane", infer_matrix_lane(matrix_id)))
        matrix_rows.append(
            "<tr>"
            f"<td><code>{escape(matrix_id)}</code></td>"
            f"<td><span class='badge lane'>{escape(lane)}</span></td>"
            f"<td>{escape(str(latest.get('generatedAtUtc', '')))}</td>"
            f"<td><span class='badge {status_class(comparison_status, kind='comparison')}'>{escape(comparison_status)}</span></td>"
            f"<td><span class='badge {status_class(claim_status, kind='claim')}'>{escape(claim_status)}</span></td>"
            f"<td>{escape(str(latest.get('workloadCount', 0)))}</td>"
            f"<td>{escape(str(latest.get('nonComparableCount', 0)))}</td>"
            f"<td>{escape(str(latest.get('nonClaimableCount', 0)))}</td>"
            f"<td>{escape(format_delta(safe_float(latest.get('overallP50DeltaPercent'))))}</td>"
            f"<td><code>{escape(str(latest.get('sourcePath', '')))}</code></td>"
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
        matrix_id = str(report.get("matrixId", "unknown"))
        lane = str(report.get("lane", infer_matrix_lane(matrix_id)))
        comparison_status = str(report.get("comparisonStatus", "unknown"))
        claim_status = str(report.get("claimStatus", "unknown"))
        recent_rows.append(
            "<tr>"
            f"<td>{escape(str(report.get('generatedAtUtc', '')))}</td>"
            f"<td><code>{escape(matrix_id)}</code></td>"
            f"<td><span class='badge lane'>{escape(lane)}</span></td>"
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
        ".badge.lane{background:#e0f2fe;color:#075985;}"
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
        f"<div class='card'><div class='k'>Comparable+Claimable Reports</div><div class='v'>{escape(str(summary.get('claimableComparableReportCount', 0)))}</div></div>"
        f"<div class='card'><div class='k'>Latest Comparable Matrices</div><div class='v'>{escape(str(summary.get('latestComparableMatrixCount', 0)))}</div></div>"
        f"<div class='card'><div class='k'>Latest Claimable Matrices</div><div class='v'>{escape(str(summary.get('latestClaimableMatrixCount', 0)))}</div></div>"
        "</div>"
        "<h2>Matrix Status (Latest)</h2>"
        "<table><thead><tr><th>Matrix</th><th>Lane</th><th>Latest UTC</th><th>Comparison</th><th>Claim</th><th>Workloads</th><th>Non-Comparable</th><th>Non-Claimable</th><th>p50 Delta</th><th>Source</th></tr></thead><tbody>"
        + ("".join(matrix_rows) if matrix_rows else "<tr><td colspan='10'>No matrix rows.</td></tr>")
        + "</tbody></table>"
        "<h2>Tested Hardware/Driver Profiles</h2>"
        "<table><thead><tr><th>Profile</th><th>Reports</th><th>Samples</th><th>Sides</th><th>Matrices</th><th>First Seen</th><th>Last Seen</th></tr></thead><tbody>"
        + ("".join(profile_rows) if profile_rows else "<tr><td colspan='7'>No profile rows.</td></tr>")
        + "</tbody></table>"
        "<h2>Recent Reports</h2>"
        "<table><thead><tr><th>Generated UTC</th><th>Matrix</th><th>Lane</th><th>Comparison</th><th>Claim</th><th>p50 Delta</th><th>Workloads</th><th>Source</th></tr></thead><tbody>"
        + ("".join(recent_rows) if recent_rows else "<tr><td colspan='8'>No reports.</td></tr>")
        + "</tbody></table>"
        "</body></html>"
    )
