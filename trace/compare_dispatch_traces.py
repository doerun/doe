#!/usr/bin/env python3
"""
Compare two NDJSON trace streams row-by-row using the decision envelope contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TRACE_FIELDS = {
    "seq",
    "command",
    "kernel",
    "matched",
    "scope",
    "safetyClass",
    "verificationMode",
    "proofLevel",
    "requiresLean",
    "blocking",
    "score",
    "matched_count",
    "action",
    "toggle",
}


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def pick_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in TRACE_FIELDS if k in row}


def validate_sequences(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    left_len = len(left)
    right_len = len(right)
    if left_len != right_len:
        errors.append(f"row_count mismatch: left={left_len} right={right_len}")

    checked = min(left_len, right_len)
    for i in range(checked):
        a = pick_fields(left[i])
        b = pick_fields(right[i])
        if a != b:
            errors.append(f"row[{i}] diff\nleft={a}\nright={b}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    args = parser.parse_args()

    left = read_ndjson(args.left)
    right = read_ndjson(args.right)
    diffs = validate_sequences(left, right)
    if diffs:
        print("FAIL")
        for item in diffs:
            print(item)
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
