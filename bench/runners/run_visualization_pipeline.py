#!/usr/bin/env python3
"""Build a timestamped Doe benchmark visualization bundle."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.lib import output_paths
from bench.lib import visualization_pipeline_html

NO_MATCH_GLOB = "bench/out/__visualization_pipeline_no_match__/*.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend-report-glob",
        action="append",
        default=[],
        help="Glob for native/backend compare reports.",
    )
    parser.add_argument(
        "--backend-report",
        action="append",
        default=[],
        help="Explicit native/backend compare report path. May be repeated.",
    )
    parser.add_argument(
        "--node-report-glob",
        action="append",
        default=[],
        help="Glob for Node package compare reports.",
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
        help="Glob for Bun package compare reports.",
    )
    parser.add_argument(
        "--bun-report",
        action="append",
        default=[],
        help="Explicit Bun package compare report path. May be repeated.",
    )
    parser.add_argument(
        "--index-out",
        default="bench/out/visualization/index.html",
        help="Landing HTML path for the timestamped bundle.",
    )
    parser.add_argument(
        "--summary-out",
        default="bench/out/visualization/pipeline.summary.json",
        help="Summary JSON path for the timestamped bundle.",
    )
    parser.add_argument(
        "--latest-index",
        default="bench/out/visualization/latest/index.html",
        help="Stable latest landing HTML path.",
    )
    parser.add_argument(
        "--latest-summary",
        default="bench/out/visualization/latest/pipeline.summary.json",
        help="Stable latest summary JSON path.",
    )
    parser.add_argument(
        "--title",
        default="Doe benchmark visualization pipeline",
        help="Landing page title.",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help="UTC timestamp suffix for the visualization bundle.",
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp the primary outputs into a timestamped run folder.",
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=1000,
        help="Bootstrap iterations forwarded to compare visualization.",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=1337,
        help="Bootstrap seed forwarded to compare visualization.",
    )
    parser.add_argument(
        "--max-ecdf-workloads",
        type=int,
        default=12,
        help="Max workloads rendered as ECDF overlays per compare page.",
    )
    parser.add_argument(
        "--inventory-max-recent-reports",
        type=int,
        default=30,
        help="Max recent reports shown in the inventory dashboard.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def collect_paths(patterns: list[str], explicit_paths: list[str]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for raw in explicit_paths:
        path = Path(raw).resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(path)
    for pattern in patterns:
        for raw in sorted(glob(pattern, recursive=True)):
            path = Path(raw).resolve()
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path)
    return candidates


def run_command(argv: list[str]) -> None:
    subprocess.run(
        argv,
        check=True,
        cwd=REPO_ROOT,
    )


def copy_latest(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "artifact"


def report_slug(path: Path) -> str:
    return slugify(path.stem)


def surface_label(path: Path) -> str:
    path_text = str(path).lower()
    name_text = path.name.lower()
    if "apple-metal" in path_text or ".metal" in name_text:
        return "Apple Metal"
    if "amd-vulkan" in path_text or ".vulkan" in name_text:
        return "AMD Vulkan"
    if "d3d12" in path_text or ".d3d12" in name_text:
        return "Windows D3D12"
    return "Benchmark"


def lane_label(kind: str, path: Path) -> str:
    surface = surface_label(path)
    if kind == "backend":
        return f"{surface} native"
    if kind == "node":
        return f"{surface} Node package"
    return f"{surface} Bun package"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def default_claim_report_path(report_path: Path) -> Path | None:
    name = report_path.name
    if name.endswith(".compare.json"):
        candidate = report_path.with_name(name.replace(".compare.json", ".claim.json"))
        if candidate.exists():
            return candidate
    return None


def load_optional_claim_report(report_path: Path) -> dict[str, Any]:
    candidate = default_claim_report_path(report_path)
    if candidate is None:
        return {}
    payload = load_json(candidate)
    if payload.get("artifactKind") != "claim-report":
        raise ValueError(f"expected claim-report at {candidate}")
    return payload


def summarize_report(
    *,
    label: str,
    report_path: Path,
    html_path: Path,
    analysis_path: Path,
) -> dict[str, Any]:
    payload = load_json(report_path)
    claim_payload = load_optional_claim_report(report_path)
    comparability = payload.get("comparabilitySummary", {})
    operator_diff = payload.get("operatorDiffSummary", {})
    workloads = payload.get("workloads", [])
    comparable_count = 0
    if isinstance(comparability, dict):
        comparable_count = max(
            int(comparability.get("workloadCount", 0))
            - int(comparability.get("nonComparableCount", 0)),
            0,
        )
    operator_status = "unknown"
    if isinstance(operator_diff, dict):
        operator_workloads = operator_diff.get("workloads", [])
        if isinstance(operator_workloads, list) and operator_workloads:
            first = operator_workloads[0]
            if isinstance(first, dict):
                operator_status = str(first.get("status", "unknown"))
    timing_policy = payload.get("timingInterpretationPolicy", {})
    if not isinstance(timing_policy, dict):
        timing_policy = {}
    claim_policy = claim_payload.get("claimPolicy", {})
    if not isinstance(claim_policy, dict):
        claim_policy = {}
    summary = (
        "Selected timing and workload-unit wall are both surfaced here. "
        "Use wall as the conservative end-to-end read when it materially differs."
    )
    return {
        "label": label,
        "summary": summary,
        "reportPath": str(report_path),
        "claimReportPath": (
            str(default_claim_report_path(report_path))
            if default_claim_report_path(report_path) is not None
            else ""
        ),
        "htmlPath": str(html_path),
        "analysisPath": str(analysis_path),
        "comparisonStatus": payload.get("comparisonStatus", "unknown"),
        "claimStatus": claim_payload.get(
            "claimStatus",
            payload.get("claimStatus", "not-evaluated"),
        ),
        "claimabilityMode": claim_policy.get("mode", "not-evaluated"),
        "workloadCount": len(workloads) if isinstance(workloads, list) else 0,
        "comparableCount": comparable_count,
        "selectedP50DeltaPercent": payload.get("overall", {}).get("deltaPercent", {}).get("p50Percent"),
        "selectedP95DeltaPercent": payload.get("overall", {}).get("deltaPercent", {}).get("p95Percent"),
        "wallP50DeltaPercent": payload.get("overallWorkloadUnitWall", {}).get("deltaPercent", {}).get("p50Percent"),
        "wallP95DeltaPercent": payload.get("overallWorkloadUnitWall", {}).get("deltaPercent", {}).get("p95Percent"),
        "timingGuidance": timing_policy.get("guidance", ""),
        "operatorDiffStatus": operator_status,
    }


def main() -> int:
    args = parse_args()
    backend_reports = collect_paths(args.backend_report_glob, args.backend_report)
    node_reports = collect_paths(args.node_report_glob, args.node_report)
    bun_reports = collect_paths(args.bun_report_glob, args.bun_report)
    all_reports = backend_reports + node_reports + bun_reports
    if not all_reports:
        raise ValueError("no compare reports provided to visualization pipeline")

    timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )
    index_out = output_paths.with_timestamp(
        args.index_out,
        timestamp,
        enabled=args.timestamp_output,
        group="visualization",
    ).resolve()
    summary_out = output_paths.with_timestamp(
        args.summary_out,
        timestamp,
        enabled=args.timestamp_output,
        group="visualization",
    ).resolve()
    run_dir = index_out.parent
    latest_index = Path(args.latest_index).resolve()
    latest_summary = Path(args.latest_summary).resolve()
    latest_dir = latest_index.parent
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    report_entries: list[dict[str, Any]] = []
    for kind, reports in (
        ("backend", backend_reports),
        ("node", node_reports),
        ("bun", bun_reports),
    ):
        for report_path in reports:
            slug = report_slug(report_path)
            html_out = run_dir / f"{slug}.html"
            analysis_out = run_dir / f"{slug}.analysis.json"
            title = f"Doe compare report | {lane_label(kind, report_path)}"
            claim_report_path = default_claim_report_path(report_path)
            run_command(
                [
                    sys.executable,
                    "bench/native-compare/visualize_dawn_vs_doe.py",
                    "--report",
                    str(report_path),
                    "--out",
                    str(html_out),
                    "--analysis-out",
                    str(analysis_out),
                    "--title",
                    title,
                    "--bootstrap-iterations",
                    str(max(args.bootstrap_iterations, 0)),
                    "--bootstrap-seed",
                    str(args.bootstrap_seed),
                    "--max-ecdf-workloads",
                    str(max(args.max_ecdf_workloads, 0)),
                    *(
                        ["--claim-report", str(claim_report_path)]
                        if claim_report_path is not None
                        else []
                    ),
                ]
            )
            copy_latest(html_out, latest_dir / html_out.name)
            copy_latest(analysis_out, latest_dir / analysis_out.name)
            report_entries.append(
                summarize_report(
                    label=lane_label(kind, report_path),
                    report_path=report_path,
                    html_path=html_out,
                    analysis_path=analysis_out,
                )
            )

    inventory_json = run_dir / "inventory.json"
    inventory_html = run_dir / "inventory.dashboard.html"
    latest_inventory_json = latest_dir / "inventory.json"
    latest_inventory_html = latest_dir / "inventory.dashboard.html"
    inventory_args = [
        sys.executable,
        "bench/tools/build_test_inventory_dashboard.py",
        "--no-timestamp-output",
        "--report-glob",
        NO_MATCH_GLOB,
        "--inventory-out",
        str(inventory_json),
        "--dashboard-out",
        str(inventory_html),
        "--latest-inventory",
        str(latest_inventory_json),
        "--latest-dashboard",
        str(latest_inventory_html),
        "--max-recent-reports",
        str(max(args.inventory_max_recent_reports, 0)),
    ]
    for report_path in all_reports:
        inventory_args.extend(["--report", str(report_path)])
    run_command(inventory_args)

    cube_summary = run_dir / "cube.summary.json"
    cube_rows = run_dir / "cube.rows.json"
    cube_matrix = run_dir / "cube.matrix.md"
    cube_html = run_dir / "cube.dashboard.html"
    latest_cube_summary = latest_dir / "cube.summary.json"
    latest_cube_rows = latest_dir / "cube.rows.json"
    latest_cube_matrix = latest_dir / "cube.matrix.md"
    latest_cube_html = latest_dir / "cube.dashboard.html"
    cube_args = [
        sys.executable,
        "bench/tools/build_benchmark_cube.py",
        "--no-timestamp-output",
        "--backend-report-glob",
        NO_MATCH_GLOB,
        "--node-report-glob",
        NO_MATCH_GLOB,
        "--bun-report-glob",
        NO_MATCH_GLOB,
        "--summary-out",
        str(cube_summary),
        "--rows-out",
        str(cube_rows),
        "--matrix-md-out",
        str(cube_matrix),
        "--dashboard-html-out",
        str(cube_html),
        "--latest-summary",
        str(latest_cube_summary),
        "--latest-rows",
        str(latest_cube_rows),
        "--latest-matrix-md",
        str(latest_cube_matrix),
        "--latest-dashboard-html",
        str(latest_cube_html),
        "--no-preserve-latest",
    ]
    for report_path in backend_reports:
        cube_args.extend(["--backend-report", str(report_path)])
    for report_path in node_reports:
        cube_args.extend(["--node-report", str(report_path)])
    for report_path in bun_reports:
        cube_args.extend(["--bun-report", str(report_path)])
    run_command(cube_args)

    summary_payload = {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "outputTimestamp": timestamp,
        "title": args.title,
        "reports": report_entries,
        "dashboards": {
            "cube": {
                "summaryPath": str(cube_summary),
                "rowsPath": str(cube_rows),
                "matrixMarkdownPath": str(cube_matrix),
                "dashboardHtmlPath": str(cube_html),
            },
            "inventory": {
                "inventoryPath": str(inventory_json),
                "dashboardHtmlPath": str(inventory_html),
            },
        },
    }
    index_html = visualization_pipeline_html.build_index_html(
        summary_payload,
        page_path=index_out,
    )
    index_out.write_text(index_html, encoding="utf-8")
    write_json(summary_out, summary_payload)
    copy_latest(index_out, latest_index)
    copy_latest(summary_out, latest_summary)

    output_paths.write_run_manifest_for_outputs(
        [
            index_out,
            summary_out,
            inventory_json,
            inventory_html,
            cube_summary,
            cube_rows,
            cube_matrix,
            cube_html,
        ],
        {
            "runType": "visualization-pipeline",
            "title": args.title,
            "status": "passed",
            "indexPath": str(index_out),
            "summaryPath": str(summary_out),
            "compareReportCount": len(report_entries),
        },
    )

    print("PASS: built visualization bundle")
    print(f"index: {index_out}")
    print(f"summary: {summary_out}")
    print(f"latest index: {latest_index}")
    print(f"latest summary: {latest_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
