#!/usr/bin/env python3
"""Probe cslc across 2D grid sizes.

Last turn's probe_cslc_grid_limits.py tested 1D widths and surfaced the
SDK memcpy .width i16 ceiling at peCount > 32,767. The aggregate claimed
that emitting 2D layouts keeps each axis under i16 max (e.g. 246x236 for
31B). This probe tests that claim for real on a 2D variant of the
elementwise-double kernel.

Outputs a report listing each (width, height) tested with status.
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--cslc", default="/home/x/cerebras-sdk/cslc")
    p.add_argument(
        "--layout",
        default="bench/out/cslc-grid-probe/elementwise-double-2d/layout.csl",
    )
    p.add_argument(
        "--grids",
        default="4x2,16x8,149x117,246x236",
        help="Comma-separated WxH entries",
    )
    p.add_argument("--arch", default="wse3")
    p.add_argument(
        "--out-json",
        default="bench/out/cslc-grid-probe/2d-grid-probe-report.json",
    )
    p.add_argument("--per-run-timeout-sec", type=int, default=1800)
    return p.parse_args()


def resolve(p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else (REPO_ROOT / pp).resolve()


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p.resolve())


def compute_fabric(width: int, height: int) -> tuple[int, int, int, int]:
    fabric_w = width + 4 + 3
    fabric_h = height + 1 + 1
    return fabric_w, fabric_h, 4, 1


def run_cslc(
    *, cslc: str, layout: Path, width: int, height: int, arch: str,
    out_dir: Path, timeout_sec: int,
) -> dict:
    fw, fh, ox, oy = compute_fabric(width, height)
    cmd = [
        cslc, str(layout),
        f"--arch={arch}",
        f"--fabric-dims={fw},{fh}",
        f"--fabric-offsets={ox},{oy}",
        "--channels=1",
        f"--params=width:{width},height:{height}",
        "-o", str(out_dir),
        "--memcpy",
    ]
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return {
            "width": width, "height": height, "peCount": width * height,
            "fabricDims": [fw, fh], "status": "timeout",
            "elapsedSec": float(timeout_sec), "stderrTail": "",
        }
    elapsed = time.time() - start
    status = "succeeded" if proc.returncode == 0 else "failed"
    return {
        "width": width, "height": height, "peCount": width * height,
        "fabricDims": [fw, fh], "status": status,
        "returnCode": proc.returncode,
        "elapsedSec": round(elapsed, 2),
        "stderrTail": (proc.stderr or "")[-800:],
    }


def main() -> int:
    args = parse_args()
    layout = resolve(args.layout)
    if not layout.exists():
        print(f"FAIL: 2D layout not found at {layout}")
        return 1

    grids: list[tuple[int, int]] = []
    for entry in args.grids.split(","):
        w, _, h = entry.strip().partition("x")
        grids.append((int(w), int(h)))

    out_dir_root = resolve(args.out_json).parent / "2d-compile-outputs"
    out_dir_root.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for w, h in grids:
        out_dir = out_dir_root / f"{w}x{h}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        r = run_cslc(
            cslc=args.cslc, layout=layout, width=w, height=h,
            arch=args.arch, out_dir=out_dir, timeout_sec=args.per_run_timeout_sec,
        )
        results.append(r)
        tag = "PASS" if r["status"] == "succeeded" else "FAIL"
        print(f"  [{tag}] {w}x{h} = {w*h:,} PE  elapsed={r.get('elapsedSec')}s  status={r['status']}")
        if r["status"] != "succeeded":
            print(f"    stderr tail: {r['stderrTail'][-300:]}")

    report = {
        "schemaVersion": 1,
        "artifactKind": "cslc_2d_grid_probe_report",
        "arch": args.arch,
        "layoutPath": rel(layout),
        "results": results,
        "summary": {
            "maxProvenPeCount": max((r["peCount"] for r in results if r["status"] == "succeeded"), default=0),
            "gridsTested": len(results),
            "gridsPassed": sum(1 for r in results if r["status"] == "succeeded"),
            "gridsFailed": sum(1 for r in results if r["status"] == "failed"),
        },
    }
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {rel(out_path)} (max proven peCount={report['summary']['maxProvenPeCount']:,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
