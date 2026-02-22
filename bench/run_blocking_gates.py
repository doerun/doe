#!/usr/bin/env python3
"""Canonical entrypoint for blocking schema/correctness/trace/claim gates."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-fawn.json",
        help="Comparison report produced by compare_dawn_vs_fawn.py",
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
        "--with-claim-gate",
        action="store_true",
        help="Run claim_gate.py after schema/correctness/trace gates.",
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

    bench_dir = Path(__file__).resolve().parent
    schema_gate = bench_dir / "schema_gate.py"
    correctness_gate = bench_dir / "check_correctness.py"
    trace_gate = bench_dir / "trace_gate.py"
    claim_gate = bench_dir / "claim_gate.py"

    try:
        run_gate("schema", [sys.executable, str(schema_gate)])
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
        run_gate("trace", [sys.executable, str(trace_gate), "--report", str(report_path)])

        if args.with_claim_gate:
            run_gate(
                "claim",
                [
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
                ],
            )
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: gate command failed with return code {exc.returncode}")
        return exc.returncode

    print("PASS: blocking gate sequence completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
