#!/usr/bin/env python3
"""Fail if Cerebras SDK or cslc-generated artifacts are tracked."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class Violation:
    path: str
    reason: str


DENIED_SUFFIXES = (".elf", ".pelf", ".sif")
DENIED_FILENAMES = {
    "cerebras-software-eula.pdf",
    "sim.log",
    "corefile.cs1",
}
DENIED_DIR_NAMES = {
    "cerebras-sdk",
    "simfab_traces",
    "sdk-gui",
    "sdk_debug",
}
DENIED_WHEEL_PREFIXES = (
    "cerebras_sdk",
    "cerebras-appliance",
    "cerebras_appliance",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="",
        help="Repository root. Defaults to two directories above this script.",
    )
    return parser.parse_args()


def repo_root(raw_root: str) -> Path:
    if raw_root:
        return Path(raw_root).resolve()
    return Path(__file__).resolve().parents[2]


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    ]


def is_runtime_compiled_output(path: PurePosixPath) -> bool:
    parts = path.parts
    prefix = ("runtime", "zig", "examples", "simulator")
    if len(parts) < len(prefix) + 3 or parts[: len(prefix)] != prefix:
        return False
    return "compile" in parts and "compiled" in parts


def classify(path_text: str) -> str | None:
    path = PurePosixPath(path_text)
    lower_parts = tuple(part.lower() for part in path.parts)
    lower_name = path.name.lower()

    if any(part.startswith("csl-extras-") for part in lower_parts):
        return "Cerebras SDK csl-extras content must not be tracked"
    if is_runtime_compiled_output(PurePosixPath(*lower_parts)):
        return "cslc compile output must stay in local evidence bundles"
    if lower_name.endswith(DENIED_SUFFIXES):
        return "compiled Cerebras/SDK binary artifact must not be tracked"
    if lower_name in DENIED_FILENAMES:
        return "raw SDK run/debug artifact must not be tracked"
    if lower_name.endswith(".whl") and lower_name.startswith(DENIED_WHEEL_PREFIXES):
        return "Cerebras SDK/appliance wheel must not be tracked"
    if any(part in DENIED_DIR_NAMES for part in lower_parts):
        return "Cerebras SDK/debug artifact directory must not be tracked"
    if lower_name.startswith("sdk-cbcore-"):
        return "Cerebras SDK container image must not be tracked"
    return None


def find_violations(paths: list[str]) -> list[Violation]:
    violations: list[Violation] = []
    for path in paths:
        reason = classify(path)
        if reason is not None:
            violations.append(Violation(path=path, reason=reason))
    return violations


def main() -> int:
    root = repo_root(parse_args().root)
    violations = find_violations(tracked_files(root))
    if violations:
        print("FAIL: Cerebras artifact gate")
        for violation in violations:
            print(f"{violation.path}: {violation.reason}")
        return 1
    print("PASS: Cerebras artifact gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
