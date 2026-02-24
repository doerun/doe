#!/usr/bin/env python3
"""List benchmark output run folders with manifest-derived summary."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TIMESTAMP_RE = re.compile(r"^\d{8}T\d{6}Z$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default="bench/out",
        help="Benchmark output directory.",
    )
    parser.add_argument(
        "--include-scratch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include bench/out/scratch/<timestamp> folders.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum rows to print (0 = all).",
    )
    return parser.parse_args()


def is_timestamp_folder(path: Path) -> bool:
    return path.is_dir() and bool(TIMESTAMP_RE.fullmatch(path.name))


def collect_folders(out_dir: Path, *, include_scratch: bool) -> list[Path]:
    folders = [path for path in out_dir.iterdir() if is_timestamp_folder(path)]
    if include_scratch:
        scratch_root = out_dir / "scratch"
        if scratch_root.is_dir():
            folders.extend(path for path in scratch_root.iterdir() if is_timestamp_folder(path))
    return sorted(
        folders,
        key=lambda path: (
            path.name,
            1 if "scratch" in path.parts else 0,
            str(path),
        ),
    )


def read_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path / "run_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def summarize_files(path: Path) -> str:
    names = sorted(item.name for item in path.iterdir())
    compare_reports = [name for name in names if name.startswith("dawn-vs-fawn") and name.endswith(".json")]
    compare_html = [name for name in names if name.startswith("dawn-vs-fawn") and name.endswith(".html")]
    release_windows = [name for name in names if name.startswith("release-claim-windows") and name.endswith(".json")]
    dropin_reports = [name for name in names if name.startswith("dropin_report") and name.endswith(".json")]

    if compare_reports:
        return f"compare:{len(compare_reports)} html:{len(compare_html)}"
    if release_windows:
        return f"release-windows:{len(release_windows)}"
    if dropin_reports:
        return f"dropin:{len(dropin_reports)}"
    return f"files:{len(names)}"


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    if not out_dir.exists() or not out_dir.is_dir():
        print(f"FAIL: invalid --out-dir: {out_dir}")
        return 1

    rows: list[str] = []
    folders = collect_folders(out_dir, include_scratch=args.include_scratch)
    for folder in folders:
        manifest = read_manifest(folder)
        run_type = str(manifest.get("runType", "unknown"))
        status = str(manifest.get("status", "unknown"))
        scope = "scratch" if "scratch" in folder.parts else "canonical"
        row = (
            f"{folder.name}  "
            f"{scope:9}  "
            f"{run_type:24}  "
            f"{status:18}  "
            f"{summarize_files(folder)}"
        )
        rows.append(row)

    if args.limit > 0:
        rows = rows[-args.limit :]

    if not rows:
        print("no timestamp folders found")
        return 0

    print("timestamp          scope      run_type                  status              summary")
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
