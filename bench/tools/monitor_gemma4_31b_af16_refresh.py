#!/usr/bin/env python3
"""Monitor the Gemma 4 31B af16 manifest-shape refresh run."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_OUT_ROOT = (
    REPO_ROOT / "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel"
)
DEFAULT_RUNNER_PATTERN = "gemma4_31b_af16_hostplan_streaming_runner.py"
DEFAULT_PROBE_PATTERN = "manifest_kernel_probe_runner.py"
DEFAULT_ADAPTER_PATTERN = "chain_step_adapter.py"

DTYPE_BYTES = {
    "f16": 2,
    "bf16": 2,
    "f32": 4,
    "i32": 4,
    "u32": 4,
    "u8": 1,
    "i8": 1,
}


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    stat: str
    etimes: int
    etime: str
    pcpu: str
    pmem: str
    cmd: str


@dataclass(frozen=True)
class IoSpec:
    symbol: str
    path: Path
    dtype: str
    per_pe_chunk: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def ps_rows() -> list[Proc]:
    proc = subprocess.run(
        [
            "ps",
            "-eo",
            "pid=,ppid=,stat=,etimes=,etime=,pcpu=,pmem=,cmd=",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    rows: list[Proc] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 7)
        if len(parts) != 8:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            etimes = int(parts[3])
        except ValueError:
            continue
        rows.append(
            Proc(
                pid=pid,
                ppid=ppid,
                stat=parts[2],
                etimes=etimes,
                etime=parts[4],
                pcpu=parts[5],
                pmem=parts[6],
                cmd=parts[7],
            )
        )
    return rows


def find_proc(rows: list[Proc], pattern: str) -> Proc | None:
    matches = [row for row in rows if pattern in row.cmd]
    return matches[-1] if matches else None


def command_tokens(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def arg_value(tokens: list[str], name: str) -> str | None:
    for index, token in enumerate(tokens):
        if token == name and index + 1 < len(tokens):
            return tokens[index + 1]
    return None


def repeated_arg_values(tokens: list[str], name: str) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(tokens):
        if token == name and index + 1 < len(tokens):
            values.append(tokens[index + 1])
    return values


def kernel_from_adapter(adapter: Proc | None) -> str:
    if adapter is None:
        return "none"
    compile_dir = arg_value(command_tokens(adapter.cmd), "--compile-dir")
    if not compile_dir:
        return "unknown"
    return Path(compile_dir).name


def int_arg(tokens: list[str], name: str) -> int | None:
    raw = arg_value(tokens, name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def parse_io_spec(raw: str) -> IoSpec | None:
    parts = raw.split(":")
    if len(parts) != 4:
        return None
    try:
        chunk = int(parts[3])
    except ValueError:
        return None
    return IoSpec(
        symbol=parts[0],
        path=resolve(Path(parts[1])),
        dtype=parts[2].lower(),
        per_pe_chunk=chunk,
    )


def live_io(adapter: Proc | None) -> dict[str, Any]:
    if adapter is None:
        return {
            "inputBytes": 0,
            "outputBytes": 0,
            "expectedOutputBytes": 0,
            "outputFiles": 0,
        }
    tokens = command_tokens(adapter.cmd)
    width = int_arg(tokens, "--width") or 0
    height = int_arg(tokens, "--height") or 0
    inputs = [
        spec for raw in repeated_arg_values(tokens, "--input")
        if (spec := parse_io_spec(raw)) is not None
    ]
    outputs = [
        spec for raw in repeated_arg_values(tokens, "--output")
        if (spec := parse_io_spec(raw)) is not None
    ]
    input_bytes = sum(
        spec.path.stat().st_size for spec in inputs if spec.path.is_file()
    )
    output_files = sum(1 for spec in outputs if spec.path.is_file())
    output_bytes = sum(
        spec.path.stat().st_size for spec in outputs if spec.path.is_file()
    )
    expected = sum(
        width * height * spec.per_pe_chunk * DTYPE_BYTES.get(spec.dtype, 0)
        for spec in outputs
    )
    return {
        "inputBytes": input_bytes,
        "outputBytes": output_bytes,
        "expectedOutputBytes": expected,
        "outputFiles": output_files,
    }


def load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def receipt_state(out_root: Path, kernel: str) -> dict[str, Any]:
    if kernel in {"none", "unknown"}:
        return {}
    receipt = load_json(out_root / f"{kernel}.json")
    if not isinstance(receipt, dict):
        return {}
    return {
        "verdict": receipt.get("verdict"),
        "blocker": receipt.get("blocker"),
        "dispatchExitCode": receipt.get("dispatchExitCode"),
        "dispatchTimedOut": receipt.get("dispatchTimedOut"),
        "dispatchWallclockNs": receipt.get("dispatchWallclockNs"),
    }


def summary_state(out_root: Path) -> dict[str, Any]:
    summary_path = out_root / "summary.json"
    summary = load_json(summary_path)
    if not isinstance(summary, dict):
        return {
            "mtime": "missing",
            "totals": {},
            "blockers": {},
        }
    blockers: dict[str, int] = {}
    for kernel in summary.get("kernels") or []:
        if not isinstance(kernel, dict):
            continue
        blocker = str(kernel.get("blocker") or "unknown")
        blockers[blocker] = blockers.get(blocker, 0) + 1
    mtime = "missing"
    if summary_path.is_file():
        mtime = time.strftime(
            "%H:%M:%S",
            time.localtime(summary_path.stat().st_mtime),
        )
    return {
        "mtime": mtime,
        "totals": summary.get("totals") or {},
        "blockers": blockers,
    }


def refreshed_count(out_root: Path, runner: Proc | None) -> int:
    if runner is None:
        return 0
    run_start = time.time() - runner.etimes
    count = 0
    for path in out_root.glob("*.json"):
        if path.name == "summary.json":
            continue
        if path.stat().st_mtime >= run_start:
            count += 1
    return count


def total_count(out_root: Path, summary: dict[str, Any]) -> int:
    totals = summary.get("totals") or {}
    raw = totals.get("kernelCount")
    if isinstance(raw, int) and raw > 0:
        return raw
    return len([p for p in out_root.glob("*.json") if p.name != "summary.json"])


def format_blockers(blockers: dict[str, int]) -> str:
    if not blockers:
        return "{}"
    return "{" + ",".join(
        f"{key}:{blockers[key]}" for key in sorted(blockers)
    ) + "}"


def print_status(out_root: Path) -> None:
    rows = ps_rows()
    runner = find_proc(rows, DEFAULT_RUNNER_PATTERN)
    probe = find_proc(rows, DEFAULT_PROBE_PATTERN)
    adapter = find_proc(rows, DEFAULT_ADAPTER_PATTERN)
    kernel = kernel_from_adapter(adapter)
    io = live_io(adapter)
    receipt = receipt_state(out_root, kernel)
    summary = summary_state(out_root)
    total = total_count(out_root, summary)
    refreshed = refreshed_count(out_root, runner)
    expected = int(io["expectedOutputBytes"] or 0)
    actual = int(io["outputBytes"] or 0)
    out_pct = "na"
    if expected > 0:
        out_pct = str(min(100, actual * 100 // expected))
    totals = summary.get("totals") or {}
    line = (
        f"{time.strftime('%H:%M:%S')} "
        f"runner={'alive' if runner else 'none'} "
        f"probe={'alive' if probe else 'none'} "
        f"pid={adapter.pid if adapter else 'none'} "
        f"stat={adapter.stat if adapter else 'none'} "
        f"kernel={kernel} "
        f"kernelRun={adapter.etime if adapter else 'none'} "
        f"cpu={adapter.pcpu if adapter else '0'} "
        f"mem={adapter.pmem if adapter else '0'} "
        f"refreshed={refreshed}/{total} "
        f"inputBytes={io['inputBytes']} "
        f"outFiles={io['outputFiles']} "
        f"outBytes={actual}/{expected} "
        f"outPct={out_pct} "
        f"receipt={receipt.get('verdict', '?')}/"
        f"{receipt.get('blocker', '?')} "
        f"exit={receipt.get('dispatchExitCode', 'null')} "
        f"timedOut={receipt.get('dispatchTimedOut', 'null')} "
        f"summaryMtime={summary['mtime']} "
        f"summaryBound={totals.get('boundCount', 0)} "
        f"summaryBlocked={totals.get('blockedCount', 0)} "
        f"summaryBlockers={format_blockers(summary['blockers'])}"
    )
    print(line, flush=True)


def main() -> int:
    args = parse_args()
    out_root = resolve(args.out_root)
    if args.once:
        print_status(out_root)
        return 0
    while True:
        print_status(out_root)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
