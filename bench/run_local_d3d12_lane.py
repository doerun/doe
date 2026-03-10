#!/usr/bin/env python3
"""Run the governed local Windows D3D12 handoff sequence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO_ROOT / "bench"
PREFLIGHT = BENCH_DIR / "preflight_d3d12_host.py"
COMPARE = BENCH_DIR / "compare_dawn_vs_doe.py"
BLOCKING_GATES = BENCH_DIR / "run_blocking_gates.py"
CUBE = BENCH_DIR / "build_benchmark_cube.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--smoke-config",
        default="bench/compare_dawn_vs_doe.config.local.d3d12.smoke.json",
        help="Smoke compare config path.",
    )
    parser.add_argument(
        "--extended-config",
        default="bench/compare_dawn_vs_doe.config.local.d3d12.extended.comparable.json",
        help="Extended comparable config path.",
    )
    parser.add_argument(
        "--trace-semantic-parity-mode",
        choices=["off", "auto", "required"],
        default="auto",
        help="Forwarded to run_blocking_gates.py for the extended comparable report.",
    )
    parser.add_argument(
        "--skip-cube",
        action="store_true",
        help="Skip benchmark cube rebuild after the extended comparable lane passes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned commands without executing them.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def config_report_path(config_path: Path) -> Path:
    payload = load_json(config_path)
    run_payload = payload.get("run")
    if not isinstance(run_payload, dict):
        raise ValueError(f"invalid compare config: {config_path}")
    out_path = run_payload.get("out")
    if not isinstance(out_path, str) or not out_path:
        raise ValueError(f"missing run.out in compare config: {config_path}")
    return REPO_ROOT / out_path


def run_step(name: str, command: list[str], *, dry_run: bool) -> None:
    printable = " ".join(command)
    print(f"[{name}] {printable}")
    if dry_run:
        return
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def main() -> int:
    args = parse_args()
    smoke_config = REPO_ROOT / args.smoke_config
    extended_config = REPO_ROOT / args.extended_config
    extended_report = config_report_path(extended_config)

    steps: list[tuple[str, list[str]]] = [
        ("preflight", [sys.executable, str(PREFLIGHT), "--json"]),
        ("smoke", [sys.executable, str(COMPARE), "--config", str(smoke_config)]),
        ("extended", [sys.executable, str(COMPARE), "--config", str(extended_config)]),
        (
            "blocking-gates",
            [
                sys.executable,
                str(BLOCKING_GATES),
                "--report",
                str(extended_report),
                "--trace-semantic-parity-mode",
                args.trace_semantic_parity_mode,
            ],
        ),
    ]
    if not args.skip_cube:
        steps.append(("cube", [sys.executable, str(CUBE)]))

    for name, command in steps:
        run_step(name, command, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
