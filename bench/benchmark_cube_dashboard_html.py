"""HTML rendering helpers for benchmark cube dashboards."""

from __future__ import annotations

from html import escape
from typing import Any


STATUS_COLORS = {
    "unsupported": ("#fecaca", "#991b1b"),
    "unimplemented": ("#e2e8f0", "#475569"),
    "diagnostic": ("#fef3c7", "#92400e"),
    "comparable": ("#bfdbfe", "#1d4ed8"),
    "claimable": ("#bbf7d0", "#166534"),
}

STATUS_ORDER = {
    "unsupported": 0,
    "unimplemented": 1,
    "diagnostic": 2,
    "comparable": 3,
    "claimable": 4,
}


def safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def format_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def status_color(status: str) -> tuple[str, str]:
    return STATUS_COLORS.get(status, ("#e2e8f0", "#475569"))


def status_badge(status: str) -> str:
    bg, fg = status_color(status)
    return (
        f"<span class='badge' style='background:{bg};color:{fg};'>"
        f"{escape(status)}</span>"
    )


def cell_sort_key(cell: dict[str, Any]) -> tuple[int, str, str]:
    return (
        STATUS_ORDER.get(str(cell.get("status", "unimplemented")), -1),
        str(cell.get("workloadSet", "")),
        str(cell.get("hostProfile", "")),
    )


def build_heatmap_svg(
    *,
    surface: dict[str, Any],
    cells: list[dict[str, Any]],
    host_profiles: dict[str, Any],
    workload_sets: dict[str, Any],
) -> str:
    width_per_col = 156
    height_per_row = 48
    left_margin = 196
    top_margin = 60
    width = left_margin + len(surface["expectedHostProfiles"]) * width_per_col + 12
    height = top_margin + len(surface["workloadSets"]) * height_per_row + 12
    cell_map = {
        (cell["hostProfile"], cell["workloadSet"]): cell
        for cell in cells
    }

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" '
        f'aria-label="{escape(surface["displayName"])} benchmark cube heatmap">'
    ]
    parts.append(
        f"<text x='12' y='24' font-size='18' font-weight='700' fill='#0f172a'>"
        f"{escape(surface['displayName'])} matrix</text>"
    )

    for col_idx, host_id in enumerate(surface["expectedHostProfiles"]):
        x = left_margin + col_idx * width_per_col + 8
        label = host_profiles[host_id]["displayName"]
        parts.append(
            f"<text x='{x + 64}' y='42' text-anchor='middle' font-size='12' fill='#334155'>"
            f"{escape(label)}</text>"
        )

    for row_idx, workload_id in enumerate(surface["workloadSets"]):
        y = top_margin + row_idx * height_per_row
        parts.append(
            f"<text x='12' y='{y + 29}' font-size='12' fill='#334155'>"
            f"{escape(workload_sets[workload_id]['displayName'])}</text>"
        )
        for col_idx, host_id in enumerate(surface["expectedHostProfiles"]):
            x = left_margin + col_idx * width_per_col
            cell = cell_map[(host_id, workload_id)]
            bg, fg = status_color(str(cell.get("status", "unimplemented")))
            delta = format_delta(safe_float(cell.get("deltaP50MedianPercent")))
            label = str(cell.get("status", "unimplemented"))
            parts.append(
                f"<rect x='{x}' y='{y}' width='144' height='36' rx='10' ry='10' "
                f"fill='{bg}' stroke='#cbd5e1'/>"
            )
            parts.append(
                f"<text x='{x + 72}' y='{y + 16}' text-anchor='middle' font-size='12' "
                f"font-weight='700' fill='{fg}'>{escape(label)}</text>"
            )
            parts.append(
                f"<text x='{x + 72}' y='{y + 30}' text-anchor='middle' font-size='11' "
                f"fill='#334155'>{escape(delta)}</text>"
            )
    parts.append("</svg>")
    return "".join(parts)


