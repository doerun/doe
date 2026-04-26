#!/usr/bin/env python3
"""Cluster B Gemma 3 1B Doe-CSL host-plan fixture regen drift gate.

Mitigates "Cluster B fixture regen drift" from
docs/cerebras-north-star.md (Local risk mitigations).

The Cluster B clean-tree bundle gate reads two pinned fixture files
(`host-plan.json` and `doppler-program-bundle.json` under
`bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/`). If those
files drift from the recorded baseline without an explicit re-pin, the
bundle gate would silently start shipping unrelated content.

This gate reads the baseline at
`config/cluster-b-fixture-regen-baseline.json` and verifies every
listed fixture's sha256 against the current on-disk content. Failure
modes:
  - missing: fixture path does not exist on disk
  - drifted: fixture exists but sha256 does not match the baseline

Re-pin path: regenerate the fixtures intentionally, then update the
baseline by re-hashing and editing the JSON file. The gate is a guard
on accidental regeneration, not a freeze on legitimate updates.

Usage:
    python3 bench/gates/cluster_b_fixture_regen_gate.py
    python3 bench/gates/cluster_b_fixture_regen_gate.py --baseline path/to/baseline.json

Exit:
    0 - all fixtures match baseline
    1 - one or more fixtures drifted or missing
    2 - baseline file invalid
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = REPO_ROOT / "config/cluster-b-fixture-regen-baseline.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Path to the Cluster B fixture regen baseline JSON.",
    )
    return p.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    args = parse_args()
    if not args.baseline.is_file():
        print(
            f"FAIL: cluster_b_fixture_regen_gate: baseline {args.baseline} not found",
            file=sys.stderr,
        )
        return 2

    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"FAIL: cluster_b_fixture_regen_gate: baseline parse failed: {exc}",
            file=sys.stderr,
        )
        return 2

    fixtures = baseline.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        print(
            "FAIL: cluster_b_fixture_regen_gate: baseline.fixtures must be a non-empty list",
            file=sys.stderr,
        )
        return 2

    failures: list[str] = []
    for entry in fixtures:
        rel = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(rel, str) or not isinstance(expected, str):
            failures.append(
                f"baseline entry malformed: {entry!r}"
            )
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            failures.append(f"missing fixture: {rel}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            failures.append(
                f"drifted: {rel} sha256={actual} (baseline={expected}). "
                f"Either revert the regeneration or re-pin the baseline "
                f"in {args.baseline.relative_to(REPO_ROOT)}."
            )

    if failures:
        print(
            f"FAIL: cluster_b_fixture_regen_gate ({len(failures)} fixture(s) "
            f"drifted/missing)"
        )
        for f in failures:
            print(f"  {f}")
        return 1

    print(
        f"PASS: cluster_b_fixture_regen_gate ({len(fixtures)} fixture(s) "
        f"match baseline)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
