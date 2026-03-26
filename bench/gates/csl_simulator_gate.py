#!/usr/bin/env python3
"""Validate governed CSL lane reports and referenced artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)


import argparse
from pathlib import Path

from native_compare_modules import csl_simulator_contract as contract
from native_compare_modules import host_plan_contract


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="bench/out/csl-simulator/csl-gelu-smoke.json")
    parser.add_argument("--report-schema", default="config/csl-governed-lane-report.schema.json")
    parser.add_argument("--host-plan-schema", default="config/doe-wgsl-host-plan.schema.json")
    parser.add_argument("--result-schema", default="config/doe-wgsl-simulator-result.schema.json")
    parser.add_argument("--driver-result-schema", default="config/doe-wgsl-simulator-driver-result.schema.json")
    parser.add_argument("--trace-schema", default="config/doe-wgsl-simulator-trace.schema.json")
    parser.add_argument("--require-ready", action="store_true", help="Fail unless laneStatus=ready.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    report_schema = contract.load_schema(Path(args.report_schema))
    host_plan_schema = host_plan_contract.load_schema(Path(args.host_plan_schema))
    result_schema = contract.load_schema(Path(args.result_schema))
    driver_result_schema = contract.load_schema(Path(args.driver_result_schema))
    trace_schema = contract.load_schema(Path(args.trace_schema))

    failures = contract.validate_artifact(report_path, report_schema)
    if failures:
        print("FAIL: csl simulator gate")
        for item in failures:
            print(f"  {item}")
        return 1

    report = contract.load_json(report_path)
    if args.require_ready and report.get("laneStatus") != "ready":
        print(f"FAIL: laneStatus={report.get('laneStatus')} (expected ready)")
        return 1
    run_payload = report.get("run", {})
    if not isinstance(run_payload, dict):
        run_payload = {}

    artifacts = report.get("artifacts", {})
    if not isinstance(artifacts, dict):
        print("FAIL: report.artifacts missing/invalid")
        return 1

    failures = []
    host_plan_path = artifacts.get("hostPlanArtifactPath")
    host_plan_hash = artifacts.get("hostPlanArtifactHash")
    if isinstance(host_plan_path, str) and host_plan_path:
        failures.extend(
            host_plan_contract.validate_artifact(
                contract.resolve_relative_path(report_path.parent, host_plan_path),
                host_plan_schema,
                expected_hash=host_plan_hash if isinstance(host_plan_hash, str) and host_plan_hash else None,
            )
        )

    result_path = artifacts.get("simulatorResultPath")
    result_hash = artifacts.get("simulatorResultHash")
    if isinstance(result_path, str) and result_path:
        resolved_result_path = contract.resolve_relative_path(report_path.parent, result_path)
        if resolved_result_path.exists():
            failures.extend(
                contract.validate_artifact(
                    resolved_result_path,
                    result_schema,
                    expected_hash=result_hash if isinstance(result_hash, str) and result_hash else None,
                )
            )
        elif run_payload.get("status") == "succeeded":
            failures.append(f"missing simulator result artifact: {resolved_result_path}")

    driver_result_path = artifacts.get("driverResultPath")
    if isinstance(driver_result_path, str) and driver_result_path:
        failures.extend(
            contract.validate_artifact(
                contract.resolve_relative_path(report_path.parent, driver_result_path),
                driver_result_schema,
            )
        )

    trace_path = artifacts.get("tracePath")
    trace_hash = artifacts.get("traceHash")
    if isinstance(trace_path, str) and trace_path:
        resolved_trace_path = contract.resolve_relative_path(report_path.parent, trace_path)
        if resolved_trace_path.exists():
            failures.extend(
                contract.validate_artifact(
                    resolved_trace_path,
                    trace_schema,
                    expected_hash=trace_hash if isinstance(trace_hash, str) and trace_hash else None,
                )
            )
            parity = report.get("parity", {})
            if isinstance(parity, dict) and parity.get("status") == "matched":
                trace_payload = contract.load_json(resolved_trace_path)
                expected_trace = parity.get("traceExpected", {})
                if not isinstance(expected_trace, dict):
                    expected_trace = {}
                parity_errors = contract.evaluate_trace_parity(trace_payload, expected_trace)
                failures.extend(f"trace parity: {item}" for item in parity_errors)
        elif bool(run_payload.get("traceProduced")):
            failures.append(f"missing simulator trace artifact: {resolved_trace_path}")

    if failures:
        print("FAIL: csl simulator gate")
        for item in failures:
            print(f"  {item}")
        return 1

    print(f"PASS: csl simulator gate (laneStatus={report.get('laneStatus')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