def build_surface_table_rows(
    *,
    surface: dict[str, Any],
    cells: list[dict[str, Any]],
    host_profiles: dict[str, Any],
    workload_sets: dict[str, Any],
) -> str:
    rows: list[str] = []
    for cell in sorted(cells, key=cell_sort_key, reverse=True):
        host_label = host_profiles[cell["hostProfile"]]["displayName"]
        workload_label = workload_sets[cell["workloadSet"]]["displayName"]
        conformance = str(cell.get("sourceConformance", ""))
        if not conformance and cell.get("reportCount", 0) == 0:
            conformance = "-"
        rows.append(
            "<tr>"
            f"<td>{escape(workload_label)}</td>"
            f"<td>{escape(host_label)}</td>"
            f"<td>{status_badge(str(cell.get('status', 'unimplemented')))}</td>"
            f"<td>{status_badge(str(cell.get('comparisonStatus', cell.get('status', 'unimplemented'))))}</td>"
            f"<td>{status_badge(str(cell.get('claimStatus', cell.get('status', 'unimplemented'))))}</td>"
            f"<td>{escape(str(cell.get('reportCount', 0)))}</td>"
            f"<td>{escape(str(cell.get('rowCount', 0)))}</td>"
            f"<td>{escape(format_delta(safe_float(cell.get('deltaP50MedianPercent'))))}</td>"
            f"<td><code>{escape(str(cell.get('latestGeneratedAt', '-')))}</code></td>"
            f"<td><code>{escape(conformance)}</code></td>"
            "</tr>"
        )
    if rows:
        return "".join(rows)
    return "<tr><td colspan='10'>No cells.</td></tr>"


def build_source_rows(summary: dict[str, Any]) -> str:
    rows: list[str] = []
    source_counts = summary.get("sourceCounts", {})
    labels = {
        "backendReports": "Backend",
        "nodeReports": "Node",
        "bunReports": "Bun",
    }
    for key in ("backendReports", "nodeReports", "bunReports"):
        payload = source_counts.get(key, {})
        rows.append(
            "<tr>"
            f"<td>{escape(labels[key])}</td>"
            f"<td>{escape(str(payload.get('discovered', 0)))}</td>"
            f"<td>{escape(str(payload.get('included', 0)))}</td>"
            f"<td>{escape(str(payload.get('canonicalIncluded', 0)))}</td>"
            f"<td>{escape(str(payload.get('legacyIncluded', 0)))}</td>"
            f"<td>{escape(str(payload.get('skipped', 0)))}</td>"
            "</tr>"
        )
    return "".join(rows)


