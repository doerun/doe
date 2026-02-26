#!/usr/bin/env python3
"""Host preflight checks for local Metal lanes."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-toolchain",
        action="store_true",
        help="Require xcrun metal/metallib availability.",
    )
    return parser.parse_args()


def run_tool(*cmd: str) -> bool:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return completed.returncode == 0


def main() -> int:
    _ = parse_args()

    if sys.platform != "darwin":
        print("FAIL: Metal preflight requires macOS host")
        return 1

    if shutil.which("xcrun") is None:
        print("FAIL: missing xcrun")
        return 1

    if not run_tool("xcrun", "--find", "metal"):
        print("FAIL: xcrun cannot locate metal tool")
        return 1

    if not run_tool("xcrun", "--find", "metallib"):
        print("FAIL: xcrun cannot locate metallib tool")
        return 1

    print("PASS: metal host preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
