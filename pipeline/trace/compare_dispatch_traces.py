#!/usr/bin/env python3
"""
Compare two NDJSON trace streams entry-by-entry using the decision envelope contract.
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


def validate_sequences(
    baseline: list[dict[str, Any]],
    comparison: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    baseline_len = len(baseline)
    comparison_len = len(comparison)
    if baseline_len != comparison_len:
        errors.append(
            f"entry_count mismatch: baseline={baseline_len} comparison={comparison_len}"
        )

    checked = min(baseline_len, comparison_len)
    for i in range(checked):
        a = pick_fields(baseline[i])
        b = pick_fields(comparison[i])
        if a != b:
            errors.append(f"entry[{i}] diff\nbaseline={a}\ncomparison={b}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--comparison", required=True, type=Path)
    args = parser.parse_args()

    baseline = read_ndjson(args.baseline)
    comparison = read_ndjson(args.comparison)
    diffs = validate_sequences(baseline, comparison)
    if diffs:
        print("FAIL")
        for item in diffs:
            print(item)
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
