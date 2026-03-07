#!/usr/bin/env python3
"""Top-level drop-in compatibility gate (symbols + behavior + benchmarks)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact",
        default="zig/zig-out/lib/libwebgpu_doe.so",
        help="Path to candidate drop-in shared library artifact.",
    )
    parser.add_argument(
        "--symbols",
        default="config/dropin_abi.symbols.txt",
        help="Required symbol list for symbol gate.",
    )
    parser.add_argument(
        "--symbol-report",
        default="bench/out/dropin_symbol_report.json",
        help="Symbol gate report path.",
    )
    parser.add_argument(
        "--behavior-report",
        default="bench/out/dropin_behavior_report.json",
        help="Behavior suite report path.",
    )
    parser.add_argument(
        "--benchmark-report",
        default="bench/out/dropin_benchmark_report.json",
        help="Benchmark suite report path.",
    )
    parser.add_argument(
        "--benchmark-html",
        default="bench/out/dropin_benchmark_report.html",
        help="Benchmark visualization HTML output path.",
    )
    parser.add_argument(
        "--report",
        default="bench/out/dropin_report.json",
        help="Top-level consolidated report path.",
    )
    parser.add_argument(
        "--micro-iterations",
        type=int,
        default=30,
        help="Micro benchmark iterations.",
    )
    parser.add_argument(
        "--e2e-iterations",
        type=int,
        default=10,
        help="End-to-end benchmark iterations.",
    )
    parser.add_argument(
        "--skip-benchmarks",
        action="store_true",
        help="Skip drop-in benchmark suite execution.",
    )
    parser.add_argument(
        "--with-proc-resolution-gate",
        action="store_true",
        help="Run proc-resolution ownership checks against loaded symbols.",
    )
    parser.add_argument(
        "--symbol-ownership",
        default="config/dropin-symbol-ownership.json",
        help="Symbol ownership contract path passed to proc-resolution checks.",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for output artifacts (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp report/output paths with a UTC timestamp suffix.",
    )
    return parser.parse_args()


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def run_step(label: str, command: list[str], report_path: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    elapsed = time.perf_counter() - started
    child_report = load_json_if_exists(report_path) if report_path is not None else None
    step: dict[str, Any] = {
        "label": label,
        "command": command,
        "returnCode": completed.returncode,
        "runtimeSeconds": round(elapsed, 6),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "pass": completed.returncode == 0,
    }
    if report_path is not None:
        step["reportPath"] = str(report_path)
        step["report"] = child_report
    return step


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    if args.micro_iterations <= 0:
        print("FAIL: --micro-iterations must be > 0")
        return 1
    if args.e2e_iterations <= 0:
        print("FAIL: --e2e-iterations must be > 0")
        return 1

    artifact_path = Path(args.artifact)
    symbols_path = Path(args.symbols)
    symbol_report = Path(args.symbol_report)
    behavior_report = Path(args.behavior_report)
    benchmark_report = Path(args.benchmark_report)
    benchmark_html = Path(args.benchmark_html)
    report_path = Path(args.report)
    ownership_path = Path(args.symbol_ownership)
    ownership_arg = str(ownership_path) if ownership_path.exists() else ""
    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )
    if args.timestamp_output:
        symbol_report = output_paths.with_timestamp(symbol_report, output_timestamp)
        behavior_report = output_paths.with_timestamp(behavior_report, output_timestamp)
        benchmark_report = output_paths.with_timestamp(benchmark_report, output_timestamp)
        benchmark_html = output_paths.with_timestamp(benchmark_html, output_timestamp)
        report_path = output_paths.with_timestamp(report_path, output_timestamp)

    bench_dir = Path(__file__).resolve().parent
    symbol_gate = bench_dir / "dropin_symbol_gate.py"
    behavior_suite = bench_dir / "dropin_behavior_suite.py"
    benchmark_suite = bench_dir / "dropin_benchmark_suite.py"
    benchmark_visualize = bench_dir / "visualize_dropin_benchmark.py"
    proc_resolution_tests = bench_dir / "dropin_proc_resolution_tests.py"
    child_time_args: list[str] = []
    if args.timestamp_output:
        child_time_args = ["--timestamp", output_timestamp]
    else:
        child_time_args = ["--no-timestamp-output"]

    steps: list[dict[str, Any]] = []

    symbol_command = [
        sys.executable,
        str(symbol_gate),
        "--artifact",
        str(artifact_path),
        "--symbols",
        str(symbols_path),
        "--ownership",
        ownership_arg,
        "--report",
        str(symbol_report),
    ]
    symbol_command.extend(child_time_args)
    steps.append(run_step("symbol_gate", symbol_command, symbol_report))

    behavior_command = [
        sys.executable,
        str(behavior_suite),
        "--artifact",
        str(artifact_path),
        "--report",
        str(behavior_report),
    ]
    behavior_command.extend(child_time_args)
    steps.append(run_step("behavior_suite", behavior_command, behavior_report))

    if args.with_proc_resolution_gate:
        if not ownership_path.exists():
            print(f"FAIL: missing --symbol-ownership: {ownership_path}")
            return 1
        proc_resolution_command = [
            sys.executable,
            str(proc_resolution_tests),
            "--artifact",
            str(artifact_path),
            "--ownership",
            str(ownership_path),
        ]
        steps.append(run_step("proc_resolution", proc_resolution_command))

    if not args.skip_benchmarks:
        benchmark_command = [
            sys.executable,
            str(benchmark_suite),
            "--artifact",
            str(artifact_path),
            "--micro-iterations",
            str(args.micro_iterations),
            "--e2e-iterations",
            str(args.e2e_iterations),
            "--report",
            str(benchmark_report),
        ]
        benchmark_command.extend(child_time_args)
        steps.append(run_step("benchmark_suite", benchmark_command, benchmark_report))

        visualize_command = [
            sys.executable,
            str(benchmark_visualize),
            "--report",
            str(benchmark_report),
            "--out",
            str(benchmark_html),
        ]
        steps.append(run_step("benchmark_visualization", visualize_command))

    overall_pass = all(bool(step.get("pass")) for step in steps)
    failing_steps = [step for step in steps if not step.get("pass")]

    consolidated_report: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "outputTimestamp": output_timestamp,
        "artifact": str(artifact_path),
        "symbols": str(symbols_path),
        "benchmarkHtml": str(benchmark_html),
        "pass": overall_pass,
        "steps": steps,
        "failedStepLabels": [str(step.get("label")) for step in failing_steps],
        "totalRuntimeSeconds": round(sum(float(step.get("runtimeSeconds", 0.0)) for step in steps), 6),
    }

    write_report(report_path, consolidated_report)
    output_paths.write_run_manifest_for_outputs(
        [report_path, symbol_report, behavior_report, benchmark_report, benchmark_html],
        {
            "runType": "dropin_gate",
            "config": {
                "artifact": str(artifact_path),
                "symbols": str(symbols_path),
                "microIterations": args.micro_iterations,
                "e2eIterations": args.e2e_iterations,
                "skipBenchmarks": bool(args.skip_benchmarks),
            },
            "fullRun": not args.skip_benchmarks,
            "claimGateRan": False,
            "dropinGateRan": True,
            "reportPath": str(report_path),
            "status": "passed" if overall_pass else "failed",
        },
    )

    if overall_pass:
        print("PASS: drop-in gate")
    else:
        print("FAIL: drop-in gate")
        print("runtime-to-fix (seconds):")
        for step in failing_steps:
            label = str(step.get("label"))
            runtime = float(step.get("runtimeSeconds", 0.0))
            print(f"  {label}: {runtime:.3f}s")
            child_report = step.get("report")
            if isinstance(child_report, dict):
                error = child_report.get("error")
                if isinstance(error, str) and error:
                    print(f"    error: {error}")
                failure = child_report.get("suiteResult")
                if isinstance(failure, dict):
                    failure_token = failure.get("failure")
                    if isinstance(failure_token, str) and failure_token:
                        print(f"    failure_token: {failure_token}")

    print(f"report: {report_path}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
