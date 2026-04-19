#!/usr/bin/env python3
"""Validate a doe_kernel_chain_parity receipt against its schema.

Optional strict flags:
  --require-bit-exact     — fail unless laneStatus is 'bit_exact'.
  --require-bit-close     — fail unless laneStatus is 'bit_close' or 'bit_exact'.

Per-step parity counts too: if any perStepParity.passed is false the gate
fails regardless of end-to-end result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", required=True)
    p.add_argument("--schema", default="config/doe-kernel-chain-parity.schema.json")
    p.add_argument("--require-bit-exact", action="store_true")
    p.add_argument("--require-bit-close", action="store_true")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def main() -> int:
    args = parse_args()
    try:
        receipt = json.loads(resolve(args.receipt).read_text(encoding="utf-8"))
        schema = json.loads(resolve(args.schema).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: kernel chain parity gate: {exc}")
        return 1

    failures = [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(receipt),
            key=lambda it: tuple(str(p) for p in it.absolute_path),
        )
    ]

    for step in receipt.get("steps", []):
        if not step.get("perStepParity", {}).get("passed", False):
            failures.append(f"step[{step.get('stepIndex')}] {step.get('fixtureId')!r}: perStepParity.passed=false")

    end_to_end = receipt.get("endToEndParity", {})
    if not end_to_end.get("passed", False):
        failures.append(
            f"endToEndParity.passed=false, maxAbsErr={end_to_end.get('maxAbsErr')}"
        )

    lane_status = receipt.get("laneStatus", "")
    if args.require_bit_exact and lane_status != "bit_exact":
        failures.append(f"laneStatus={lane_status!r}, expected 'bit_exact'")
    if args.require_bit_close and lane_status not in ("bit_exact", "bit_close"):
        failures.append(f"laneStatus={lane_status!r}, expected 'bit_exact' or 'bit_close'")

    if failures:
        print("FAIL: kernel chain parity gate")
        for f in failures:
            print(f"  {f}")
        return 1

    print(
        f"PASS: kernel chain parity gate "
        f"(chain={receipt.get('chainName', '?')}, steps={len(receipt.get('steps', []))}, "
        f"endToEnd maxAbsErr={end_to_end.get('maxAbsErr'):.3e}, laneStatus={lane_status!r})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
