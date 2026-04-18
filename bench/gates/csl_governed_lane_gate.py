#!/usr/bin/env python3
"""Validate governed CSL compile/run/parity reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="bench/out/csl-governed-lane.report.json")
    parser.add_argument("--schema", default="config/csl-governed-lane-report.schema.json")
    parser.add_argument("--require-parity-match", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-compile-success", action="store_true")
    parser.add_argument("--require-run-success", action="store_true")
    parser.add_argument(
        "--require-host-plan-kernel-patterns",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "When the referenced HostPlan has more than one kernel, fail the "
            "gate unless the op-graph receipt carries kernelPatternCount > 0. "
            "Catches the regression where synthesize_operation_graph silently "
            "collapses a heterogeneous HostPlan (270M/E2B) into a single-target "
            "receipt, dropping the per-kernel Doppler pattern binding."
        ),
    )
    return parser.parse_args()


def _count_host_plan_kernels(report: dict[str, Any]) -> int | None:
    """Return the HostPlan kernel count, or None when the referenced
    artifact is unavailable. Missing/unreadable paths are NOT a gate
    failure on their own — the upstream lane runner is already the
    source of truth for whether the HostPlan was produced. The gate
    only consumes the count to decide whether heterogeneous-HostPlan
    coverage is expected."""
    artifacts = report.get("artifacts", {}) or {}
    hp_path_raw = artifacts.get("actualHostPlanPath") or artifacts.get("expectedHostPlanPath")
    if not hp_path_raw:
        return None
    hp_path = Path(hp_path_raw)
    if not hp_path.is_absolute():
        hp_path = (REPO_ROOT / hp_path).resolve()
    if not hp_path.exists():
        return None
    try:
        payload = json.loads(hp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    kernels = payload.get("hostPlan", {}).get("kernels")
    if not isinstance(kernels, list):
        return None
    # Count distinct kernel names — the same name repeated with count > 1
    # is still a single logical kernel from the graph receipt's perspective.
    names = {k.get("name") for k in kernels if isinstance(k, dict) and k.get("name")}
    return len(names)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = (REPO_ROOT / report_path).resolve()
    schema_path = Path(args.schema)
    if not schema_path.is_absolute():
        schema_path = (REPO_ROOT / schema_path).resolve()
    report = load_json(report_path)
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator(schema).validate(report)

    failures: list[str] = []
    if report.get("laneStatus") == "failed":
        failures.append("laneStatus=failed")
    if args.require_parity_match and report.get("parity", {}).get("status") != "matched":
        failures.append(f"parity.status={report.get('parity', {}).get('status')!r}")
    if args.require_compile_success and report.get("compile", {}).get("status") != "succeeded":
        failures.append(f"compile.status={report.get('compile', {}).get('status')!r}")
    if args.require_run_success and report.get("run", {}).get("status") != "succeeded":
        failures.append(f"run.status={report.get('run', {}).get('status')!r}")

    if args.require_host_plan_kernel_patterns:
        hp_kernel_count = _count_host_plan_kernels(report)
        if hp_kernel_count is not None and hp_kernel_count > 1:
            receipt = report.get("receipts", {}).get("operationGraph", {}) or {}
            kernel_pattern_count = receipt.get("kernelPatternCount", 0)
            if not isinstance(kernel_pattern_count, int) or kernel_pattern_count <= 0:
                failures.append(
                    f"receipts.operationGraph.kernelPatternCount={kernel_pattern_count!r} "
                    f"but HostPlan declares {hp_kernel_count} distinct kernels — "
                    f"heterogeneous HostPlan evidence dropped from op-graph receipt"
                )

    if failures:
        print("FAIL: csl governed lane gate")
        for item in failures:
            print(f"  {item}")
        return 1

    print("PASS: csl governed lane gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
