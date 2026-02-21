#!/usr/bin/env python3
"""
Release hard-gate for trace replay validity.

Validates every successful trace artifact in a dawn-vs-fawn comparison report
with the replay checker.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPLAY_SCRIPT = Path(__file__).resolve().parents[1] / "trace" / "replay.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="fawn/bench/out/dawn-vs-fawn.json",
        help="Comparison report produced by compare_dawn_vs_fawn.py",
    )
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fail(message: str) -> None:
    print(f"FAIL: {message}")


def run_replay_check(meta_path: Path, trace_jsonl: Path) -> tuple[bool, str]:
    cmd = [sys.executable, str(REPLAY_SCRIPT), "--trace-meta", str(meta_path), "--trace-jsonl", str(trace_jsonl)]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode == 0:
        return True, result.stdout.strip()
    return (
        False,
        (result.stdout or result.stderr).strip(),
    )


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        fail(f"missing report: {report_path}")
        return 1

    try:
        report = load_json(args.report)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        fail(f"invalid report: {exc}")
        return 1

    if not isinstance(report, dict):
        fail(f"invalid report format: {args.report}")
        return 1

    workloads = report.get("workloads")
    if not isinstance(workloads, list):
        fail("invalid report format: missing workloads list")
        return 1

    failures: list[str] = []
    checks = 0
    for workload_idx, workload in enumerate(workloads):
        if not isinstance(workload, dict):
            failures.append(f"workloads[{workload_idx}] is not an object")
            continue
        workload_id = workload.get("id", "unknown")
        for side in ("left", "right"):
            side_payload = workload.get(side, {})
            if not isinstance(side_payload, dict):
                continue
            for sample_idx, sample in enumerate(side_payload.get("commandSamples", [])):
                if not isinstance(sample, dict):
                    continue
                return_code = sample.get("returnCode")
                if not isinstance(return_code, int):
                    failures.append(
                        f"{workload_id}/{side} sample {sample_idx} missing or invalid returnCode (expected int)"
                    )
                    continue
                if return_code != 0:
                    continue

                trace_meta = sample.get("traceMetaPath")
                trace_jsonl = sample.get("traceJsonlPath")
                if not trace_meta or not trace_jsonl:
                    msg = (
                        f"{workload_id}/{side} sample {sample_idx} missing trace artifact paths "
                        "(expected traceMetaPath and traceJsonlPath)"
                    )
                    failures.append(msg)
                    continue

                meta_path = Path(trace_meta)
                jsonl_path = Path(trace_jsonl)
                if not meta_path.exists() or not jsonl_path.exists():
                    failures.append(
                        f"{workload_id}/{side} sample {sample_idx} missing trace files: "
                        f"meta={meta_path} jsonl={jsonl_path}"
                    )
                    continue

                checks += 1
                ok, output = run_replay_check(meta_path, jsonl_path)
                if not ok:
                    failures.append(
                        f"{workload_id}/{side} sample {sample_idx} trace replay check failed:\n{output}"
                    )

    if failures:
        fail("trace gate failed")
        for item in failures:
            print(item)
        return 1

    if not checks:
        fail("no successful trace samples found")
        return 1

    print(f"PASS: replay-validated {checks} trace samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
