#!/usr/bin/env python3
"""Canonical release/smoke pipeline runner for benchmark + gates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="bench/compare_dawn_vs_fawn.config.amd.vulkan.release.json",
        help="compare_dawn_vs_fawn.py config path for this pipeline run.",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Override report path. Defaults to run.out from --config.",
    )
    parser.add_argument(
        "--strict-amd-vulkan",
        action="store_true",
        help="Run strict AMD Vulkan host preflight before benchmark execution.",
    )
    parser.add_argument(
        "--verify-smoke-report",
        default="",
        help="Optional smoke report path to validate with verify_smoke_gpu_usage.py.",
    )
    parser.add_argument(
        "--verify-smoke-require-comparable",
        action="store_true",
        help="Pass --require-comparable to verify_smoke_gpu_usage.py.",
    )
    parser.add_argument(
        "--with-claim-gate",
        action="store_true",
        help="Run claim gate in addition to schema/correctness/trace gates.",
    )
    parser.add_argument(
        "--claim-require-comparison-status",
        default="comparable",
        help="Required comparisonStatus for claim gate.",
    )
    parser.add_argument(
        "--claim-require-claim-status",
        default="claimable",
        help="Required claimStatus for claim gate.",
    )
    parser.add_argument(
        "--claim-require-claimability-mode",
        default="release",
        help="Required claimability mode for claim gate.",
    )
    parser.add_argument(
        "--claim-require-min-timed-samples",
        type=int,
        default=15,
        help="Minimum timed sample floor for claim gate.",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip host preflight step.",
    )
    parser.add_argument(
        "--skip-compare",
        action="store_true",
        help="Skip compare_dawn_vs_fawn.py execution.",
    )
    parser.add_argument(
        "--skip-gates",
        action="store_true",
        help="Skip run_blocking_gates.py execution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def resolve_report_path(config_path: Path, explicit_report: str) -> Path:
    if explicit_report:
        return Path(explicit_report)

    config_payload = load_json(config_path)
    run_payload = config_payload.get("run")
    if not isinstance(run_payload, dict):
        raise ValueError(f"invalid config {config_path}: missing object field run")
    out_value = run_payload.get("out")
    if not isinstance(out_value, str) or not out_value.strip():
        raise ValueError(f"invalid config {config_path}: missing non-empty run.out")
    return Path(out_value)


def run_step(label: str, command: list[str], *, dry_run: bool) -> None:
    print(f"[pipeline] {label}: {' '.join(command)}", flush=True)
    if dry_run:
        return
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()

    if args.claim_require_min_timed_samples < 0:
        print(
            "FAIL: invalid --claim-require-min-timed-samples="
            f"{args.claim_require_min_timed_samples} expected >= 0"
        )
        return 1

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"FAIL: missing config: {config_path}")
        return 1

    report_path = resolve_report_path(config_path, args.report)

    bench_dir = Path(__file__).resolve().parent
    python_exe = sys.executable
    preflight = bench_dir / "preflight_bench_host.py"
    compare = bench_dir / "compare_dawn_vs_fawn.py"
    smoke_verify = bench_dir / "verify_smoke_gpu_usage.py"
    gates = bench_dir / "run_blocking_gates.py"

    try:
        if args.strict_amd_vulkan and not args.skip_preflight:
            run_step(
                "preflight",
                [python_exe, str(preflight), "--strict-amd-vulkan"],
                dry_run=args.dry_run,
            )

        if not args.skip_compare:
            run_step(
                "compare",
                [python_exe, str(compare), "--config", str(config_path)],
                dry_run=args.dry_run,
            )

        if args.verify_smoke_report:
            verify_cmd = [
                python_exe,
                str(smoke_verify),
                "--report",
                args.verify_smoke_report,
            ]
            if args.verify_smoke_require_comparable:
                verify_cmd.append("--require-comparable")
            run_step("verify-smoke", verify_cmd, dry_run=args.dry_run)

        if not args.skip_gates:
            gates_cmd = [python_exe, str(gates), "--report", str(report_path)]
            if args.with_claim_gate:
                gates_cmd.extend(
                    [
                        "--with-claim-gate",
                        "--claim-require-comparison-status",
                        args.claim_require_comparison_status,
                        "--claim-require-claim-status",
                        args.claim_require_claim_status,
                        "--claim-require-claimability-mode",
                        args.claim_require_claimability_mode,
                        "--claim-require-min-timed-samples",
                        str(args.claim_require_min_timed_samples),
                    ]
                )
            run_step("gates", gates_cmd, dry_run=args.dry_run)
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: pipeline step failed with return code {exc.returncode}")
        return exc.returncode

    print("PASS: release pipeline completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
