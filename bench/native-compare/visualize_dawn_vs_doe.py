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
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.lib import visual_report_theme


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-doe.json",
        help="Path to a compare-lane JSON report.",
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


def percent_delta(baseline: float, comparison: float) -> float:
    if baseline <= 0.0:
        return 0.0
    return ((comparison / baseline) - 1.0) * 100.0


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


def probability_baseline_faster(baseline: list[float], comparison: list[float]) -> float:
    if not baseline or not comparison:
        return 0.0

    comparison_sorted = sorted(comparison)
    m = len(comparison_sorted)
    score = 0.0
    for value in baseline:
        lo = bisect.bisect_left(comparison_sorted, value)
        hi = bisect.bisect_right(comparison_sorted, value)
        greater = m - hi
        ties = hi - lo
        score += (float(greater) + (0.5 * float(ties))) / float(m)
    return score / float(len(baseline))


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
    baseline = workload.get("baseline", {})
    comparison = workload.get("comparison", {})

    baseline_samples = to_float_list(baseline.get("timingsMs"))
    comparison_samples = to_float_list(comparison.get("timingsMs"))

    baseline_stats_raw = baseline.get("stats", {}) if isinstance(baseline.get("stats"), dict) else {}
    comparison_stats_raw = comparison.get("stats", {}) if isinstance(comparison.get("stats"), dict) else {}

    baseline_stats = sample_stats(baseline_samples)
    comparison_stats = sample_stats(comparison_samples)

    for key, q in (("p10Ms", 0.10), ("p50Ms", 0.5), ("p95Ms", 0.95), ("p99Ms", 0.99)):
        baseline_stats[key] = resolve_stat_ms(baseline_stats_raw, key, baseline_samples, q)
        comparison_stats[key] = resolve_stat_ms(comparison_stats_raw, key, comparison_samples, q)
    baseline_stats["meanMs"] = resolve_stat_ms(baseline_stats_raw, "meanMs", baseline_samples)
    comparison_stats["meanMs"] = resolve_stat_ms(comparison_stats_raw, "meanMs", comparison_samples)

    delta = {
        "p10Percent": percent_delta(baseline_stats["p10Ms"], comparison_stats["p10Ms"]),
        "p50Percent": percent_delta(baseline_stats["p50Ms"], comparison_stats["p50Ms"]),
        "p95Percent": percent_delta(baseline_stats["p95Ms"], comparison_stats["p95Ms"]),
        "p99Percent": percent_delta(baseline_stats["p99Ms"], comparison_stats["p99Ms"]),
        "meanPercent": percent_delta(baseline_stats["meanMs"], comparison_stats["meanMs"]),
    }

    ks_d = ks_statistic(baseline_samples, comparison_samples)
    ks_p = ks_asymptotic_pvalue(ks_d, len(baseline_samples), len(comparison_samples))
    w1 = wasserstein_1d(baseline_samples, comparison_samples)
    superiority = probability_baseline_faster(baseline_samples, comparison_samples)

    ci_p50 = bootstrap_quantile_delta_ci(baseline_samples, comparison_samples, 0.5, bootstrap_iterations, rng)
    ci_p95 = bootstrap_quantile_delta_ci(baseline_samples, comparison_samples, 0.95, bootstrap_iterations, rng)
    ci_p99 = bootstrap_quantile_delta_ci(baseline_samples, comparison_samples, 0.99, bootstrap_iterations, rng)
    timing_interpretation = workload.get("timingInterpretation", {})
    if not isinstance(timing_interpretation, dict):
        timing_interpretation = {}
    selected_timing = timing_interpretation.get("selectedTiming", {})
    if not isinstance(selected_timing, dict):
        selected_timing = {}
    workload_unit_wall = timing_interpretation.get("workloadUnitWall", {})
    if not isinstance(workload_unit_wall, dict):
        workload_unit_wall = {}
    if not workload_unit_wall:
        legacy_workload_unit_wall = timing_interpretation.get("headlineProcessWall", {})
        if isinstance(legacy_workload_unit_wall, dict):
            workload_unit_wall = legacy_workload_unit_wall
    workload_unit_delta = workload_unit_wall.get("deltaPercent", {})
    if not isinstance(workload_unit_delta, dict):
        workload_unit_delta = {}

    return {
        "id": workload.get("id"),
        "domain": workload.get("domain"),
        "comparable": workload.get("comparability", {}).get("comparable"),
        "baselineSampleCount": len(baseline_samples),
        "comparisonSampleCount": len(comparison_samples),
        "baselineStatsMs": baseline_stats,
        "comparisonStatsMs": comparison_stats,
        "deltaPercent": delta,
        "distribution": {
            "ksStatistic": ks_d,
            "ksAsymptoticPValue": ks_p,
            "wassersteinMs": w1,
            "probabilityBaselineFaster": superiority,
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
        "workloadUnitWallDeltaPercent": workload_unit_delta,
        "baselineSamplesMs": baseline_samples,
        "comparisonSamplesMs": comparison_samples,
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
    baseline = analysis.get("baselineSamplesMs", [])
    comparison = analysis.get("comparisonSamplesMs", [])
    if not baseline or not comparison:
        return "<p>No samples for ECDF.</p>"

    x_min = min(min(baseline), min(comparison))
    x_max = max(max(baseline), max(comparison))
    if x_max <= x_min:
        x_max = x_min + 1.0

    margin_left = 52
    margin_right = 10
    margin_top = 12
    margin_bottom = 28
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    baseline_points = ecdf_polyline_points(baseline, x_min, x_max, plot_w, plot_h)
    comparison_points = ecdf_polyline_points(comparison, x_min, x_max, plot_w, plot_h)

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" '
        f'aria-label="ECDF overlay for {escape(str(analysis.get("id", "workload")))}">'
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_w}" height="{plot_h}" fill="#ffffff" stroke="#dbe3ef"/>'
        f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" stroke="#94a3b8"/>'
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#94a3b8"/>'
        f'<polyline fill="none" stroke="#15803d" stroke-width="2" points="{" ".join(f"{margin_left + float(pt.split(",")[0]):.2f},{margin_top + float(pt.split(",")[1]):.2f}" for pt in baseline_points.split() if pt)}"/>'
        f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{" ".join(f"{margin_left + float(pt.split(",")[0]):.2f},{margin_top + float(pt.split(",")[1]):.2f}" for pt in comparison_points.split() if pt)}"/>'
        f'<text x="{margin_left}" y="{height - 6}" font-size="11" fill="#334155">{x_min:.6f} ms</text>'
        f'<text x="{margin_left + plot_w - 88}" y="{height - 6}" font-size="11" fill="#334155">{x_max:.6f} ms</text>'
        f'<text x="{margin_left + 6}" y="{margin_top + 14}" font-size="11" fill="#15803d">baseline</text>'
        f'<text x="{margin_left + 66}" y="{margin_top + 14}" font-size="11" fill="#2563eb">comparison</text>'
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


def metric_class(value: Any) -> str:
    tone = visual_report_theme.delta_tone(value)
    if tone == "good":
        return "metric-positive"
    if tone == "bad":
        return "metric-negative"
    return "metric-neutral"


def generate_html(
    report: dict[str, Any],
    analyses: list[dict[str, Any]],
    title: str,
    max_ecdf_workloads: int,
) -> str:
    comparison_status = report.get("comparisonStatus", "unknown")
    claim_status = report.get("claimStatus", "not-evaluated")
    comparability = report.get("comparabilitySummary", {})
    workload_count = comparability.get("workloadCount", 0)
    non_comparable_count = comparability.get("nonComparableCount", 0)
    comparable_count = max(int(workload_count) - int(non_comparable_count), 0)
    generated_at = report.get("generatedAt", "")
    schema_version = report.get("schemaVersion", "")
    output_timestamp = report.get("outputTimestamp", "")
    timing_policy = report.get("timingInterpretationPolicy", {})
    if not isinstance(timing_policy, dict):
        timing_policy = {}

    overall_delta = report.get("overall", {}).get("deltaPercent", {})
    overall_wall_delta = report.get("overallWorkloadUnitWall", {}).get("deltaPercent", {})
    overall_table = (
        "<div class='table-shell'><table>"
        "<thead><tr><th>Metric</th><th>Delta</th></tr></thead>"
        "<tbody>"
        f"<tr><td>selected p10</td><td class='{metric_class(overall_delta.get('p10Approx'))}'>{fmt_pct(overall_delta.get('p10Approx'))}</td></tr>"
        f"<tr><td>selected p50</td><td class='{metric_class(overall_delta.get('p50Approx'))}'>{fmt_pct(overall_delta.get('p50Approx'))}</td></tr>"
        f"<tr><td>selected p95</td><td class='{metric_class(overall_delta.get('p95Approx'))}'>{fmt_pct(overall_delta.get('p95Approx'))}</td></tr>"
        f"<tr><td>selected p99</td><td class='{metric_class(overall_delta.get('p99Approx'))}'>{fmt_pct(overall_delta.get('p99Approx'))}</td></tr>"
        f"<tr><td>wall p50</td><td class='{metric_class(overall_wall_delta.get('p50Percent'))}'>{fmt_pct(overall_wall_delta.get('p50Percent'))}</td></tr>"
        f"<tr><td>wall p95</td><td class='{metric_class(overall_wall_delta.get('p95Percent'))}'>{fmt_pct(overall_wall_delta.get('p95Percent'))}</td></tr>"
        "</tbody></table>"
        "</div>"
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
            f"<td>{escape(str(analysis.get('baselineSampleCount', 0)))}</td>"
            f"<td>{escape(str(analysis.get('comparisonSampleCount', 0)))}</td>"
            f"<td class='{metric_class(delta.get('p50Percent'))}'>{fmt_pct(delta.get('p50Percent'))}</td>"
            f"<td class='{metric_class(delta.get('p95Percent'))}'>{fmt_pct(delta.get('p95Percent'))}</td>"
            f"<td class='{metric_class(delta.get('p99Percent'))}'>{fmt_pct(delta.get('p99Percent'))}</td>"
            f"<td>{fmt_prob(dist.get('probabilityBaselineFaster'))}</td>"
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
        baseline_stats = analysis.get("baselineStatsMs", {})
        comparison_stats = analysis.get("comparisonStatsMs", {})
        delta = analysis.get("deltaPercent", {})
        workload_unit_delta = analysis.get("workloadUnitWallDeltaPercent", {})
        if not isinstance(workload_unit_delta, dict):
            workload_unit_delta = {}
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
            f"<td>{fmt_ms(baseline_stats.get('p10Ms'))}</td>"
            f"<td>{fmt_ms(baseline_stats.get('p50Ms'))}</td>"
            f"<td>{fmt_ms(baseline_stats.get('p95Ms'))}</td>"
            f"<td>{fmt_ms(baseline_stats.get('p99Ms'))}</td>"
            f"<td>{fmt_ms(comparison_stats.get('p10Ms'))}</td>"
            f"<td>{fmt_ms(comparison_stats.get('p50Ms'))}</td>"
            f"<td>{fmt_ms(comparison_stats.get('p95Ms'))}</td>"
            f"<td>{fmt_ms(comparison_stats.get('p99Ms'))}</td>"
            f"<td class='{metric_class(workload_unit_delta.get('p50Percent'))}'>{fmt_pct(workload_unit_delta.get('p50Percent'))}</td>"
            f"<td class='{metric_class(delta.get('p10Percent'))}'>{fmt_pct(delta.get('p10Percent'))}</td>"
            f"<td class='{metric_class(delta.get('p50Percent'))}'>{fmt_pct(delta.get('p50Percent'))}</td>"
            f"<td class='{metric_class(delta.get('p95Percent'))}'>{fmt_pct(delta.get('p95Percent'))}</td>"
            f"<td class='{metric_class(delta.get('p99Percent'))}'>{fmt_pct(delta.get('p99Percent'))}</td>"
            "</tr>"
        )
        if not analysis.get("comparable") and safe_float(delta.get("p50Percent", 0)) > 50.0:
            speedup_rows.append(row_html)
        else:
            table_rows.append(row_html)

    speedup_section = ""
    if speedup_rows:
        speedup_section = (
            "<section class='section'>\n"
            "  <div class='section-head'>\n"
            "    <div>\n"
            "      <h2>Non-comparable structural wins</h2>\n"
            "      <div class='section-copy'>Rows where Doe is materially faster in a way that the strict apples-to-apples contract does not permit as a direct Doe-versus-Dawn speed claim. They stay visible, but they stay segregated.</div>\n"
            "    </div>\n"
            "  </div>\n"
            "  <div class='table-shell'>\n"
            "    <table>\n"
            "      <thead>\n"
            "        <tr>\n"
            "          <th>workload</th>\n"
            "          <th>domain</th>\n"
            "          <th>comparable</th>\n"
            "          <th>scope</th>\n"
            "          <th>baseline p10 ms</th>\n"
            "          <th>baseline p50 ms</th>\n"
            "          <th>baseline p95 ms</th>\n"
            "          <th>baseline p99 ms</th>\n"
            "          <th>comparison p10 ms</th>\n"
            "          <th>comparison p50 ms</th>\n"
            "          <th>comparison p95 ms</th>\n"
            "          <th>comparison p99 ms</th>\n"
            "          <th>workload-unit wall p50</th>\n"
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

    sorted_by_p50 = sorted(
        analyses,
        key=lambda item: safe_float(item.get("deltaPercent", {}).get("p50Percent")) or float("-inf"),
        reverse=True,
    )
    spotlight_tiles: list[str] = []
    for analysis in sorted_by_p50[: min(3, len(sorted_by_p50))]:
        delta = analysis.get("deltaPercent", {})
        spotlight_tiles.append(
            "<article class='tile'>"
            f"<h3>{escape(str(analysis.get('id', 'workload')))}</h3>"
            "<div class='badge-row'>"
            f"{visual_report_theme.badge('comparable' if analysis.get('comparable') else 'non-comparable', tone='good' if analysis.get('comparable') else 'warn')}"
            f"{visual_report_theme.badge(str(analysis.get('domain', 'domain')), tone='info')}"
            "</div>"
            f"<p>Selected scope {escape(str((analysis.get('selectedTiming', {}) or {}).get('scopeClass', '-')))} with p50 {fmt_pct(delta.get('p50Percent'))}, p95 {fmt_pct(delta.get('p95Percent'))}, and p99 {fmt_pct(delta.get('p99Percent'))}.</p>"
            "</article>"
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

    cards_html = "".join(
        [
            visual_report_theme.stat_card(
                "Comparison",
                str(comparison_status),
                tone=visual_report_theme.status_tone(str(comparison_status)),
                detail="Top-level comparability outcome for this compare report.",
            ),
            visual_report_theme.stat_card(
                "Claim",
                str(claim_status),
                tone=visual_report_theme.status_tone(str(claim_status), kind="claim"),
                detail="Top-level claim outcome after policy evaluation.",
            ),
            visual_report_theme.stat_card(
                "Workloads",
                str(workload_count),
                detail=f"{comparable_count} comparable, {non_comparable_count} non-comparable.",
            ),
            visual_report_theme.stat_card(
                "Selected p50",
                fmt_pct(overall_delta.get("p50Approx")),
                tone=visual_report_theme.delta_tone(overall_delta.get("p50Approx")),
                detail="Methodology-selected timing scope for this compare report.",
            ),
            visual_report_theme.stat_card(
                "Wall p50",
                fmt_pct(overall_wall_delta.get("p50Percent")),
                tone=visual_report_theme.delta_tone(overall_wall_delta.get("p50Percent")),
                detail="Timed workload-unit wall view when present in the report.",
            ),
            visual_report_theme.stat_card(
                "Wall p95",
                fmt_pct(overall_wall_delta.get("p95Percent")),
                tone=visual_report_theme.delta_tone(overall_wall_delta.get("p95Percent")),
                detail="Workload-unit wall tail behavior, separate from narrow execution timing.",
            ),
            visual_report_theme.stat_card(
                "Selected p95",
                fmt_pct(overall_delta.get("p95Approx")),
                tone=visual_report_theme.delta_tone(overall_delta.get("p95Approx")),
                detail="Selected timing tail behavior, which can be narrower than workload wall.",
            ),
            visual_report_theme.stat_card(
                "Output stamp",
                str(output_timestamp or "-"),
                detail=f"Schema v{schema_version}.",
            ),
        ]
    )

    summary_tiles = (
        "<div class='tile-grid'>"
        "<article class='tile'>"
        "<h3>Overall deltas</h3>"
        "<p>This is the top-line approximation across the selected timing scope recorded in the report. Positive means Doe faster because Doe is the baseline side.</p>"
        f"{overall_table}"
        "</article>"
        "<article class='tile'>"
        "<h3>Workload spotlights</h3>"
        "<p>The strongest current rows by p50 delta, regardless of whether the report contains one workload or many.</p>"
        f"<div class='tile-grid'>{''.join(spotlight_tiles) if spotlight_tiles else '<p>No workload rows.</p>'}</div>"
        "</article>"
        "</div>"
    )

    body_html = (
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>Claim surface snapshot</h2>"
        "<div class='section-copy'>The compare page is optimized for quickly answering three questions: is the report comparable, is it claimable, and where do the selected timing and workload-unit wall views agree or diverge when both sides execute the same workload contract.</div>"
        "</div>"
        "<div class='badge-row'>"
        f"{visual_report_theme.badge(str(comparison_status), tone=visual_report_theme.status_tone(str(comparison_status)))}"
        f"{visual_report_theme.badge(str(claim_status), tone=visual_report_theme.status_tone(str(claim_status), kind='claim'))}"
        f"{visual_report_theme.badge(f'{comparable_count} comparable rows', tone='info')}"
        "</div>"
        "</div>"
        f"<div class='stat-grid'>{cards_html}</div>"
        f"<div class='fine-print'>Timing policy: {escape(str(timing_policy.get('guidance', 'No extra timing guidance recorded.')))}</div>"
        "</section>"
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>Summary and standout rows</h2>"
        "<div class='section-copy'>Use this first when you need the high-level direction before digging into the tables and ECDF overlays below. Selected timing and workload-unit wall are kept side by side so fast-path diagnostics do not silently replace end-to-end timing.</div>"
        "</div>"
        "</div>"
        f"{summary_tiles}"
        "</section>"
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>Workload by percentile heatmap</h2>"
        "<div class='section-copy'>A dense view of how each workload moves across p10, p50, p95, and p99 on the selected timing scope.</div>"
        "</div>"
        "</div>"
        "<div class='table-shell' style='padding:12px; overflow:auto; background:rgba(255,255,255,0.6);'>"
        f"{heatmap_svg(analyses)}"
        "</div>"
        "</section>"
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>Distribution diagnostics</h2>"
        "<div class='section-copy'>These diagnostics show whether the delta is broad-based or only visible in a narrow part of the distribution. Probability of superiority, KS, Wasserstein, and bootstrap intervals all stay on the page because tails matter.</div>"
        "</div>"
        "</div>"
        "<div class='table-shell'>"
        "<table>"
        "<thead>"
        "<tr>"
        "<th>workload</th><th>n baseline</th><th>n comparison</th><th>delta p50</th><th>delta p95</th><th>delta p99</th><th>P(baseline&lt;comparison)</th><th>KS D</th><th>KS p</th><th>Wasserstein ms</th><th>CI95 delta p50</th><th>CI95 delta p95</th><th>CI95 delta p99</th>"
        "</tr>"
        "</thead>"
        "<tbody>"
        f"{''.join(distribution_rows)}"
        "</tbody>"
        "</table>"
        "</div>"
        "</section>"
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>Strict workload table</h2>"
        "<div class='section-copy'>Fast-end p10 is shown alongside p50, p95, and p99. The workload-unit wall column stays visible so narrow-scope timing can be read against the full timed-command process wall.</div>"
        "</div>"
        "</div>"
        "<div class='table-shell'>"
        "<table>"
        "<thead>"
        "<tr>"
        "<th>workload</th><th>domain</th><th>comparable</th><th>scope</th><th>baseline p10 ms</th><th>baseline p50 ms</th><th>baseline p95 ms</th><th>baseline p99 ms</th><th>comparison p10 ms</th><th>comparison p50 ms</th><th>comparison p95 ms</th><th>comparison p99 ms</th><th>workload-unit wall p50</th><th>delta p10</th><th>delta p50</th><th>delta p95</th><th>delta p99</th>"
        "</tr>"
        "</thead>"
        "<tbody>"
        f"{''.join(table_rows)}"
        "</tbody>"
        "</table>"
        "</div>"
        "</section>"
        f"{speedup_section}"
        "<section class='section'>"
        "<div class='section-head'>"
        "<div>"
        "<h2>ECDF overlays</h2>"
        "<div class='section-copy'>Each overlay shows the full distribution shape for a workload. This is where it becomes obvious whether the advantage is consistent or whether it only appears in one tail.</div>"
        "</div>"
        "</div>"
        f"{''.join(ecdf_panels)}"
        "</section>"
    )

    meta_html = " | ".join(
        [
            f"generated: <code>{escape(str(generated_at))}</code>",
            f"schema: <code>{escape(str(schema_version))}</code>",
            f"output timestamp: <code>{escape(str(output_timestamp or '-'))}</code>",
        ]
    )

    return visual_report_theme.render_page(
        title=title,
        eyebrow="Doe compare report",
        headline=title,
        intro=(
            "A distribution-first compare view for strict Doe-versus-Dawn benchmarking, "
            "including tails, comparability state, and explicit separation of non-comparable structural wins."
        ),
        meta_html=meta_html,
        hero_extra_html=f"<div class='stat-grid'>{cards_html}</div>",
        body_html=body_html,
    )


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
