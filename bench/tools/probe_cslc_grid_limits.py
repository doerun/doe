#!/usr/bin/env python3
"""Probe the grid sizes cslc accepts for a 1D elementwise kernel.

The per-kernel toy fixtures compile at 4 PE — well under any cslc limit.
The E2B host-plan peGrid is 149x117 (17,433 PE) and 31B's is 246x236
(58,056 PE). Real-hardware execution needs cslc to accept those sizes.
This probe binary-searches a few likely grid widths on the smallest
kernel (elementwise-double) to produce a compile-receipt artifact for
each tested size. The point isn't to fully compile E2B — that needs
per-layer shape resolution — but to surface whether cslc itself has a
grid-size ceiling that would block the full-grid step regardless of
emitter progress.

Output: bench/out/cslc-grid-probe/grid-probe-report.json listing
{ width, peCount, fabricDims, compileStatus, elapsedSec, stderr_tail }
per test, and a summary.maxProvenWidth + summary.wseArchMaxFabric.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_WIDTHS = [4, 16, 64, 256, 1024, 4096, 17433]
DEFAULT_CSLC = "/home/x/cerebras-sdk/cslc"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--cslc", default=DEFAULT_CSLC)
    p.add_argument(
        "--layout",
        default="runtime/zig/examples/simulator/elementwise-double-runtime/compile/elementwise-double/layout.csl",
    )
    p.add_argument("--widths", default=",".join(str(w) for w in DEFAULT_WIDTHS))
    p.add_argument(
        "--arch",
        default="wse3",
        choices=["wse2", "wse3"],
    )
    p.add_argument(
        "--out-json",
        default="bench/out/cslc-grid-probe/grid-probe-report.json",
    )
    p.add_argument("--per-run-timeout-sec", type=int, default=180)
    return p.parse_args()


def resolve(p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else (REPO_ROOT / pp).resolve()


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p.resolve())


def compute_fabric(width: int, height: int = 1) -> tuple[int, int, int, int]:
    """Return (fabric_w, fabric_h, offset_x, offset_y).

    The memcpy driver needs a fabric with a 4-column west margin + 4-column
    east slack for memcpy colors, and 1-row north slack. This mirrors the
    driver's default derivation in runtime/zig/tools/csl_sdk_driver.py.
    """
    fabric_w = width + 4 + 3
    fabric_h = height + 1 + 1
    offset_x = 4
    offset_y = 1
    return fabric_w, fabric_h, offset_x, offset_y


def run_cslc(
    *,
    cslc: str,
    layout: Path,
    width: int,
    arch: str,
    out_dir: Path,
    timeout_sec: int,
) -> dict:
    fabric_w, fabric_h, off_x, off_y = compute_fabric(width, 1)
    cmd = [
        cslc,
        str(layout),
        f"--arch={arch}",
        f"--fabric-dims={fabric_w},{fabric_h}",
        f"--fabric-offsets={off_x},{off_y}",
        "--channels=1",
        f"--params=width:{width},height:1",
        "-o", str(out_dir),
        "--memcpy",
    ]
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        return {
            "width": width,
            "peCount": width,
            "fabricDims": [fabric_w, fabric_h],
            "status": "timeout",
            "elapsedSec": float(timeout_sec),
            "stderrTail": (exc.stderr or b"")[-800:].decode("utf-8", errors="replace") if exc.stderr else "",
        }
    elapsed = time.time() - start
    status = "succeeded" if proc.returncode == 0 else "failed"
    stderr_tail = proc.stderr[-800:] if proc.stderr else ""
    return {
        "width": width,
        "peCount": width,
        "fabricDims": [fabric_w, fabric_h],
        "status": status,
        "returnCode": proc.returncode,
        "elapsedSec": round(elapsed, 2),
        "stderrTail": stderr_tail,
    }


def main() -> int:
    args = parse_args()
    if not shutil.which(args.cslc) and not Path(args.cslc).exists():
        print(f"FAIL: cslc not found at {args.cslc}")
        return 1

    layout = resolve(args.layout)
    widths = [int(w) for w in args.widths.split(",") if w.strip()]
    out_dir_root = resolve(args.out_json).parent / "compile-outputs"
    out_dir_root.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for w in widths:
        out_dir = out_dir_root / f"w{w:05d}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        result = run_cslc(
            cslc=args.cslc,
            layout=layout,
            width=w,
            arch=args.arch,
            out_dir=out_dir,
            timeout_sec=args.per_run_timeout_sec,
        )
        results.append(result)
        emoji = "PASS" if result["status"] == "succeeded" else "FAIL"
        print(f"  [{emoji}] width={w} elapsed={result.get('elapsedSec')}s "
              f"fabric={result['fabricDims']} status={result['status']}")

    max_proven = max((r["width"] for r in results if r["status"] == "succeeded"), default=0)
    report = {
        "schemaVersion": 1,
        "artifactKind": "cslc_grid_probe_report",
        "arch": args.arch,
        "layoutPath": rel(layout),
        "cslcExecutable": args.cslc,
        "results": results,
        "summary": {
            "maxProvenWidth": max_proven,
            "maxProvenPeCount": max_proven,
            "widthsTested": len(widths),
            "widthsPassed": sum(1 for r in results if r["status"] == "succeeded"),
            "widthsFailed": sum(1 for r in results if r["status"] == "failed"),
            "widthsTimedOut": sum(1 for r in results if r["status"] == "timeout"),
        },
    }

    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {rel(out_path)} (max proven width={max_proven}, "
        f"{report['summary']['widthsPassed']}/{report['summary']['widthsTested']} sizes passed)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
