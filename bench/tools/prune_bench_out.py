#!/usr/bin/env python3
"""Prune bulky bench/out content while keeping the portable JSON artifact surface."""

from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_OUT = REPO_ROOT / "bench" / "out"

KEEP_FILE_NAMES = {
    "README.local.md",
}
KEEP_SUFFIXES = (
    ".run.json",
    ".compare.json",
    ".compare-dev.json",
    ".release.json",
    ".smoke.json",
    ".claim.json",
)
KEEP_PREFIXES = (
    "test-inventory",
)


def should_keep(path: Path) -> bool:
    relative = path.relative_to(BENCH_OUT)
    if path.name in KEEP_FILE_NAMES:
        return True
    if any(path.name.endswith(suffix) for suffix in KEEP_SUFFIXES):
        return True
    if any(path.name.startswith(prefix) and path.suffix == ".json" for prefix in KEEP_PREFIXES):
        return True
    if relative == Path("cube/latest/cube.summary.json"):
        return True
    if relative == Path("cube/latest/cube.rows.json"):
        return True
    if relative == Path("visualization/latest/inventory.json"):
        return True
    if relative == Path("visualization/latest/pipeline.summary.json"):
        return True
    if relative == Path("visualization/latest/cube.summary.json"):
        return True
    if relative == Path("visualization/latest/cube.rows.json"):
        return True
    return False


def prune(root: Path, *, dry_run: bool) -> tuple[int, int]:
    removed_files = 0
    removed_dirs = 0
    for path in sorted(root.rglob("*"), key=lambda item: (len(item.parts), str(item)), reverse=True):
        if path.is_symlink():
            continue
        if path.is_file():
            if should_keep(path):
                continue
            removed_files += 1
            if not dry_run:
                path.unlink()
        elif path.is_dir():
            try:
                next(path.iterdir())
            except StopIteration:
                removed_dirs += 1
                if not dry_run:
                    path.rmdir()
    return removed_files, removed_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be removed without deleting anything.",
    )
    parser.add_argument(
        "--reset-visualization-latest",
        action="store_true",
        help="After pruning, recreate bench/out/visualization/latest as an empty directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not BENCH_OUT.exists():
        print(f"FAIL: missing {BENCH_OUT}")
        return 1
    removed_files, removed_dirs = prune(BENCH_OUT, dry_run=args.dry_run)
    if args.reset_visualization_latest and not args.dry_run:
        (BENCH_OUT / "visualization" / "latest").mkdir(parents=True, exist_ok=True)
    mode = "would remove" if args.dry_run else "removed"
    print(f"PASS: {mode} {removed_files} files and {removed_dirs} empty directories under {BENCH_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
