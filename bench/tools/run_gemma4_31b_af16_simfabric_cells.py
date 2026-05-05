#!/usr/bin/env python3
"""Compile and run Gemma 4 31B AF16 simfabric cells."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SDK_ROOT = Path("/home/x/cerebras-sdk-2.10.0")
DEFAULT_CELLS_ROOT = (
    REPO_ROOT / "bench/runners/csl-runners/gemma-4-31b-af16-cells"
)
DEFAULT_OUT_ROOT = REPO_ROOT / "bench/out"
DEFAULT_SUMMARY_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-gemma-af16-simfabric-cells/summary-receipt.json"
)

CELLS: tuple[dict[str, Any], ...] = (
    {
        "kernel": "lm_head_prefill_stable",
        "layout": "lm_head_prefill_stable_layout.csl",
        "pe_program": "lm_head_prefill_stable_pe_program.csl",
        "runner": "lm_head_prefill_stable_run.py",
        "out_dir": "r3-1-31b-gemma-af16-lm-head-prefill-stable-simfabric-cell",
        "compile_params": (
            "width:4,height:1,out_dim:4,out_dim_per_pe:4,in_dim_per_pe:32"
        ),
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--cells-root", type=Path, default=DEFAULT_CELLS_ROOT)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--cmaddr", default="")
    return parser.parse_args()


def _run(argv: list[str], cwd: Path) -> None:
    proc = subprocess.run(argv, cwd=cwd, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed with code {proc.returncode}: {' '.join(argv)}"
        )


def _copy_cell_sources(cell: dict[str, Any], cells_root: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    copies = (
        (str(cell["layout"]), "layout.csl"),
        (str(cell["pe_program"]), "pe_program.csl"),
        (str(cell["runner"]), "run.py"),
    )
    for source_name, target_name in copies:
        source = cells_root / source_name
        if not source.is_file():
            raise FileNotFoundError(f"cell source not found: {source}")
        shutil.copy2(source, out_dir / target_name)


def _run_cell(
    *,
    cell: dict[str, Any],
    sdk_root: Path,
    cells_root: Path,
    out_root: Path,
    cmaddr: str,
) -> None:
    cslc = sdk_root / "cslc"
    cs_python = sdk_root / "cs_python"
    if not cslc.is_file():
        raise FileNotFoundError(f"cslc not found: {cslc}")
    if not cs_python.is_file():
        raise FileNotFoundError(f"cs_python not found: {cs_python}")

    out_dir = out_root / str(cell["out_dir"])
    _copy_cell_sources(cell, cells_root, out_dir)
    _run(
        [
            str(cslc),
            "layout.csl",
            "--arch=wse3",
            "--fabric-dims=11,5",
            "--fabric-offsets=4,1",
            f"--params={cell['compile_params']}",
            "--memcpy",
            "--channels=1",
            "-o",
            "compiled",
        ],
        cwd=out_dir,
    )
    run_argv = [
        str(cs_python),
        "run.py",
        "--name",
        "compiled",
        "--out-receipt",
        "receipt.json",
    ]
    if cmaddr:
        run_argv.extend(["--cmaddr", cmaddr])
    _run(run_argv, cwd=out_dir)


def main() -> int:
    args = parse_args()
    try:
        for cell in CELLS:
            _run_cell(
                cell=cell,
                sdk_root=args.sdk_root,
                cells_root=args.cells_root,
                out_root=args.out_root,
                cmaddr=args.cmaddr.strip(),
            )
        _run(
            [
                sys.executable,
                "bench/tools/"
                "synthesize_gemma4_31b_af16_simfabric_cells_summary_receipt.py",
                "--cells-root",
                str(args.cells_root),
                "--receipts-root",
                str(args.out_root),
                "--out",
                str(args.summary_out),
            ],
            cwd=REPO_ROOT,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        sys.stderr.write(f"run_gemma4_31b_af16_simfabric_cells: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
