#!/usr/bin/env python3
"""Restore tracked Cerebras receipt fields that are volatile by design."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
VOLATILE_KEYS = {
    "adapterWallclockNsSum",
    "wallclockNs",
}
TRACKED_RECEIPTS = (
    "bench/out/r3-1-31b-af16-doppler-csl-splice/"
    "session-single_block_hidden/hostplan-runtime/launch-receipts/"
    "launch-0001.json",
)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "__volatile__" if key in VOLATILE_KEYS else normalize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def restore_if_only_volatile(path: str) -> tuple[bool, str]:
    status = git("status", "--porcelain", "--", path)
    if status.returncode != 0:
        return False, status.stderr.strip() or f"git_status_failed:{path}"
    if not status.stdout.strip():
        return False, f"unchanged:{path}"

    head = git("show", f"HEAD:{path}")
    if head.returncode != 0:
        return False, head.stderr.strip() or f"git_show_failed:{path}"
    current_path = REPO_ROOT / path
    try:
        baseline = json.loads(head.stdout)
        current = json.loads(current_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"receipt_parse_failed:{path}:{exc}"

    if normalize(baseline) != normalize(current):
        return False, f"nonvolatile_receipt_drift:{path}"

    current_path.write_text(
        json.dumps(baseline, indent=2) + "\n",
        encoding="utf-8",
    )
    return True, f"restored:{path}"


def main() -> int:
    failed = []
    restored_count = 0
    for path in TRACKED_RECEIPTS:
        restored, message = restore_if_only_volatile(path)
        print(message)
        if restored:
            restored_count += 1
        elif message.startswith(("nonvolatile_", "receipt_parse_", "git_")):
            failed.append(message)
    if failed:
        for message in failed:
            print(f"FAIL: {message}", file=sys.stderr)
        return 1
    print(f"PASS: restored {restored_count} volatile receipt file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