def build_dashboard_html(summary: dict[str, Any], policy: dict[str, Any]) -> str:
    host_profiles = policy["hostProfiles"]
    workload_sets = policy["workloadSets"]
    raw_policy = policy["raw"]
    cells = summary.get("cells", [])
    generated_at = escape(str(summary.get("generatedAt", "")))
    rows_path = escape(str(summary.get("artifacts", {}).get("rowsPath", "")))
    matrix_path = escape(str(summary.get("artifacts", {}).get("matrixMarkdownPath", "")))
    dashboard_path = escape(str(summary.get("artifacts", {}).get("dashboardHtmlPath", "")))
    source_rows = build_source_rows(summary)

    cards = [
        ("Rows", summary.get("rowCount", 0)),
        ("Cells", len(cells)),
        ("Claimable Cells", summary.get("statusCounts", {}).get("claimable", 0)),
        ("Comparable Cells", summary.get("statusCounts", {}).get("comparable", 0)),
        ("Diagnostic Cells", summary.get("statusCounts", {}).get("diagnostic", 0)),
        ("Unimplemented Cells", summary.get("statusCounts", {}).get("unimplemented", 0)),
    ]
    card_html = "".join(
        "<div class='card'>"
        f"<div class='k'>{escape(label)}</div>"
        f"<div class='v'>{escape(str(value))}</div>"
        "</div>"
        for label, value in cards
    )

    surface_sections: list[str] = []
    for surface in raw_policy["surfaces"]:
        surface_cells = [
            cell for cell in cells if cell.get("surface") == surface["id"]
        ]
        heatmap = build_heatmap_svg(
            surface=surface,
            cells=surface_cells,
            host_profiles=host_profiles,
            workload_sets=workload_sets,
        )
        notes_html = "".join(f"<li>{escape(note)}</li>" for note in surface["notes"])
        table_rows = build_surface_table_rows(
            surface=surface,
            cells=surface_cells,
            host_profiles=host_profiles,
            workload_sets=workload_sets,
        )
        surface_sections.append(
            "<section class='surface'>"
            f"<div class='surface-head'><div><h2>{escape(surface['displayName'])}</h2>"
            f"<div class='sub'>maturity: <code>{escape(surface['maturity'])}</code> | "
            f"primary support: <code>{escape(surface['primarySupport'])}</code></div></div></div>"
            f"<div class='heatmap'>{heatmap}</div>"
            "<div class='notes'><strong>Notes</strong><ul>"
            f"{notes_html}"
            "</ul></div>"
            "<table><thead><tr>"
            "<th>Workload Set</th><th>Host</th><th>Status</th><th>Comparison</th><th>Claim</th>"
            "<th>Reports</th><th>Rows</th><th>Median p50 Delta</th><th>Latest UTC</th><th>Conformance</th>"
            "</tr></thead><tbody>"
            f"{table_rows}"
            "</tbody></table>"
            "</section>"
        )

    legend_html = "".join(
        f"<span class='legend-item'><span class='legend-swatch' style='background:{bg};'></span>{escape(status)}</span>"
        for status, (bg, _fg) in STATUS_COLORS.items()
    )

    return (
        "<!doctype html>"
        "<html lang='en'>"
        "<head>"
        "<meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>Fawn Benchmark Cube</title>"
        "<style>"
        ":root{--ink:#102033;--muted:#526277;--line:#d7e0ea;--bg:#f3f6fb;--panel:#ffffff;--accent:#0f766e;}"
        "*{box-sizing:border-box;}body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:linear-gradient(180deg,#eef4ff 0%,#f8fafc 160px,#f8fafc 100%);color:var(--ink);}"
        "main{max-width:1380px;margin:0 auto;padding:28px 24px 64px;}"
        "h1{margin:0;font-size:34px;line-height:1.1;}h2{margin:0 0 8px 0;font-size:22px;}code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;}"
        ".hero{display:grid;gap:18px;background:rgba(255,255,255,0.72);backdrop-filter:blur(8px);border:1px solid rgba(215,224,234,0.9);border-radius:18px;padding:22px 22px 18px;box-shadow:0 10px 30px rgba(15,23,42,0.06);}"
        ".hero p,.sub,.meta{color:var(--muted);} .meta{font-size:13px;}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:8px;}"
        ".card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 15px;}"
        ".card .k{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;}"
        ".card .v{margin-top:6px;font-size:28px;font-weight:700;}"
        ".legend{display:flex;flex-wrap:wrap;gap:12px 16px;margin-top:8px;font-size:13px;color:var(--muted);}"
        ".legend-item{display:inline-flex;align-items:center;gap:8px;}"
        ".legend-swatch{width:16px;height:16px;border-radius:4px;border:1px solid rgba(15,23,42,0.12);display:inline-block;}"
        ".artifact-list{display:grid;gap:6px;margin-top:8px;font-size:13px;}"
        ".surface{margin-top:28px;padding:20px;background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 24px rgba(15,23,42,0.04);}"
        ".surface-head{display:flex;justify-content:space-between;gap:16px;align-items:end;margin-bottom:10px;}"
        ".heatmap{margin:8px 0 16px 0;padding:12px;background:#f8fafc;border:1px solid var(--line);border-radius:14px;overflow:auto;}"
        ".notes{margin:0 0 14px 0;color:var(--muted);font-size:14px;}"
        ".notes ul{margin:8px 0 0 18px;padding:0;}"
        "table{width:100%;border-collapse:collapse;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fff;}"
        "th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #eef2f7;font-size:13px;vertical-align:top;}"
        "th{background:#edf3fb;color:#334155;font-weight:700;}"
        "tr:last-child td{border-bottom:none;}"
        ".badge{display:inline-block;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:700;text-transform:lowercase;}"
        "@media (max-width:900px){main{padding:18px 14px 40px;}h1{font-size:28px;}.surface{padding:16px;}}"
        "</style>"
        "</head>"
        "<body><main>"
        "<section class='hero'>"
        "<div>"
        "<h1>Benchmark Cube Dashboard</h1>"
        "<p>Cross-surface evidence view for Doe vs Dawn backend, Node, and Bun benchmark lanes.</p>"
        f"<div class='meta'>generated: <code>{generated_at}</code></div>"
        "</div>"
        f"<div class='cards'>{card_html}</div>"
        f"<div class='legend'>{legend_html}</div>"
        "<div class='artifact-list'>"
        f"<div>rows: <code>{rows_path}</code></div>"
        f"<div>matrix: <code>{matrix_path}</code></div>"
        f"<div>dashboard: <code>{dashboard_path}</code></div>"
        "</div>"
        "</section>"
        "<section class='surface'>"
        "<h2>Source Conformance</h2>"
        "<table><thead><tr><th>Source</th><th>Discovered</th><th>Included</th><th>Canonical</th><th>Legacy</th><th>Skipped</th></tr></thead><tbody>"
        f"{source_rows}"
        "</tbody></table>"
        "</section>"
        + "".join(surface_sections)
        + "</main></body></html>"
    )
