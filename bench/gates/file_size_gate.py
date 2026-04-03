#!/usr/bin/env python3
"""Blocking file-size gate: enforces maximum line counts for source files.

Zig runtime sources in runtime/zig/src/ must not exceed 999 lines.
Python benchmark/tooling files in bench/ and pipeline/agent/ must not exceed 1200 lines.

Exemptions (Zig): test files (test_*.zig, *_test.zig, test_suite*.zig) and
wgpu_types.zig are data-heavy by nature and exempt from the 999-line limit.

Exit 0 when all files are within limits, 1 when any violation is found.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


ZIG_LINE_LIMIT = 999
PYTHON_LINE_LIMIT = 1200

# Directories containing third-party code that are not subject to project limits.
VENDOR_DIRS = ("vendor",)

# Zig filenames exempt from the line limit (test and type-definition files).
ZIG_EXEMPT_NAMES = frozenset({"wgpu_types.zig"})
ZIG_EXEMPT_PREFIXES = ("test_", "test_suite")
ZIG_EXEMPT_SUFFIXES = ("_test.zig",)


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
    if (cwd / "runtime" / "zig" / "src").is_dir() and (cwd / "bench").is_dir():
        return cwd.resolve()
    nested = cwd / "fawn"
    if (nested / "runtime" / "zig" / "src").is_dir() and (nested / "bench").is_dir():
        return nested.resolve()

    raise ValueError(
        "unable to auto-detect repository root; pass --root with a path "
        "containing runtime/zig/src/ and bench/"
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


def _is_zig_exempt(name: str) -> bool:
    """Return True for Zig files exempt from the line limit per CLAUDE.md policy."""
    if name in ZIG_EXEMPT_NAMES:
        return True
    if any(name.startswith(p) for p in ZIG_EXEMPT_PREFIXES):
        return True
    if any(name.endswith(s) for s in ZIG_EXEMPT_SUFFIXES):
        return True
    return False


def scan_directory(
    root: Path,
    rel_dir: str,
    extension: str,
    limit: int,
    language: str,
    excludes: set[str],
    *,
    exempt_fn: Callable[[str], bool] | None = None,
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
        if exempt_fn is not None and exempt_fn(path.name):
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
        scan_directory(
            root, "runtime/zig/src", ".zig", ZIG_LINE_LIMIT, "zig", excludes,
            exempt_fn=_is_zig_exempt,
        )
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
                "zig": {"directory": "runtime/zig/src", "maxLines": ZIG_LINE_LIMIT},
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
