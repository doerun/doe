#!/usr/bin/env python3
"""Canonical entrypoint for schema/correctness/trace/drop-in/claim gates with optional parity verification."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
import output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-doe.json",
        help="Comparison report produced by compare_dawn_vs_doe.py",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for drop-in gate outputs (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp drop-in gate report paths with a UTC timestamp suffix.",
    )
    parser.add_argument(
        "--gates",
        default="config/gates.json",
        help="Gate policy config path passed to check_correctness.py",
    )
    parser.add_argument(
        "--quirk",
        default="examples/quirks/intel_gen12_temp_buffer.json",
        help="Reference quirk path passed to check_correctness.py",
    )
    parser.add_argument(
        "--with-comparability-parity-gate",
        action="store_true",
        help=(
            "Run comparability_obligation_parity_gate.py as a verification-lane gate "
            "before correctness/trace."
        ),
    )
    parser.add_argument(
        "--with-claim-gate",
        action="store_true",
        help="Run claim_gate.py after schema/correctness/trace gates.",
    )
    parser.add_argument(
        "--require-claim-gate",
        action="store_true",
        help=(
            "Fail unless --with-claim-gate is set. "
            "Use this when the run is intended as release-claim readiness evidence."
        ),
    )
    parser.add_argument(
        "--trace-semantic-parity-mode",
        choices=["off", "auto", "required"],
        default="auto",
        help="Semantic parity mode passed to trace_gate.py.",
    )
    parser.add_argument(
        "--with-dropin-gate",
        action="store_true",
        help="Run dropin_gate.py after schema/correctness/trace gates.",
    )
    parser.add_argument(
        "--dropin-artifact",
        default="zig/zig-out/lib/libdoe_webgpu.so",
        help="Shared library artifact path passed to dropin_gate.py when --with-dropin-gate is set.",
    )
    parser.add_argument(
        "--dropin-symbols",
        default="config/dropin_abi.symbols.txt",
        help="Required symbol list passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-report",
        default="bench/out/dropin_report.json",
        help="Top-level drop-in report path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-symbol-report",
        default="bench/out/dropin_symbol_report.json",
        help="Drop-in symbol report path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-behavior-report",
        default="bench/out/dropin_behavior_report.json",
        help="Drop-in behavior report path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-benchmark-report",
        default="bench/out/dropin_benchmark_report.json",
        help="Drop-in benchmark report path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-benchmark-html",
        default="bench/out/dropin_benchmark_report.html",
        help="Drop-in benchmark HTML path passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-micro-iterations",
        type=int,
        default=30,
        help="Micro benchmark iteration count passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-e2e-iterations",
        type=int,
        default=10,
        help="End-to-end benchmark iteration count passed to dropin_gate.py.",
    )
    parser.add_argument(
        "--dropin-skip-benchmarks",
        action="store_true",
        help="Pass --skip-benchmarks to dropin_gate.py.",
    )
    parser.add_argument(
        "--claim-require-comparison-status",
        default="comparable",
        help="Required top-level comparisonStatus when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-require-claim-status",
        default="claimable",
        help="Required top-level claimStatus when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-require-claimability-mode",
        default="release",
        help="Required claimabilityPolicy.mode when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-require-min-timed-samples",
        type=int,
        default=15,
        help="Required claimabilityPolicy.minTimedSamples lower bound when --with-claim-gate is set.",
    )
    parser.add_argument(
        "--claim-expected-workload-contract",
        default="",
        help=(
            "Optional workload contract path forwarded to claim_gate.py "
            "for workload hash/ID-set checks."
        ),
    )
    parser.add_argument(
        "--claim-require-workload-contract-hash",
        action="store_true",
        help="Forward --require-workload-contract-hash to claim_gate.py.",
    )
    parser.add_argument(
        "--claim-require-workload-id-set-match",
        action="store_true",
        help="Forward --require-workload-id-set-match to claim_gate.py.",
    )
    return parser.parse_args()


def run_gate(label: str, command: list[str]) -> None:
    print(f"[gate] {label}: {' '.join(command)}", flush=True)
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        print(f"FAIL: missing report: {report_path}")
        return 1

    if args.claim_require_min_timed_samples < 0:
        print(
            "FAIL: invalid --claim-require-min-timed-samples="
            f"{args.claim_require_min_timed_samples} expected >= 0"
        )
        return 1
    if args.require_claim_gate and not args.with_claim_gate:
        print("FAIL: --require-claim-gate requires --with-claim-gate")
        return 1
    if args.dropin_micro_iterations < 0:
        print(
            "FAIL: invalid --dropin-micro-iterations="
            f"{args.dropin_micro_iterations} expected >= 0"
        )
        return 1
    if args.dropin_e2e_iterations < 0:
        print(
            "FAIL: invalid --dropin-e2e-iterations="
            f"{args.dropin_e2e_iterations} expected >= 0"
        )
        return 1

    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )

    bench_dir = Path(__file__).resolve().parent
    schema_gate = bench_dir / "schema_gate.py"
    comparability_parity_gate = bench_dir / "comparability_obligation_parity_gate.py"
    correctness_gate = bench_dir / "check_correctness.py"
    trace_gate = bench_dir / "trace_gate.py"
    dropin_gate = bench_dir / "dropin_gate.py"
    claim_gate = bench_dir / "claim_gate.py"

    if not args.with_claim_gate:
        print(
            "INFO: claim gate not requested; this run validates blocking gates only "
            "(schema/correctness/trace[/drop-in]) and is not release-claim readiness evidence."
        )
    if not args.with_comparability_parity_gate:
        print(
            "INFO: comparability parity gate not requested; verification-lane Lean/Python "
            "fixture parity is not checked in this run."
        )

    try:
        run_gate("schema", [sys.executable, str(schema_gate)])
        if args.with_comparability_parity_gate:
            run_gate("comparability-parity", [sys.executable, str(comparability_parity_gate)])
        run_gate(
            "correctness",
            [
                sys.executable,
                str(correctness_gate),
                "--gates",
                args.gates,
                "--quirk",
                args.quirk,
                "--report",
                str(report_path),
            ],
        )
        run_gate(
            "trace",
            [
                sys.executable,
                str(trace_gate),
                "--report",
                str(report_path),
                "--semantic-parity-mode",
                args.trace_semantic_parity_mode,
            ],
        )

        if args.with_dropin_gate:
            if not args.dropin_artifact.strip():
                print("FAIL: --with-dropin-gate requires --dropin-artifact")
                return 1
            artifact_path = Path(args.dropin_artifact)
            if not artifact_path.exists():
                print(f"FAIL: missing --dropin-artifact: {artifact_path}")
                return 1
            dropin_report = output_paths.with_timestamp(
                args.dropin_report,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_symbol_report = output_paths.with_timestamp(
                args.dropin_symbol_report,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_behavior_report = output_paths.with_timestamp(
                args.dropin_behavior_report,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_benchmark_report = output_paths.with_timestamp(
                args.dropin_benchmark_report,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_benchmark_html = output_paths.with_timestamp(
                args.dropin_benchmark_html,
                output_timestamp,
                enabled=args.timestamp_output,
            )
            dropin_command = [
                sys.executable,
                str(dropin_gate),
                "--artifact",
                args.dropin_artifact,
                "--symbols",
                args.dropin_symbols,
                "--report",
                str(dropin_report),
                "--symbol-report",
                str(dropin_symbol_report),
                "--behavior-report",
                str(dropin_behavior_report),
                "--benchmark-report",
                str(dropin_benchmark_report),
                "--benchmark-html",
                str(dropin_benchmark_html),
                "--micro-iterations",
                str(args.dropin_micro_iterations),
                "--e2e-iterations",
                str(args.dropin_e2e_iterations),
            ]
            if args.timestamp_output:
                dropin_command.extend(["--timestamp", output_timestamp])
            else:
                dropin_command.append("--no-timestamp-output")
            if args.dropin_skip_benchmarks:
                dropin_command.append("--skip-benchmarks")
            run_gate("dropin", dropin_command)

        if args.with_claim_gate:
            claim_command = [
                sys.executable,
                str(claim_gate),
                "--report",
                str(report_path),
                "--require-comparison-status",
                args.claim_require_comparison_status,
                "--require-claim-status",
                args.claim_require_claim_status,
                "--require-claimability-mode",
                args.claim_require_claimability_mode,
                "--require-min-timed-samples",
                str(args.claim_require_min_timed_samples),
            ]
            if args.claim_expected_workload_contract.strip():
                claim_command.extend(
                    [
                        "--expected-workload-contract",
                        args.claim_expected_workload_contract,
                    ]
                )
            if args.claim_require_workload_contract_hash:
                claim_command.append("--require-workload-contract-hash")
            if args.claim_require_workload_id_set_match:
                claim_command.append("--require-workload-id-set-match")
            run_gate("claim", claim_command)
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: gate command failed with return code {exc.returncode}")
        return exc.returncode

    print("PASS: blocking gate sequence completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
