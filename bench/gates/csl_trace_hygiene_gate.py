#!/usr/bin/env python3
"""Fail if CSL receipts/traces contain publish-unsafe SDK artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DENIED_SUBSTRINGS = (
    ".elf",
    ".pelf",
    ".sif",
    "csl-extras",
    "cerebras-software-eula",
    "sdk-cbcore-",
    "simfab_traces",
    "corefile.cs1",
    "sim.log",
    "sdk_debug",
    "sdk-gui",
)
CMADDR_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d+\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", action="append", default=[])
    return parser.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def walk_strings(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(prefix or "<root>", value)]
    if isinstance(value, list):
        out: list[tuple[str, str]] = []
        for idx, item in enumerate(value):
            out.extend(walk_strings(item, f"{prefix}[{idx}]"))
        return out
    if isinstance(value, dict):
        out: list[tuple[str, str]] = []
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            out.extend(walk_strings(item, child))
        return out
    return []


def default_paths() -> list[str]:
    return [
        "bench/out/streaming-executor/e2b-layer-block-smoke-trace.json",
        "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
        "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json",
        "examples/doe-csl-reference-parity.gemma-4-e2b-layer-block.sample.json",
        "examples/doe-csl-demo-evidence.gemma-4-e2b.sample.json",
        "examples/doe-csl-appliance-driver-receipt.sample.json",
        "examples/doe-csl-int4ple-hardware-receipt.pending.sample.json",
    ]


def main() -> int:
    paths = parse_args().path or default_paths()
    failures: list[str] = []
    checked = 0
    for raw in paths:
        path = resolve(raw)
        if not path.is_file():
            failures.append(f"{raw}: missing")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{raw}: cannot read JSON: {exc}")
            continue
        checked += 1
        for location, text in walk_strings(payload):
            lowered = text.lower()
            for denied in DENIED_SUBSTRINGS:
                if denied in lowered:
                    failures.append(
                        f"{raw}:{location}: contains publish-unsafe "
                        f"token {denied!r}"
                    )
            if CMADDR_RE.search(text) and "$DOE_CSL_CMADDR" not in text:
                failures.append(
                    f"{raw}:{location}: contains unredacted "
                    "cmaddr-like endpoint"
                )

    if failures:
        print("FAIL: CSL trace hygiene gate")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"PASS: CSL trace hygiene gate ({checked} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
