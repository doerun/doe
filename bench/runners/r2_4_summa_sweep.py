#!/usr/bin/env python3
"""R2-4 SUMMA d2h-hang sweep runner.

Builds and runs the canonical csl-extras gemm-collectives_2d example across a
2-axis sweep (PE-count P, per-PE tile dimension Mt=Kt=Nt). The goal is to
isolate which axis triggers the simfabric memcpy_d2h hang observed at Doe's
exact geometry (P=54, Mt=22 -> 5.6 MB d2h). Canonical sources are used so the
SDK is the only variable.

Per-cell receipt schema:
  { cell, P, Mt, fabric_dims, fabric_offsets, total_c_bytes, per_pe_c_bytes,
    build_ms, run_ms, build_exit, run_exit, classification, stderr_tail }

classification:
  - success            : run.py printed SUCCESS (np.allclose passed)
  - run_timeout        : cs_python exceeded --run-timeout
  - run_failed         : non-zero exit, not a timeout
  - build_failed       : cslc compile error
  - skipped            : cell explicitly skipped
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = Path(
    "/tmp/csl-extras-extract/csl-extras-202604101435-6-d2f7d96e/"
    "examples/benchmarks/gemm-collectives_2d"
)
DEFAULT_OUT = REPO_ROOT / "bench" / "out" / "r2-4-summa-sweep"
DEFAULT_CSLC = "/home/x/cerebras-sdk-2.10.0/cslc"
DEFAULT_CS_PYTHON = "/home/x/cerebras-sdk-2.10.0/cs_python"

WEST_RESERVED = 4
EAST_RESERVED = 3
NORTH_RESERVED = 1
SOUTH_RESERVED = 1


@dataclass(frozen=True)
class Cell:
    name: str
    P: int
    Mt: int

    @property
    def total_c_bytes(self) -> int:
        return (self.P * self.Mt) ** 2 * 4

    @property
    def per_pe_c_bytes(self) -> int:
        return self.Mt * self.Mt * 4

    def fabric_dims(self) -> tuple[int, int]:
        return (self.P + WEST_RESERVED + EAST_RESERVED,
                self.P + NORTH_RESERVED + SOUTH_RESERVED)


CELLS: tuple[Cell, ...] = (
    Cell("baseline",   P=4,  Mt=14),
    Cell("tile-up",    P=4,  Mt=22),
    Cell("count-up-1", P=8,  Mt=14),
    Cell("count-up-2", P=16, Mt=14),
    Cell("count-up-3", P=32, Mt=14),
    Cell("doe-exact",  P=54, Mt=22),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(DEFAULT_SRC),
                        help="Canonical gemm-collectives_2d source dir")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="Sweep output root")
    parser.add_argument("--cslc", default=DEFAULT_CSLC)
    parser.add_argument("--cs-python", default=DEFAULT_CS_PYTHON)
    parser.add_argument("--cell", action="append", default=None,
                        help="Run only the named cell (repeatable). "
                             "Defaults to all cells in order.")
    parser.add_argument("--build-timeout", type=int, default=300,
                        help="Per-cell cslc timeout (seconds)")
    parser.add_argument("--run-timeout", type=int, default=300,
                        help="Per-cell cs_python timeout (seconds). "
                             "Canonical baseline runs in <30s; 5min is "
                             "plenty to detect a d2h hang.")
    return parser.parse_args()


def _run(cmd: list[str], *, cwd: Path, timeout: int,
         stdout_path: Path, stderr_path: Path) -> tuple[int | None, float, bool]:
    started = time.monotonic()
    timed_out = False
    with stdout_path.open("w", encoding="utf-8") as so, \
         stderr_path.open("w", encoding="utf-8") as se:
        try:
            proc = subprocess.run(
                cmd, cwd=str(cwd), stdout=so, stderr=se,
                timeout=timeout, check=False,
            )
            exit_code: int | None = proc.returncode
        except subprocess.TimeoutExpired:
            exit_code = None
            timed_out = True
    elapsed_ms = (time.monotonic() - started) * 1000.0
    return exit_code, elapsed_ms, timed_out


def _classify(*, build_exit: int | None, run_exit: int | None,
              run_timed_out: bool, stdout_path: Path) -> str:
    if build_exit is None or build_exit != 0:
        return "build_failed"
    if run_timed_out:
        return "run_timeout"
    if run_exit != 0:
        return "run_failed"
    text = stdout_path.read_text(encoding="utf-8", errors="replace")
    return "success" if "SUCCESS" in text else "run_failed"


def _stderr_tail(path: Path, limit: int = 4000) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        return text
    return "...[truncated]...\n" + text[-limit:]


def run_cell(cell: Cell, args: argparse.Namespace) -> dict:
    src_dir = Path(args.src).resolve()
    cell_dir = (Path(args.out) / cell.name).resolve()
    cell_dir.mkdir(parents=True, exist_ok=True)
    for src_name in ("pe.csl", "layout.csl", "run.py"):
        src = src_dir / src_name
        if not src.is_file():
            raise FileNotFoundError(f"missing canonical source: {src}")
        shutil.copy2(src, cell_dir / src_name)

    fab_w, fab_h = cell.fabric_dims()
    params = f"P:{cell.P},Mt:{cell.Mt},Kt:{cell.Mt},Nt:{cell.Mt}"

    build_cmd = [
        args.cslc,
        "--arch=wse3",
        "./layout.csl",
        f"--fabric-dims={fab_w},{fab_h}",
        "--fabric-offsets=4,1",
        f"--params={params}",
        "--memcpy",
        "--channels=1",
        "-o", "out",
    ]
    build_stdout = cell_dir / "cslc.stdout.log"
    build_stderr = cell_dir / "cslc.stderr.log"
    build_exit, build_ms, _ = _run(
        build_cmd, cwd=cell_dir, timeout=args.build_timeout,
        stdout_path=build_stdout, stderr_path=build_stderr,
    )

    run_exit: int | None = None
    run_ms = 0.0
    run_timed_out = False
    run_stdout = cell_dir / "run.stdout.log"
    run_stderr = cell_dir / "run.stderr.log"
    if build_exit == 0:
        run_cmd = [args.cs_python, "run.py", "--name", "out"]
        run_exit, run_ms, run_timed_out = _run(
            run_cmd, cwd=cell_dir, timeout=args.run_timeout,
            stdout_path=run_stdout, stderr_path=run_stderr,
        )

    classification = _classify(
        build_exit=build_exit, run_exit=run_exit,
        run_timed_out=run_timed_out, stdout_path=run_stdout,
    )

    receipt = {
        "cell": cell.name,
        "P": cell.P,
        "Mt": cell.Mt,
        "fabric_dims": [fab_w, fab_h],
        "fabric_offsets": [4, 1],
        "total_c_bytes": cell.total_c_bytes,
        "per_pe_c_bytes": cell.per_pe_c_bytes,
        "build_ms": round(build_ms, 1),
        "run_ms": round(run_ms, 1),
        "build_exit": build_exit,
        "run_exit": run_exit,
        "run_timed_out": run_timed_out,
        "classification": classification,
        "stderr_tail": (
            _stderr_tail(run_stderr) if build_exit == 0
            else _stderr_tail(build_stderr)
        ),
    }
    (cell_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8",
    )
    return receipt


def main() -> int:
    args = parse_args()
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    targets: list[Cell] = []
    if args.cell:
        wanted = set(args.cell)
        unknown = wanted - {c.name for c in CELLS}
        if unknown:
            raise SystemExit(f"unknown cell name(s): {sorted(unknown)}")
        targets = [c for c in CELLS if c.name in wanted]
    else:
        targets = list(CELLS)

    receipts: list[dict] = []
    for cell in targets:
        print(f"[r2-4] cell={cell.name} P={cell.P} Mt={cell.Mt} "
              f"total_C={cell.total_c_bytes} bytes", flush=True)
        receipt = run_cell(cell, args)
        receipts.append(receipt)
        print(
            f"[r2-4] {cell.name}: classification={receipt['classification']} "
            f"build_ms={receipt['build_ms']} run_ms={receipt['run_ms']} "
            f"build_exit={receipt['build_exit']} run_exit={receipt['run_exit']}",
            flush=True,
        )

    summary = {
        "src": str(Path(args.src).resolve()),
        "out": str(out_root.resolve()),
        "cslc": args.cslc,
        "cs_python": args.cs_python,
        "build_timeout_s": args.build_timeout,
        "run_timeout_s": args.run_timeout,
        "cells": receipts,
    }
    (out_root / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
