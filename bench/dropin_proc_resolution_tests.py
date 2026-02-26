#!/usr/bin/env python3
"""Drop-in proc resolution checks with ownership-aware expectations."""

from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--ownership", default="config/dropin-symbol-ownership.json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def main() -> int:
    args = parse_args()
    artifact = Path(args.artifact)
    ownership = load_json(Path(args.ownership))

    if not artifact.exists():
        print(f"FAIL: missing artifact: {artifact}")
        return 1

    lib = ctypes.CDLL(str(artifact))
    failures: list[str] = []

    symbols = ownership.get("symbols")
    if not isinstance(symbols, list):
        print("FAIL: ownership symbols missing/invalid")
        return 1

    for entry in symbols:
        if not isinstance(entry, dict):
            continue
        symbol = entry.get("symbol")
        required = bool(entry.get("requiredInStrict", False))
        if not isinstance(symbol, str) or not symbol:
            continue
        resolved = hasattr(lib, symbol)
        if required and not resolved:
            failures.append(f"required symbol unresolved: {symbol}")

    if failures:
        print("FAIL: dropin proc resolution")
        for item in failures:
            print(f"  {item}")
        return 1

    print("PASS: dropin proc resolution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
