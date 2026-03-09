#!/usr/bin/env python3
"""Prune old timestamped browser-lane artifacts."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifacts-dir",
        default="nursery/fawn-browser/artifacts",
        help="Browser artifact directory to prune.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=14,
        help="Remove timestamped artifact folders older than this many days.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def parse_timestamp_dir(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.name, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def main() -> int:
    args = parse_args()
    if args.retention_days < 0:
        raise SystemExit("--retention-days must be >= 0")
    root = Path(args.artifacts_dir)
    if not root.exists():
        raise SystemExit(f"artifacts directory does not exist: {root}")

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.retention_days)
    candidates = []
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        timestamp = parse_timestamp_dir(entry)
        if timestamp is None:
            continue
        if timestamp < cutoff:
            candidates.append(entry)

    print(f"browser artifact cleanup candidates: {len(candidates)}")
    for candidate in candidates:
        print(candidate)

    if args.dry_run:
        return 0
    for candidate in candidates:
        shutil.rmtree(candidate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
