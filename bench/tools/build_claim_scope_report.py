#!/usr/bin/env python3
"""Emit claim-scope artifacts that external copy can cite without overgeneralizing."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-doe.json",
        help="Comparison report produced by compare_dawn_vs_doe.py",
    )
    parser.add_argument(
        "--out-json",
        default="bench/out/claim_scope_report.json",
        help="JSON output path.",
    )
    parser.add_argument(
        "--out-md",
        default="bench/out/claim_scope_report.md",
        help="Markdown output path.",
    )
    parser.add_argument(
        "--require-comparison-status",
        default="comparable",
        help="Required top-level comparisonStatus.",
    )
    parser.add_argument(
        "--require-claim-status",
        default="claimable",
        help="Required top-level claimStatus.",
    )
    parser.add_argument(
        "--require-claimability-mode",
        default="release",
        help="Required claimabilityPolicy.mode.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def parse_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            out.append(item)
    return out


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def unique_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def trace_meta_paths(side: dict[str, Any]) -> list[str]:
    raw_samples = side.get("commandSamples")
    if not isinstance(raw_samples, list):
        return []
    paths: list[str] = []
    for sample in raw_samples:
        if not isinstance(sample, dict):
            continue
        raw_path = sample.get("traceMetaPath")
        if isinstance(raw_path, str) and raw_path.strip():
            paths.append(raw_path.strip())
    return unique_paths(paths)


def side_profile(side: dict[str, Any]) -> dict[str, str]:
    last_meta = side.get("lastMeta")
    if not isinstance(last_meta, dict):
        return {}
    profile = last_meta.get("profile")
    if not isinstance(profile, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("vendor", "api", "deviceFamily", "driver"):
        value = profile.get(key)
        if isinstance(value, str) and value:
            out[key] = value
    return out


def side_backend_id(side: dict[str, Any]) -> str:
    last_meta = side.get("lastMeta")
    if not isinstance(last_meta, dict):
        return ""
    value = last_meta.get("backendId")
    return value if isinstance(value, str) else ""


def side_stats(side: dict[str, Any]) -> dict[str, float | None]:
    stats = side.get("stats")
    if not isinstance(stats, dict):
        return {"p50Ms": None, "p95Ms": None, "p99Ms": None}
    return {
        "p50Ms": parse_float(stats.get("p50Ms")),
        "p95Ms": parse_float(stats.get("p95Ms")),
        "p99Ms": parse_float(stats.get("p99Ms")),
    }


def claim_scope_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    workloads = report.get("workloads")
    if not isinstance(workloads, list):
        return []

    report_out_path = report.get("outPath")
    report_path_value = report_out_path if isinstance(report_out_path, str) else ""
    top_comparison_status = report.get("comparisonStatus")
    top_claim_status = report.get("claimStatus")

    rows: list[dict[str, Any]] = []
    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        workload_id = workload.get("id")
        if not isinstance(workload_id, str) or not workload_id:
            continue
        left = workload.get("left")
        right = workload.get("right")
        if not isinstance(left, dict):
            left = {}
        if not isinstance(right, dict):
            right = {}

        comparability = workload.get("comparability")
        if not isinstance(comparability, dict):
            comparability = {}
        claimability = workload.get("claimability")
        if not isinstance(claimability, dict):
            claimability = {}
        timing_interpretation = workload.get("timingInterpretation")
        if not isinstance(timing_interpretation, dict):
            timing_interpretation = {}
        selected_timing = timing_interpretation.get("selectedTiming")
        if not isinstance(selected_timing, dict):
            selected_timing = {}
        headline_process_wall = timing_interpretation.get("headlineProcessWall")
        if not isinstance(headline_process_wall, dict):
            headline_process_wall = {}
        delta = workload.get("deltaPercent")
        if not isinstance(delta, dict):
            delta = {}

        left_timing_sources = parse_string_list(left.get("timingSources"))
        right_timing_sources = parse_string_list(right.get("timingSources"))
        left_timing_classes = parse_string_list(left.get("timingClasses"))
        right_timing_classes = parse_string_list(right.get("timingClasses"))
        left_stats = side_stats(left)
        right_stats = side_stats(right)
        left_backend = side_backend_id(left)
        right_backend = side_backend_id(right)
        left_profile = side_profile(left)
        right_profile = side_profile(right)
        left_meta_paths = trace_meta_paths(left)
        right_meta_paths = trace_meta_paths(right)

        delta_p50 = parse_float(delta.get("p50Percent"))
        delta_p95 = parse_float(delta.get("p95Percent"))
        delta_p99 = parse_float(delta.get("p99Percent"))
        headline_delta = headline_process_wall.get("deltaPercent")
        if not isinstance(headline_delta, dict):
            headline_delta = {}
        headline_delta_p50 = parse_float(headline_delta.get("p50Percent"))
        headline_delta_p95 = parse_float(headline_delta.get("p95Percent"))
        headline_delta_p99 = parse_float(headline_delta.get("p99Percent"))

        citation = (
            f"{workload_id}: comparisonStatus={top_comparison_status}, claimStatus={top_claim_status}, "
            f"workloadComparable={bool(workload.get('workloadComparable'))}, "
            f"workloadComparableNow={comparability.get('comparable')}, "
            f"workloadClaimableNow={claimability.get('claimable')}, "
            f"delta(p50/p95/p99)={delta_p50}/{delta_p95}/{delta_p99}, "
            f"headlineProcessWallDelta(p50/p95/p99)={headline_delta_p50}/{headline_delta_p95}/{headline_delta_p99}, "
            f"selectedScope={selected_timing.get('scope')}/{selected_timing.get('scopeClass')}, "
            f"timingSources(left/right)={left_timing_sources}/{right_timing_sources}, "
            f"backend(left/right)={left_backend}/{right_backend}, report={report_path_value}"
        )

        rows.append(
            {
                "workloadId": workload_id,
                "name": workload.get("name", workload_id),
                "domain": workload.get("domain", ""),
                "reportStatus": {
                    "comparisonStatus": top_comparison_status,
                    "claimStatus": top_claim_status,
                },
                "workloadStatus": {
                    "workloadComparableContract": bool(workload.get("workloadComparable")),
                    "workloadComparableNow": comparability.get("comparable"),
                    "workloadClaimableNow": claimability.get("claimable"),
                },
                "timing": {
                    "leftSources": left_timing_sources,
                    "rightSources": right_timing_sources,
                    "leftClasses": left_timing_classes,
                    "rightClasses": right_timing_classes,
                    "selectedScope": selected_timing.get("scope"),
                    "selectedScopeClass": selected_timing.get("scopeClass"),
                    "selectedIsNarrowHotPath": selected_timing.get("isNarrowHotPath"),
                    "selectedScopeNote": selected_timing.get("note"),
                },
                "performance": {
                    "deltaPercent": {
                        "p50Percent": delta_p50,
                        "p95Percent": delta_p95,
                        "p99Percent": delta_p99,
                    },
                    "headlineProcessWallDeltaPercent": {
                        "p50Percent": headline_delta_p50,
                        "p95Percent": headline_delta_p95,
                        "p99Percent": headline_delta_p99,
                    },
                    "leftStatsMs": left_stats,
                    "rightStatsMs": right_stats,
                    "headlineProcessWallLeftStatsMs": headline_process_wall.get("leftStatsMs", {}),
                    "headlineProcessWallRightStatsMs": headline_process_wall.get("rightStatsMs", {}),
                },
                "runtime": {
                    "leftBackendId": left_backend,
                    "rightBackendId": right_backend,
                    "leftProfile": left_profile,
                    "rightProfile": right_profile,
                },
                "artifacts": {
                    "reportPath": report_path_value,
                    "leftTraceMetaPaths": left_meta_paths,
                    "rightTraceMetaPaths": right_meta_paths,
                },
                "externalCitation": citation,
            }
        )
    return rows


def markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Claim Scope Report")
    lines.append("")
    lines.append(f"- Generated: `{payload.get('generatedAtUtc', '')}`")
    lines.append(f"- Report: `{payload.get('reportPath', '')}`")
    lines.append(f"- Comparison status: `{payload.get('comparisonStatus', '')}`")
    lines.append(f"- Claim status: `{payload.get('claimStatus', '')}`")
    lines.append(f"- Claimability mode: `{payload.get('claimabilityMode', '')}`")
    lines.append(f"- Workloads: `{payload.get('workloadCount', 0)}`")
    lines.append("")
    lines.append("| Workload | Domain | Selected p50% | Headline wall p50% | Scope | Timing (L/R) | Backend (L/R) |")
    lines.append("|---|---|---:|---:|---|---|---|")
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        performance = row.get("performance", {})
        if not isinstance(performance, dict):
            performance = {}
        delta = performance.get("deltaPercent", {})
        if not isinstance(delta, dict):
            delta = {}
        headline_delta = performance.get("headlineProcessWallDeltaPercent", {})
        if not isinstance(headline_delta, dict):
            headline_delta = {}
        timing = row.get("timing", {})
        if not isinstance(timing, dict):
            timing = {}
        runtime = row.get("runtime", {})
        if not isinstance(runtime, dict):
            runtime = {}
        left_sources = ",".join(parse_string_list(timing.get("leftSources")))
        right_sources = ",".join(parse_string_list(timing.get("rightSources")))
        left_backend = runtime.get("leftBackendId", "")
        right_backend = runtime.get("rightBackendId", "")
        selected_scope = timing.get("selectedScopeClass") or timing.get("selectedScope") or ""
        lines.append(
            "| "
            f"{row.get('workloadId', '')} | {row.get('domain', '')} | "
            f"{delta.get('p50Percent', '')} | {headline_delta.get('p50Percent', '')} | {selected_scope} | "
            f"{left_sources} / {right_sources} | {left_backend} / {right_backend} |"
        )
    lines.append("")
    lines.append("## Citation-ready lines")
    lines.append("")
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        citation = row.get("externalCitation", "")
        if isinstance(citation, str) and citation:
            lines.append(f"- {citation}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        print(f"FAIL: missing report: {report_path}")
        return 1

    try:
        report = load_json(report_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1

    comparison_status = report.get("comparisonStatus")
    claim_status = report.get("claimStatus")
    claimability_policy = report.get("claimabilityPolicy")
    claimability_mode = (
        claimability_policy.get("mode")
        if isinstance(claimability_policy, dict)
        else None
    )

    failures: list[str] = []
    if comparison_status != args.require_comparison_status:
        failures.append(
            f"comparisonStatus mismatch: expected {args.require_comparison_status}, got {comparison_status!r}"
        )
    if claim_status != args.require_claim_status:
        failures.append(
            f"claimStatus mismatch: expected {args.require_claim_status}, got {claim_status!r}"
        )
    if claimability_mode != args.require_claimability_mode:
        failures.append(
            f"claimabilityPolicy.mode mismatch: expected {args.require_claimability_mode}, got {claimability_mode!r}"
        )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    rows = claim_scope_rows(report)
    payload = {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "reportPath": str(report_path),
        "comparisonStatus": comparison_status,
        "claimStatus": claim_status,
        "claimabilityMode": claimability_mode,
        "workloadCount": len(rows),
        "rows": rows,
    }

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text(markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "outJson": str(out_json),
                "outMd": str(out_md),
                "workloadCount": len(rows),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
