#!/usr/bin/env python3
"""Host preflight checks for Apple Metal lanes."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VERSION_PATTERN = re.compile(r"\b\d+(?:\.\d+)*\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-toolchain",
        action="store_true",
        help="Require xcrun metal/metallib availability.",
    )
    parser.add_argument(
        "--toolchain",
        default="config/shader-toolchain.json",
        help="Shader toolchain contract used for optional Metal version checks.",
    )
    return parser.parse_args()


def run_tool(*cmd: str) -> bool:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return completed.returncode == 0


def capture_tool(*cmd: str) -> tuple[bool, str]:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output


def load_expected_versions(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    platforms = payload.get("platforms")
    if not isinstance(platforms, dict):
        return {}
    macos = platforms.get("macos")
    if not isinstance(macos, dict):
        return {}
    backends = macos.get("backends")
    if not isinstance(backends, dict):
        return {}
    metal = backends.get("doe_metal")
    if not isinstance(metal, dict):
        return {}
    stages = metal.get("requiredStages")
    if not isinstance(stages, list):
        return {}

    versions: dict[str, str] = {}
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if stage.get("implementation") != "external_tool":
            continue
        tool = stage.get("tool")
        args = stage.get("args")
        version = stage.get("version")
        if tool != "xcrun" or not isinstance(args, list) or not args or not isinstance(version, str):
            continue
        if args[0] in ("metal", "metallib"):
            versions[str(args[0])] = version
    return versions


def version_matches(expected: str, output: str) -> bool:
    expected_parts = expected.split(".")
    for token in VERSION_PATTERN.findall(output):
        token_parts = token.split(".")
        if len(token_parts) < len(expected_parts):
            continue
        matches = True
        for expected_part, actual_part in zip(expected_parts, token_parts):
            if expected_part == "x":
                continue
            if expected_part != actual_part:
                matches = False
                break
        if matches:
            return True
    return False


def main() -> int:
    args = parse_args()

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

    if args.require_toolchain:
        versions = load_expected_versions(Path(args.toolchain))
        for tool_name in ("metal", "metallib"):
            expected = versions.get(tool_name)
            if not expected:
                continue
            ok, output = capture_tool("xcrun", tool_name, "-version")
            if not ok:
                print(f"FAIL: xcrun {tool_name} -version failed")
                return 1
            if not version_matches(expected, output):
                print(
                    f"FAIL: {tool_name} version mismatch; expected pattern {expected!r}, got: {output.strip()}"
                )
                return 1

    print("PASS: metal host preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
