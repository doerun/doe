#!/usr/bin/env python3
"""Regression checks for the CSL SDK 2.10 migration surface."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_CSL_TOKENS = (
    "comptime_struct",
    "@concat_struct",
)

SOURCE_SCAN_ROOTS = (
    REPO_ROOT / "examples" / "csl",
    REPO_ROOT / "runtime" / "zig" / "examples" / "simulator",
    REPO_ROOT / "runtime" / "zig" / "src" / "doe_wgsl",
)

SOURCE_SUFFIXES = {".csl", ".zig"}

SOURCE_SKIP_FILES = {
    REPO_ROOT / "runtime" / "zig" / "src" / "doe_wgsl" / "emit_csl_validate.zig",
}

VERSION_SCAN_ROOTS = (
    REPO_ROOT / "examples",
    REPO_ROOT / "runtime" / "zig" / "examples",
)


def _iter_files(roots: tuple[Path, ...], suffixes: set[str]):
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in suffixes:
                continue
            yield path


class CslSdk210MigrationTests(unittest.TestCase):
    def test_generated_csl_sources_do_not_use_removed_struct_constructs(self) -> None:
        offenders: list[str] = []
        for path in _iter_files(SOURCE_SCAN_ROOTS, SOURCE_SUFFIXES):
            if path.resolve() in SOURCE_SKIP_FILES:
                continue
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_CSL_TOKENS:
                if token in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
        self.assertEqual([], offenders)

    def test_fabric_dsds_use_queue_color_binding(self) -> None:
        offenders: list[str] = []
        for path in _iter_files(SOURCE_SCAN_ROOTS, SOURCE_SUFFIXES):
            if path.resolve() in SOURCE_SKIP_FILES:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                window = "\n".join(lines[index : index + 8])
                rel = path.relative_to(REPO_ROOT)
                if "@get_dsd(fabin_dsd" in line:
                    if ".input_queue" not in window:
                        offenders.append(f"{rel}:{index + 1}: fabin_dsd missing input_queue")
                    if ".fabric_color" in window:
                        offenders.append(f"{rel}:{index + 1}: fabin_dsd uses fabric_color")
                if "@get_dsd(fabout_dsd" in line:
                    if ".output_queue" not in window:
                        offenders.append(f"{rel}:{index + 1}: fabout_dsd missing output_queue")
                    if ".fabric_color" in window:
                        offenders.append(f"{rel}:{index + 1}: fabout_dsd uses fabric_color")
        self.assertEqual([], offenders)

    def test_current_csl_contract_fixtures_use_sdk_210_floor(self) -> None:
        offenders: list[str] = []
        for path in _iter_files(VERSION_SCAN_ROOTS, {".json"}):
            text = path.read_text(encoding="utf-8")
            if "sdkVersionFloor" not in text and "minimumVersion" not in text:
                continue
            if '"1.4.0"' in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
