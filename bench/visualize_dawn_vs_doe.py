#!/usr/bin/env python3
"""
Generate a comparison HTML report with full distribution diagnostics.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import random
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="fawn/bench/out/dawn-vs-doe.json",
        help="Path to compare_dawn_vs_doe.py JSON report",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Output HTML path (default: report path with .html suffix)",
    )
    parser.add_argument(
        "--analysis-out",
        default="",
        help="Optional JSON output for computed distribution metrics",
    )
    parser.add_argument(
        "--title",
        default="Dawn vs Doe Benchmark Report",
        help="HTML report title",
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=1000,
        help="Bootstrap iterations for quantile delta confidence intervals",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=1337,
        help="Seed for bootstrap reproducibility",
    )
    parser.add_argument(
        "--max-ecdf-workloads",
        type=int,
        default=12,
        help="Max number of workloads to render ECDF overlays (0 = all)",
    )
    return parser.parse_args()


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_float_list(values: Any) -> list[float]:
    if not isinstance(values, list):
        return []
    out: list[float] = []
    for value in values:
        parsed = safe_float(value)
        if parsed is not None and math.isfinite(parsed):
            out.append(parsed)
    return out


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int((len(sorted_values) - 1) * p)
    return sorted_values[index]


def percent_delta(left: float, right: float) -> float:
    if left <= 0.0:
        return 0.0
    return ((right / left) - 1.0) * 100.0


def sample_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0.0,
            "minMs": 0.0,
            "maxMs": 0.0,
            "p10Ms": 0.0,
            "p50Ms": 0.0,
            "p95Ms": 0.0,
            "p99Ms": 0.0,
            "meanMs": 0.0,
        }
    return {
        "count": float(len(values)),
        "minMs": min(values),
        "maxMs": max(values),
        "p10Ms": percentile(values, 0.10),
        "p50Ms": percentile(values, 0.5),
        "p95Ms": percentile(values, 0.95),
        "p99Ms": percentile(values, 0.99),
        "meanMs": sum(values) / float(len(values)),
    }


def ks_statistic(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    x = sorted(left)
    y = sorted(right)
    n = len(x)
    m = len(y)
    i = 0
    j = 0
    d = 0.0

    while i < n or j < m:
        if j >= m:
            v = x[i]
        elif i >= n:
            v = y[j]
        else:
            v = x[i] if x[i] <= y[j] else y[j]

        while i < n and x[i] == v:
            i += 1
        while j < m and y[j] == v:
            j += 1

        cdf_x = float(i) / float(n)
        cdf_y = float(j) / float(m)
        gap = abs(cdf_x - cdf_y)
        if gap > d:
            d = gap
    return d


def ks_asymptotic_pvalue(d: float, n: int, m: int) -> float:
    if n <= 0 or m <= 0:
        return 1.0
    if d <= 0.0:
        return 1.0

    n_eff = (float(n) * float(m)) / float(n + m)
    if n_eff <= 0.0:
        return 1.0

    root = math.sqrt(n_eff)
    lam = (root + 0.12 + (0.11 / root)) * d
    if lam <= 0.0:
        return 1.0

    total = 0.0
    for k in range(1, 200):
        sign = 1.0 if (k % 2 == 1) else -1.0
        term = 2.0 * sign * math.exp(-2.0 * (k * k) * (lam * lam))
        total += term
        if abs(term) < 1e-12:
            break

    if total < 0.0:
        return 0.0
    if total > 1.0:
        return 1.0
    return total


def wasserstein_1d(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0

    x = sorted(left)
    y = sorted(right)
    n = len(x)
    m = len(y)
    i = 0
    j = 0
    cdf_x = 0.0
    cdf_y = 0.0
    area = 0.0
    prev = x[0] if x[0] <= y[0] else y[0]

    while i < n or j < m:
        next_x = x[i] if i < n else math.inf
        next_y = y[j] if j < m else math.inf
        nxt = next_x if next_x <= next_y else next_y

        area += abs(cdf_x - cdf_y) * (nxt - prev)

        while i < n and x[i] == nxt:
            i += 1
        while j < m and y[j] == nxt:
            j += 1

        cdf_x = float(i) / float(n)
        cdf_y = float(j) / float(m)
        prev = nxt

    return area


def probability_left_faster(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0

    right_sorted = sorted(right)
    m = len(right_sorted)
    score = 0.0
    for value in left:
        lo = bisect.bisect_left(right_sorted, value)
        hi = bisect.bisect_right(right_sorted, value)
        greater = m - hi
        ties = hi - lo
        score += (float(greater) + (0.5 * float(ties))) / float(m)
    return score / float(len(left))


def bootstrap_quantile_delta_ci(
    left: list[float],
    right: list[float],
    quantile: float,
    iterations: int,
    rng: random.Random,
) -> dict[str, float]:
    if not left or not right or iterations <= 0:
        return {"lower": 0.0, "upper": 0.0}

    n_left = len(left)
    n_right = len(right)
    samples: list[float] = []

    for _ in range(iterations):
        boot_left = [left[rng.randrange(n_left)] for _ in range(n_left)]
        boot_right = [right[rng.randrange(n_right)] for _ in range(n_right)]
        boot_delta = percent_delta(percentile(boot_left, quantile), percentile(boot_right, quantile))
        samples.append(boot_delta)

    return {
        "lower": percentile(samples, 0.025),
        "upper": percentile(samples, 0.975),
    }


def workload_quantile_delta(left: list[float], right: list[float], q: float) -> float:
    return percent_delta(percentile(left, q), percentile(right, q))


def resolve_stat_ms(stats: dict[str, Any], key: str, samples: list[float], q: float | None = None) -> float:
    value = safe_float(stats.get(key))
    if value is not None:
        return value
    if q is not None:
        return percentile(samples, q)
    if key == "meanMs":
        return (sum(samples) / float(len(samples))) if samples else 0.0
    if key == "minMs":
        return min(samples) if samples else 0.0
    if key == "maxMs":
        return max(samples) if samples else 0.0
    return 0.0


def analyze_workload(
    workload: dict[str, Any],
    bootstrap_iterations: int,
    rng: random.Random,
) -> dict[str, Any]:
    left = workload.get("left", {})
    right = workload.get("right", {})

    left_samples = to_float_list(left.get("timingsMs"))
    right_samples = to_float_list(right.get("timingsMs"))

    left_stats_raw = left.get("stats", {}) if isinstance(left.get("stats"), dict) else {}
    right_stats_raw = right.get("stats", {}) if isinstance(right.get("stats"), dict) else {}

    left_stats = sample_stats(left_samples)
    right_stats = sample_stats(right_samples)

    for key, q in (("p10Ms", 0.10), ("p50Ms", 0.5), ("p95Ms", 0.95), ("p99Ms", 0.99)):
        left_stats[key] = resolve_stat_ms(left_stats_raw, key, left_samples, q)
        right_stats[key] = resolve_stat_ms(right_stats_raw, key, right_samples, q)
    left_stats["meanMs"] = resolve_stat_ms(left_stats_raw, "meanMs", left_samples)
    right_stats["meanMs"] = resolve_stat_ms(right_stats_raw, "meanMs", right_samples)

    delta = {
        "p10Percent": percent_delta(left_stats["p10Ms"], right_stats["p10Ms"]),
        "p50Percent": percent_delta(left_stats["p50Ms"], right_stats["p50Ms"]),
        "p95Percent": percent_delta(left_stats["p95Ms"], right_stats["p95Ms"]),
        "p99Percent": percent_delta(left_stats["p99Ms"], right_stats["p99Ms"]),
        "meanPercent": percent_delta(left_stats["meanMs"], right_stats["meanMs"]),
    }

    ks_d = ks_statistic(left_samples, right_samples)
    ks_p = ks_asymptotic_pvalue(ks_d, len(left_samples), len(right_samples))
    w1 = wasserstein_1d(left_samples, right_samples)
    superiority = probability_left_faster(left_samples, right_samples)

    ci_p50 = bootstrap_quantile_delta_ci(left_samples, right_samples, 0.5, bootstrap_iterations, rng)
    ci_p95 = bootstrap_quantile_delta_ci(left_samples, right_samples, 0.95, bootstrap_iterations, rng)
    ci_p99 = bootstrap_quantile_delta_ci(left_samples, right_samples, 0.99, bootstrap_iterations, rng)
    timing_interpretation = workload.get("timingInterpretation", {})
    if not isinstance(timing_interpretation, dict):
        timing_interpretation = {}
    selected_timing = timing_interpretation.get("selectedTiming", {})
    if not isinstance(selected_timing, dict):
        selected_timing = {}
    headline_process_wall = timing_interpretation.get("headlineProcessWall", {})
    if not isinstance(headline_process_wall, dict):
        headline_process_wall = {}
    headline_delta = headline_process_wall.get("deltaPercent", {})
    if not isinstance(headline_delta, dict):
        headline_delta = {}

    return {
        "id": workload.get("id"),
        "domain": workload.get("domain"),
        "comparable": workload.get("comparability", {}).get("comparable"),
        "leftSampleCount": len(left_samples),
        "rightSampleCount": len(right_samples),
        "leftStatsMs": left_stats,
        "rightStatsMs": right_stats,
        "deltaPercent": delta,
        "distribution": {
            "ksStatistic": ks_d,
            "ksAsymptoticPValue": ks_p,
            "wassersteinMs": w1,
            "probabilityLeftFaster": superiority,
        },
        "bootstrapDeltaCI95": {
            "p50": ci_p50,
            "p95": ci_p95,
            "p99": ci_p99,
        },
        "selectedTiming": {
            "scope": selected_timing.get("scope"),
            "scopeClass": selected_timing.get("scopeClass"),
            "note": selected_timing.get("note"),
        },
        "headlineProcessWallDeltaPercent": headline_delta,
        "leftSamplesMs": left_samples,
        "rightSamplesMs": right_samples,
    }


def fmt_ms(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:.6f}"


def fmt_pct(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:+.3f}%"


def fmt_prob(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:.4f}"


def fmt_float(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:.6f}"


def pick_delta_color(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "#475569"
    return "#166534" if parsed >= 0 else "#b91c1c"


def color_mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def color_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def heatmap_color(value: float, max_abs: float) -> str:
    if max_abs <= 0.0:
        return "#f8fafc"
    t = min(abs(value) / max_abs, 1.0)
    if value >= 0.0:
        return color_hex(color_mix((240, 253, 244), (22, 101, 52), t))
    return color_hex(color_mix((254, 242, 242), (153, 27, 27), t))


def ecdf_polyline_points(samples: list[float], x_min: float, x_max: float, width: int, height: int) -> str:
    if not samples:
        return ""
    sorted_samples = sorted(samples)
    n = len(sorted_samples)
    if x_max <= x_min:
        x_max = x_min + 1e-9

    points: list[str] = []
    for idx, value in enumerate(sorted_samples):
        x_norm = (value - x_min) / (x_max - x_min)
        y_norm = float(idx + 1) / float(n)
        px = x_norm * width
        py = height - (y_norm * height)
        points.append(f"{px:.2f},{py:.2f}")
    return " ".join(points)


def ecdf_svg(analysis: dict[str, Any], width: int = 920, height: int = 220) -> str:
    left = analysis.get("leftSamplesMs", [])
    right = analysis.get("rightSamplesMs", [])
    if not left or not right:
        return "<p>No samples for ECDF.</p>"

    x_min = min(min(left), min(right))
    x_max = max(max(left), max(right))
    if x_max <= x_min:
        x_max = x_min + 1.0

    margin_left = 52
    margin_right = 10
    margin_top = 12
    margin_bottom = 28
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    left_points = ecdf_polyline_points(left, x_min, x_max, plot_w, plot_h)
    right_points = ecdf_polyline_points(right, x_min, x_max, plot_w, plot_h)

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" '
        f'aria-label="ECDF overlay for {escape(str(analysis.get("id", "workload")))}">'
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_w}" height="{plot_h}" fill="#ffffff" stroke="#dbe3ef"/>'
        f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" stroke="#94a3b8"/>'
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#94a3b8"/>'
        f'<polyline fill="none" stroke="#15803d" stroke-width="2" points="{" ".join(f"{margin_left + float(pt.split(",")[0]):.2f},{margin_top + float(pt.split(",")[1]):.2f}" for pt in left_points.split() if pt)}"/>'
        f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{" ".join(f"{margin_left + float(pt.split(",")[0]):.2f},{margin_top + float(pt.split(",")[1]):.2f}" for pt in right_points.split() if pt)}"/>'
        f'<text x="{margin_left}" y="{height - 6}" font-size="11" fill="#334155">{x_min:.6f} ms</text>'
        f'<text x="{margin_left + plot_w - 88}" y="{height - 6}" font-size="11" fill="#334155">{x_max:.6f} ms</text>'
        f'<text x="{margin_left + 6}" y="{margin_top + 14}" font-size="11" fill="#15803d">left</text>'
        f'<text x="{margin_left + 46}" y="{margin_top + 14}" font-size="11" fill="#2563eb">right</text>'
        "</svg>"
    )


def heatmap_svg(analyses: list[dict[str, Any]]) -> str:
    quantiles = [("p10Percent", "p10"), ("p50Percent", "p50"), ("p95Percent", "p95"), ("p99Percent", "p99")]
    values: list[float] = []
    for analysis in analyses:
        delta = analysis.get("deltaPercent", {})
        for key, _ in quantiles:
            value = safe_float(delta.get(key))
            if value is not None:
                values.append(value)

    max_abs = max((abs(v) for v in values), default=1.0)
    if max_abs <= 0.0:
        max_abs = 1.0

    row_h = 28
    col_w = 90
    label_w = 260
    header_h = 30
    width = label_w + col_w * len(quantiles) + 12
    height = header_h + row_h * max(len(analyses), 1) + 12

    parts: list[str] = []
    parts.append(f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" aria-label="Workload percentile heatmap">')
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')

    for col, (_, label) in enumerate(quantiles):
        x = label_w + col * col_w
        parts.append(f'<text x="{x + 8}" y="20" font-size="12" fill="#334155">{label}</text>')

    for row, analysis in enumerate(analyses):
        y = header_h + row * row_h
        workload_id = escape(str(analysis.get("id", "")))
        parts.append(f'<text x="8" y="{y + 18}" font-size="12" fill="#0f172a">{workload_id}</text>')
        delta = analysis.get("deltaPercent", {})
        for col, (key, _) in enumerate(quantiles):
            value = safe_float(delta.get(key)) or 0.0
            x = label_w + col * col_w
            fill = heatmap_color(value, max_abs)
            text_color = "#ffffff" if abs(value) / max_abs > 0.6 else "#111827"
            parts.append(f'<rect x="{x}" y="{y}" width="{col_w - 2}" height="{row_h - 2}" fill="{fill}" rx="3" ry="3"/>')
            parts.append(f'<text x="{x + 8}" y="{y + 18}" font-size="11" fill="{text_color}">{value:+.2f}%</text>')

    parts.append("</svg>")
    return "".join(parts)


def generate_html(
    report: dict[str, Any],
    analyses: list[dict[str, Any]],
    title: str,
    max_ecdf_workloads: int,
) -> str:
    comparison_status = report.get("comparisonStatus", "unknown")
    comparability = report.get("comparabilitySummary", {})
    workload_count = comparability.get("workloadCount", 0)
    non_comparable_count = comparability.get("nonComparableCount", 0)
    generated_at = report.get("generatedAt", "")
    schema_version = report.get("schemaVersion", "")

    overall_delta = report.get("overall", {}).get("deltaPercent", {})
    overall_table = (
        "<table>"
        "<thead><tr><th>Metric</th><th>Delta</th></tr></thead>"
        "<tbody>"
        f"<tr><td>p10Approx</td><td style='color:{pick_delta_color(overall_delta.get('p10Approx'))};font-weight:700'>{fmt_pct(overall_delta.get('p10Approx'))}</td></tr>"
        f"<tr><td>p50Approx</td><td style='color:{pick_delta_color(overall_delta.get('p50Approx'))};font-weight:700'>{fmt_pct(overall_delta.get('p50Approx'))}</td></tr>"
        f"<tr><td>p95Approx</td><td style='color:{pick_delta_color(overall_delta.get('p95Approx'))};font-weight:700'>{fmt_pct(overall_delta.get('p95Approx'))}</td></tr>"
        f"<tr><td>p99Approx</td><td style='color:{pick_delta_color(overall_delta.get('p99Approx'))};font-weight:700'>{fmt_pct(overall_delta.get('p99Approx'))}</td></tr>"
        "</tbody></table>"
    )

    distribution_rows: list[str] = []
    for analysis in analyses:
        delta = analysis.get("deltaPercent", {})
        dist = analysis.get("distribution", {})
        ci = analysis.get("bootstrapDeltaCI95", {})
        c50 = ci.get("p50", {})
        c95 = ci.get("p95", {})
        c99 = ci.get("p99", {})
        distribution_rows.append(
            "<tr>"
            f"<td>{escape(str(analysis.get('id', '')))}</td>"
            f"<td>{escape(str(analysis.get('leftSampleCount', 0)))}</td>"
            f"<td>{escape(str(analysis.get('rightSampleCount', 0)))}</td>"
            f"<td style='color:{pick_delta_color(delta.get('p50Percent'))};font-weight:600'>{fmt_pct(delta.get('p50Percent'))}</td>"
            f"<td style='color:{pick_delta_color(delta.get('p95Percent'))};font-weight:600'>{fmt_pct(delta.get('p95Percent'))}</td>"
            f"<td style='color:{pick_delta_color(delta.get('p99Percent'))};font-weight:600'>{fmt_pct(delta.get('p99Percent'))}</td>"
            f"<td>{fmt_prob(dist.get('probabilityLeftFaster'))}</td>"
            f"<td>{fmt_float(dist.get('ksStatistic'))}</td>"
            f"<td>{fmt_float(dist.get('ksAsymptoticPValue'))}</td>"
            f"<td>{fmt_ms(dist.get('wassersteinMs'))}</td>"
            f"<td>[{fmt_pct(c50.get('lower'))}, {fmt_pct(c50.get('upper'))}]</td>"
            f"<td>[{fmt_pct(c95.get('lower'))}, {fmt_pct(c95.get('upper'))}]</td>"
            f"<td>[{fmt_pct(c99.get('lower'))}, {fmt_pct(c99.get('upper'))}]</td>"
            "</tr>"
        )

    table_rows: list[str] = []
    speedup_rows: list[str] = []
    for analysis in analyses:
        left_stats = analysis.get("leftStatsMs", {})
        right_stats = analysis.get("rightStatsMs", {})
        delta = analysis.get("deltaPercent", {})
        headline_delta = analysis.get("headlineProcessWallDeltaPercent", {})
        if not isinstance(headline_delta, dict):
            headline_delta = {}
        selected_timing = analysis.get("selectedTiming", {})
        if not isinstance(selected_timing, dict):
            selected_timing = {}
        selected_scope = selected_timing.get("scopeClass") or selected_timing.get("scope") or "-"
        comparable_text = "yes" if analysis.get("comparable") else "no"

        row_html = (
            "<tr>"
            f"<td>{escape(str(analysis.get('id', '')))}</td>"
            f"<td>{escape(str(analysis.get('domain', '')))}</td>"
            f"<td>{escape(comparable_text)}</td>"
            f"<td>{escape(str(selected_scope))}</td>"
            f"<td>{fmt_ms(left_stats.get('p10Ms'))}</td>"
            f"<td>{fmt_ms(left_stats.get('p50Ms'))}</td>"
            f"<td>{fmt_ms(left_stats.get('p95Ms'))}</td>"
            f"<td>{fmt_ms(left_stats.get('p99Ms'))}</td>"
            f"<td>{fmt_ms(right_stats.get('p10Ms'))}</td>"
            f"<td>{fmt_ms(right_stats.get('p50Ms'))}</td>"
            f"<td>{fmt_ms(right_stats.get('p95Ms'))}</td>"
            f"<td>{fmt_ms(right_stats.get('p99Ms'))}</td>"
            f"<td style='color:{pick_delta_color(headline_delta.get('p50Percent'))};font-weight:600'>{fmt_pct(headline_delta.get('p50Percent'))}</td>"
            f"<td style='color:{pick_delta_color(delta.get('p10Percent'))};font-weight:600'>{fmt_pct(delta.get('p10Percent'))}</td>"
            f"<td style='color:{pick_delta_color(delta.get('p50Percent'))};font-weight:600'>{fmt_pct(delta.get('p50Percent'))}</td>"
            f"<td style='color:{pick_delta_color(delta.get('p95Percent'))};font-weight:600'>{fmt_pct(delta.get('p95Percent'))}</td>"
            f"<td style='color:{pick_delta_color(delta.get('p99Percent'))};font-weight:600'>{fmt_pct(delta.get('p99Percent'))}</td>"
            "</tr>"
        )
        if not analysis.get("comparable") and safe_float(delta.get("p50Percent", 0)) > 50.0:
            speedup_rows.append(row_html)
        else:
            table_rows.append(row_html)

    speedup_section = ""
    if speedup_rows:
        speedup_section = (
            "<section class=\"panel\">\n"
            "  <h2>Fawn Architectural Speedups (Non-Comparable Context)</h2>\n"
            "  <div class=\"meta\">Workloads where Fawn bypasses C++ API overhead using native WebGPU/Zig features (e.g. multi_draw_indirect). Excluded from the strict Apples-to-Apples metrics.</div>\n"
            "  <div class=\"table-wrap\">\n"
            "    <table>\n"
            "      <thead>\n"
            "        <tr>\n"
            "          <th>workload</th>\n"
            "          <th>domain</th>\n"
            "          <th>comparable</th>\n"
            "          <th>scope</th>\n"
            "          <th>left p10 ms</th>\n"
            "          <th>left p50 ms</th>\n"
            "          <th>left p95 ms</th>\n"
            "          <th>left p99 ms</th>\n"
            "          <th>right p10 ms</th>\n"
            "          <th>right p50 ms</th>\n"
            "          <th>right p95 ms</th>\n"
            "          <th>right p99 ms</th>\n"
            "          <th>headline wall p50</th>\n"
            "          <th>delta p10</th>\n"
            "          <th>delta p50</th>\n"
            "          <th>delta p95</th>\n"
            "          <th>delta p99</th>\n"
            "        </tr>\n"
            "      </thead>\n"
            "      <tbody>\n"
            f"        {''.join(speedup_rows)}\n"
            "      </tbody>\n"
            "    </table>\n"
            "  </div>\n"
            "</section>\n"
        )

    ecdf_source = analyses
    if max_ecdf_workloads > 0:
        ecdf_source = analyses[:max_ecdf_workloads]

    ecdf_panels: list[str] = []
    for analysis in ecdf_source:
        ecdf_panels.append(
            "<details>"
            f"<summary>{escape(str(analysis.get('id', 'workload')))}</summary>"
            f"{ecdf_svg(analysis)}"
            "</details>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #0f172a;
      --muted: #475569;
      --border: #dbe3ef;
    }}
    body {{
      margin: 0;
      padding: 24px;
      background: linear-gradient(180deg, #f8fafc 0%, #eef3fb 100%);
      color: var(--text);
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
      max-width: 1500px;
      margin: 0 auto;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 4px 20px rgba(15, 23, 42, 0.05);
    }}
    h1, h2 {{
      margin: 0 0 12px;
      letter-spacing: 0.2px;
    }}
    h1 {{ font-size: 24px; }}
    h2 {{ font-size: 18px; }}
    .meta {{
      color: var(--muted);
      font-size: 14px;
      margin-bottom: 10px;
    }}
    .kpis {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .kpi {{
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px 12px;
      min-width: 180px;
      background: #fcfdff;
    }}
    .kpi .label {{
      color: var(--muted);
      font-size: 12px;
    }}
    .kpi .value {{
      font-size: 18px;
      font-weight: 700;
      margin-top: 4px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 6px 8px;
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child, td:first-child,
    th:nth-child(2), td:nth-child(2),
    th:nth-child(3), td:nth-child(3) {{
      text-align: left;
    }}
    thead th {{
      position: sticky;
      top: 0;
      background: #f8fafc;
      z-index: 1;
    }}
    .table-wrap {{
      overflow: auto;
      max-height: 560px;
      border: 1px solid var(--border);
      border-radius: 10px;
    }}
    details {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px;
      margin-bottom: 8px;
      background: #fcfdff;
    }}
    summary {{
      cursor: pointer;
      font-weight: 600;
      margin-bottom: 8px;
    }}
    @media (max-width: 900px) {{
      body {{ padding: 12px; }}
    }}
  </style>
</head>
<body>
  <div class="grid">
    <section class="panel">
      <h1>{escape(title)}</h1>
      <div class="meta">generatedAt={escape(str(generated_at))} | schemaVersion={escape(str(schema_version))}</div>
      <div class="kpis">
        <div class="kpi"><div class="label">comparisonStatus</div><div class="value">{escape(str(comparison_status))}</div></div>
        <div class="kpi"><div class="label">workloadCount</div><div class="value">{escape(str(workload_count))}</div></div>
        <div class="kpi"><div class="label">nonComparableCount</div><div class="value">{escape(str(non_comparable_count))}</div></div>
      </div>
    </section>
    <section class="panel">
      <h2>Overall Delta Summary</h2>
      {overall_table}
    </section>
    <section class="panel">
      <h2>Workload x Percentile Delta Heatmap</h2>
      {heatmap_svg(analyses)}
    </section>
    <section class="panel">
      <h2>Distribution Diagnostics</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>workload</th>
              <th>n left</th>
              <th>n right</th>
              <th>delta p50</th>
              <th>delta p95</th>
              <th>delta p99</th>
              <th>P(left&lt;right)</th>
              <th>KS D</th>
              <th>KS p (asymptotic)</th>
              <th>Wasserstein ms</th>
              <th>CI95 delta p50</th>
              <th>CI95 delta p95</th>
              <th>CI95 delta p99</th>
            </tr>
          </thead>
          <tbody>
            {"".join(distribution_rows)}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <h2>Workload Table (Strict Baseline)</h2>
      <div class="meta">Fast-end metric shown is p10. Headline wall p50 is the honest timed-command process-wall view; selected deltas may be narrower in encode-only lanes.</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>workload</th>
              <th>domain</th>
              <th>comparable</th>
              <th>scope</th>
              <th>left p10 ms</th>
              <th>left p50 ms</th>
              <th>left p95 ms</th>
              <th>left p99 ms</th>
              <th>right p10 ms</th>
              <th>right p50 ms</th>
              <th>right p95 ms</th>
              <th>right p99 ms</th>
              <th>headline wall p50</th>
              <th>delta p10</th>
              <th>delta p50</th>
              <th>delta p95</th>
              <th>delta p99</th>
            </tr>
          </thead>
          <tbody>
            {"".join(table_rows)}
          </tbody>
        </table>
      </div>
    </section>
    {speedup_section}
    <section class="panel">
      <h2>ECDF Overlays</h2>
      {"".join(ecdf_panels)}
    </section>
  </div>
</body>
</html>
"""


