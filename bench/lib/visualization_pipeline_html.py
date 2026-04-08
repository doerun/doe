"""HTML rendering helpers for the benchmark visualization pipeline bundle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bench.lib import visual_report_theme


def artifact_link(
    *,
    page_path: str | Path,
    target_path: str,
    label: str | None = None,
) -> str:
    href = visual_report_theme.relative_href(page_path, target_path)
    target_label = label or Path(target_path).name
    return f"<a href='{href}'><code>{target_label}</code></a>"


def metric_class(value: Any) -> str:
    tone = visual_report_theme.delta_tone(value)
    if tone == "good":
        return "metric-positive"
    if tone == "bad":
        return "metric-negative"
    return "metric-neutral"


def report_tile(report: dict[str, Any], *, page_path: str | Path) -> str:
    selected_p50 = report.get("selectedP50DeltaPercent")
    wall_p50 = report.get("wallP50DeltaPercent")
    comparison_status = str(report.get("comparisonStatus", "unknown"))
    claim_status = str(report.get("claimStatus", "not-evaluated"))
    operator_diff_status = str(report.get("operatorDiffStatus", "unknown"))
    links = [
        f"<div>compare page: {artifact_link(page_path=page_path, target_path=str(report.get('htmlPath', '')))}</div>",
        f"<div>analysis JSON: {artifact_link(page_path=page_path, target_path=str(report.get('analysisPath', '')))}</div>",
        f"<div>source report: {artifact_link(page_path=page_path, target_path=str(report.get('reportPath', '')))}</div>",
    ]
    return (
        "<article class='tile'>"
        f"<h3>{str(report.get('label', 'Compare report'))}</h3>"
        "<div class='badge-row'>"
        f"{visual_report_theme.badge(comparison_status, tone=visual_report_theme.status_tone(comparison_status))}"
        f"{visual_report_theme.badge(claim_status, tone=visual_report_theme.status_tone(claim_status, kind='claim'))}"
        f"{visual_report_theme.badge(str(report.get('claimabilityMode', 'unknown')), tone='info')}"
        "</div>"
        f"<p>{str(report.get('summary', ''))}</p>"
        "<div class='table-shell' style='margin-top:14px; min-width:0;'>"
        "<table style='min-width:0;'>"
        "<thead><tr><th>Metric</th><th>Value</th></tr></thead>"
        "<tbody>"
        f"<tr><td>Selected p50</td><td class='{metric_class(selected_p50)}'>{visual_report_theme.format_delta(selected_p50)}</td></tr>"
        f"<tr><td>Wall p50</td><td class='{metric_class(wall_p50)}'>{visual_report_theme.format_delta(wall_p50)}</td></tr>"
        f"<tr><td>Selected p95</td><td class='{metric_class(report.get('selectedP95DeltaPercent'))}'>{visual_report_theme.format_delta(report.get('selectedP95DeltaPercent'))}</td></tr>"
        f"<tr><td>Wall p95</td><td class='{metric_class(report.get('wallP95DeltaPercent'))}'>{visual_report_theme.format_delta(report.get('wallP95DeltaPercent'))}</td></tr>"
        f"<tr><td>Workloads</td><td>{str(report.get('workloadCount', 0))}</td></tr>"
        f"<tr><td>Comparable rows</td><td>{str(report.get('comparableCount', 0))}</td></tr>"
        f"<tr><td>Operator diff</td><td>{visual_report_theme.badge(operator_diff_status, tone='warn' if 'missing' in operator_diff_status else 'neutral')}</td></tr>"
        "</tbody>"
        "</table>"
        "</div>"
        "<div class='link-list'>"
        f"{''.join(links)}"
        "</div>"
        f"<div class='fine-print'>{str(report.get('timingGuidance', ''))}</div>"
        "</article>"
    )


def dashboard_tile(
    title: str,
    copy: str,
    *,
    page_path: str | Path,
    dashboard_path: str,
    secondary_links: list[tuple[str, str]],
) -> str:
    link_rows = [f"<div>dashboard: {artifact_link(page_path=page_path, target_path=dashboard_path)}</div>"]
    for label, target in secondary_links:
        link_rows.append(f"<div>{label}: {artifact_link(page_path=page_path, target_path=target)}</div>")
    return (
        "<article class='tile'>"
        f"<h3>{title}</h3>"
        f"<p>{copy}</p>"
        "<div class='link-list'>"
        f"{''.join(link_rows)}"
        "</div>"
        "</article>"
    )


def build_index_html(
    summary: dict[str, Any],
    *,
    page_path: str | Path,
) -> str:
    reports = summary.get("reports", [])
    dashboards = summary.get("dashboards", {})
    generated_at = str(summary.get("generatedAtUtc", ""))
    claimable_count = sum(
        1 for report in reports if str(report.get("claimStatus", "")) == "claimable"
    )
    local_claim_count = sum(
        1 for report in reports if str(report.get("claimabilityMode", "")) == "local"
    )
    cards_html = "".join(
        [
            visual_report_theme.stat_card(
                "Compare pages",
                str(len(reports)),
                detail="Per-report HTML pages generated in this bundle.",
            ),
            visual_report_theme.stat_card(
                "Claimable compares",
                str(claimable_count),
                tone="good" if claimable_count else "neutral",
                detail="Top-level compare reports whose current claim status is claimable.",
            ),
            visual_report_theme.stat_card(
                "Local claim lanes",
                str(local_claim_count),
                tone="warn" if local_claim_count else "neutral",
                detail="Reports operating under local claimability mode, not release mode.",
            ),
            visual_report_theme.stat_card(
                "Bundle timestamp",
                str(summary.get("outputTimestamp", "-")),
                detail="Shared run stamp for this visualization bundle.",
            ),
        ]
    )

    report_tiles = "".join(
        report_tile(report, page_path=page_path)
        for report in reports
    )
    dashboard_tiles = "".join(
        [
            dashboard_tile(
                "Benchmark cube",
                "Cross-surface matrix over native, Node, and Bun evidence with status cells, heatmaps, and normalized row summaries.",
                page_path=page_path,
                dashboard_path=str(dashboards.get("cube", {}).get("dashboardHtmlPath", "")),
                secondary_links=[
                    ("rows", str(dashboards.get("cube", {}).get("rowsPath", ""))),
                    ("matrix", str(dashboards.get("cube", {}).get("matrixMarkdownPath", ""))),
                ],
            ),
            dashboard_tile(
                "Inventory dashboard",
                "Repository-wide index of comparable and claimable reports across matrices and tested hardware profiles.",
                page_path=page_path,
                dashboard_path=str(dashboards.get("inventory", {}).get("dashboardHtmlPath", "")),
                secondary_links=[
                    ("inventory", str(dashboards.get("inventory", {}).get("inventoryPath", ""))),
                ],
            ),
        ]
    )

    body_html = (
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>Bundle summary</h2>"
        "<div class='section-copy'>This bundle is the pipeline output for one visualization run: compare pages, cube, inventory, and a stable landing page. It is designed to be shareable inside the repo without hiding the caveats that matter.</div>"
        "</div>"
        "</div>"
        f"<div class='stat-grid'>{cards_html}</div>"
        "</section>"
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>Compare pages</h2>"
        "<div class='section-copy'>Each compare tile surfaces both selected timing and workload-unit wall so fast-path diagnostics are visible without being confused for end-to-end claim numbers.</div>"
        "</div>"
        "</div>"
        f"<div class='tile-grid'>{report_tiles or '<article class=\"tile\"><h3>No compare reports</h3><p>No reports were selected for this bundle.</p></article>'}</div>"
        "</section>"
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>Dashboards</h2>"
        "<div class='section-copy'>The compare pages show individual receipts. The cube and inventory pages answer broader coverage questions across surfaces and matrices.</div>"
        "</div>"
        "</div>"
        f"<div class='tile-grid'>{dashboard_tiles}</div>"
        "</section>"
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>Interpretation guardrails</h2>"
        "<div class='section-copy'>These are the constraints the landing page keeps visible so the bundle stays honest under skeptical reading.</div>"
        "</div>"
        "</div>"
        "<div class='tile-grid'>"
        "<article class='tile'>"
        "<h3>Selected timing is not the whole story</h3>"
        "<p>Where a report records workload-unit wall, that end-to-end view is shown alongside the selected timing view instead of being silently replaced by a larger fast-path delta.</p>"
        "</article>"
        "<article class='tile'>"
        "<h3>Local claimability stays labeled</h3>"
        "<p>This bundle does not blur local claim receipts into release-grade evidence. Claimability mode is shown on every compare tile.</p>"
        "</article>"
        "<article class='tile'>"
        "<h3>Operator-level diff gaps stay visible</h3>"
        "<p>If a report is missing operator manifests, the bundle says so directly. Structural parity is still useful, but it does not become a stronger claim than the evidence supports.</p>"
        "</article>"
        "</div>"
        "</section>"
    )

    return visual_report_theme.render_page(
        title=str(summary.get("title", "Doe visualization pipeline")),
        eyebrow="Doe visualization pipeline",
        headline="Performance bundle",
        intro=(
            "A timestamped landing page over compare receipts and dashboards, built to keep "
            "the interesting numbers visible without flattening the methodology caveats."
        ),
        meta_html=f"generated: <code>{generated_at}</code>",
        hero_extra_html=f"<div class='stat-grid'>{cards_html}</div>",
        body_html=body_html,
    )
