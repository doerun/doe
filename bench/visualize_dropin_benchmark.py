#!/usr/bin/env python3
"""Render drop-in benchmark JSON report as grouped HTML (micro vs end_to_end)."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dropin_benchmark_report.json",
        help="Input JSON report from dropin_benchmark_suite.py.",
    )
    parser.add_argument(
        "--out",
        default="bench/out/dropin_benchmark_report.html",
        help="Output HTML path.",
    )
    return parser.parse_args()


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid report payload: expected object: {path}")
    return payload


def as_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def row_html(item: dict[str, Any]) -> str:
    stats = item.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    return (
        "<tr>"
        f"<td>{html.escape(str(item.get('id', '')))}</td>"
        f"<td>{html.escape(str(item.get('class', '')))}</td>"
        f"<td>{html.escape(str(item.get('samples', '')))}</td>"
        f"<td>{html.escape(str(stats.get('minNs', '')))}</td>"
        f"<td>{html.escape(str(stats.get('p50Ns', '')))}</td>"
        f"<td>{html.escape(str(stats.get('p95Ns', '')))}</td>"
        f"<td>{html.escape(str(stats.get('maxNs', '')))}</td>"
        f"<td>{html.escape(str(stats.get('meanNs', '')))}</td>"
        "</tr>"
    )


def table_html(title: str, rows: list[dict[str, Any]]) -> str:
    body = "".join(row_html(item) for item in rows)
    return (
        f"<h2>{html.escape(title)} ({len(rows)})</h2>"
        "<table>"
        "<thead><tr>"
        "<th>benchmark</th>"
        "<th>class</th>"
        "<th>samples</th>"
        "<th>minNs</th>"
        "<th>p50Ns</th>"
        "<th>p95Ns</th>"
        "<th>maxNs</th>"
        "<th>meanNs</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
    )


def render_html(report: dict[str, Any]) -> str:
    suite = report.get("suiteResult")
    if not isinstance(suite, dict):
        suite = {}

    benchmarks = as_list(suite.get("benchmarks"))
    micro = [item for item in benchmarks if str(item.get("class")) == "micro"]
    end_to_end = [item for item in benchmarks if str(item.get("class")) == "end_to_end"]
    other = [
        item
        for item in benchmarks
        if str(item.get("class")) not in {"micro", "end_to_end"}
    ]

    sections = [
        table_html("Micro Benchmarks", micro),
        table_html("End-to-End Benchmarks", end_to_end),
    ]
    if other:
        sections.append(table_html("Other Benchmarks", other))

    generated_at = html.escape(str(report.get("generatedAtUtc", "")))
    overall_pass = html.escape(str(report.get("pass", "")))
    suite_pass = html.escape(str(suite.get("pass", "")))
    suite_failure = html.escape(str(suite.get("failure", "")))

    return (
        "<!doctype html>"
        "<html><head><meta charset='utf-8'>"
        "<title>Drop-in Benchmark Report</title>"
        "<style>"
        "body{font-family:ui-sans-serif,system-ui;margin:24px;line-height:1.35;}"
        "h1,h2{margin:0 0 10px;}"
        "p{margin:8px 0;}"
        "table{border-collapse:collapse;width:100%;margin:12px 0 24px;}"
        "th,td{border:1px solid #ddd;padding:8px;text-align:right;}"
        "th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left;}"
        "th{background:#f6f8fa;}"
        "code{background:#f3f3f3;padding:2px 4px;border-radius:4px;}"
        "</style></head><body>"
        "<h1>Drop-in Benchmark Report</h1>"
        f"<p>generatedAtUtc: <code>{generated_at}</code></p>"
        f"<p>report pass: <code>{overall_pass}</code> | suite pass: <code>{suite_pass}</code> | failure: <code>{suite_failure}</code></p>"
        f"<p>total benchmarks: <code>{len(benchmarks)}</code></p>"
        f"{''.join(sections)}"
        "</body></html>"
    )


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    out_path = Path(args.out)

    if not report_path.exists():
        print(f"FAIL: missing report: {report_path}")
        return 1

    try:
        payload = load_report(report_path)
        rendered = render_html(payload)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: unable to render drop-in benchmark HTML: {exc}")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(report_path),
                "out": str(out_path),
                "benchmarkCount": len(
                    as_list(
                        (payload.get("suiteResult") if isinstance(payload.get("suiteResult"), dict) else {}).get(
                            "benchmarks"
                        )
                    )
                ),
                "sections": ["micro", "end_to_end"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
