#!/usr/bin/env python3
"""Blocking file-size gate: enforces maximum line counts for source files.

Zig runtime sources in zig/src/ must not exceed 777 lines.
Python benchmark/tooling files in bench/ and agent/ must not exceed 1200 lines.

Exit 0 when all files are within limits, 1 when any violation is found.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ZIG_LINE_LIMIT = 777
PYTHON_LINE_LIMIT = 1200

# Directories containing third-party code that are not subject to project limits.
VENDOR_DIRS = ("vendor",)


@dataclass(frozen=True)
class Violation:
    path: str
    line_count: int
    limit: int
    language: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default="",
        help="Repository root. Auto-detected when omitted.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Relative path (from repo root) to exclude from checks. May be repeated.",
    )
    return parser.parse_args()


def detect_repo_root(explicit_root: str) -> Path:
    if explicit_root:
        root = Path(explicit_root)
        if not root.exists():
            raise ValueError(f"invalid --root path: {root}")
        return root.resolve()

    cwd = Path.cwd()
    if (cwd / "zig" / "src").is_dir() and (cwd / "bench").is_dir():
        return cwd.resolve()
    nested = cwd / "fawn"
    if (nested / "zig" / "src").is_dir() and (nested / "bench").is_dir():
        return nested.resolve()

    raise ValueError(
        "unable to auto-detect repository root; pass --root with a path "
        "containing zig/src/ and bench/"
    )


def count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _is_vendored(path: Path, scan_root: Path) -> bool:
    """Return True when the file lives under a vendor directory."""
    try:
        parts = path.relative_to(scan_root).parts
    except ValueError:
        return False
    return any(part in VENDOR_DIRS for part in parts)


def scan_directory(
    root: Path,
    rel_dir: str,
    extension: str,
    limit: int,
    language: str,
    excludes: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    scan_root = root / rel_dir
    if not scan_root.is_dir():
        return violations
    for path in sorted(scan_root.rglob(f"*{extension}")):
        if not path.is_file():
            continue
        if _is_vendored(path, scan_root):
            continue
        rel = str(path.relative_to(root))
        if rel in excludes:
            continue
        lines = count_lines(path)
        if lines > limit:
            violations.append(
                Violation(
                    path=rel,
                    line_count=lines,
                    limit=limit,
                    language=language,
                )
            )
    return violations


def main() -> int:
    args = parse_args()
    try:
        root = detect_repo_root(args.root)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    excludes = set(args.exclude)
    violations: list[Violation] = []

    violations.extend(
        scan_directory(root, "zig/src", ".zig", ZIG_LINE_LIMIT, "zig", excludes)
    )
    violations.extend(
        scan_directory(root, "bench", ".py", PYTHON_LINE_LIMIT, "python", excludes)
    )
    violations.extend(
        scan_directory(root, "agent", ".py", PYTHON_LINE_LIMIT, "python", excludes)
    )

    if args.json_output:
        payload = {
            "gate": "file-size",
            "status": "fail" if violations else "pass",
            "violations": [
                {
                    "filePath": v.path,
                    "lineCount": v.line_count,
                    "limit": v.limit,
                    "language": v.language,
                }
                for v in violations
            ],
            "checkedLimits": {
                "zig": {"directory": "zig/src", "maxLines": ZIG_LINE_LIMIT},
                "python": {
                    "directories": ["bench", "agent"],
                    "maxLines": PYTHON_LINE_LIMIT,
                },
            },
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if violations else 0

    if violations:
        print("FAIL: file-size gate")
        for v in violations:
            print(
                f"  {v.path}: {v.line_count} lines "
                f"(limit {v.limit} for {v.language})"
            )
        return 1

    print("PASS: file-size gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
