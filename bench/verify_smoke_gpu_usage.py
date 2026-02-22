#!/usr/bin/env python3
"""Validate AMD Vulkan smoke report has explicit GPU probe evidence for both sides."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-fawn.amd.vulkan.smoke.gpu.16mb.json",
        help="Path to compare_dawn_vs_fawn report JSON.",
    )
    parser.add_argument(
        "--require-comparable",
        action="store_true",
        help="Require top-level comparisonStatus=comparable.",
    )
    return parser.parse_args()


def _stats_has_count(stats: dict[str, Any], key: str) -> bool:
    value = stats.get(key)
    return isinstance(value, dict) and int(value.get("count", 0)) > 0


def _resource_ok(workload: dict[str, Any], side: str) -> tuple[bool, str]:
    side_data = workload.get(side, {})
    command_samples = side_data.get("commandSamples") or []
    if not command_samples:
        return False, f"{side}: no command samples"
    resource = command_samples[0].get("resource") or {}
    if not bool(resource.get("gpuMemoryProbeAvailable", False)):
        return False, f"{side}: gpuMemoryProbeAvailable=false"
    if int(resource.get("resourceSampleCount", 0)) <= 0:
        return False, f"{side}: resourceSampleCount=0"
    if int(resource.get("gpuVramUsedPeakBytes", 0)) <= 0:
        return False, f"{side}: gpuVramUsedPeakBytes<=0"
    stats = side_data.get("resourceStats") or {}
    if int(stats.get("gpuProbeAvailableCount", 0)) <= 0:
        return False, f"{side}: resourceStats.gpuProbeAvailableCount=0"
    if not _stats_has_count(stats, "gpuVramUsedPeakBytes"):
        return False, f"{side}: resourceStats.gpuVramUsedPeakBytes missing"
    return True, "ok"


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        raise SystemExit(f"missing report: {report_path}")
    report = json.loads(report_path.read_text())

    if args.require_comparable and report.get("comparisonStatus") != "comparable":
        raise SystemExit(
            f"comparisonStatus={report.get('comparisonStatus')} (expected comparable)"
        )

    workloads = report.get("workloads") or []
    if not workloads:
        raise SystemExit("report has no workloads")

    errors: list[str] = []
    for workload in workloads:
        workload_id = workload.get("id", "<unknown>")
        for side in ("left", "right"):
            ok, reason = _resource_ok(workload, side)
            if not ok:
                errors.append(f"{workload_id}: {reason}")

    if errors:
        joined = "\n".join(errors)
        raise SystemExit(f"gpu smoke verification failed:\n{joined}")

    print(
        "gpu smoke verification passed "
        f"(report={report_path}, workloads={len(workloads)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