def analyze_report(
    report: dict[str, Any],
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> list[dict[str, Any]]:
    workloads = report.get("workloads", [])
    if not isinstance(workloads, list):
        return []

    rng = random.Random(bootstrap_seed)
    analyses: list[dict[str, Any]] = []
    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        analyses.append(analyze_workload(workload, bootstrap_iterations, rng))

    return analyses


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        raise FileNotFoundError(f"report not found: {report_path}")

    out_path = Path(args.out) if args.out else report_path.with_suffix(".html")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    analyses = analyze_report(
        report,
        bootstrap_iterations=max(args.bootstrap_iterations, 0),
        bootstrap_seed=args.bootstrap_seed,
    )

    html = generate_html(
        report,
        analyses,
        args.title,
        max_ecdf_workloads=args.max_ecdf_workloads,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    if args.analysis_out:
        analysis_payload = {
            "schemaVersion": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "sourceReport": str(report_path),
            "bootstrapIterations": max(args.bootstrap_iterations, 0),
            "bootstrapSeed": args.bootstrap_seed,
            "workloads": analyses,
        }
        analysis_out = Path(args.analysis_out)
        analysis_out.parent.mkdir(parents=True, exist_ok=True)
        analysis_out.write_text(json.dumps(analysis_payload, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "report": str(report_path),
                "out": str(out_path),
                "workloadCount": len(report.get("workloads", [])),
                "comparisonStatus": report.get("comparisonStatus", "unknown"),
                "analysisOut": args.analysis_out,
                "bootstrapIterations": max(args.bootstrap_iterations, 0),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
