#!/usr/bin/env python3
"""Enforce the 999-line limit for Zig runtime source files.

Scans runtime/zig/src/**/*.zig and reports any file exceeding 999 lines.
Test files (*_test.zig, test_*.zig, test_suite*.zig) and type-definition
files (wgpu_types.zig) are exempt since they are data-heavy by nature.

Optionally checks Python files in bench/ against the 1200-line limit
when --with-python is passed.

Exit code 0 if all files pass, 1 if any violations found.
"""

import argparse
import os
import sys

ZIG_SRC_ROOT = os.path.join("runtime", "zig", "src")
ZIG_LINE_LIMIT = 999

PYTHON_BENCH_ROOT = "bench"
PYTHON_LINE_LIMIT = 1200

# Zig filenames exempt from the line limit per CLAUDE.md policy.
ZIG_EXEMPT_NAMES = {"wgpu_types.zig"}
ZIG_EXEMPT_PREFIXES = ("test_", "test_suite")
ZIG_EXEMPT_SUFFIXES = ("_test.zig",)

# Directories containing third-party code that are not subject to project limits.
VENDOR_DIRS = {"vendor"}


def is_zig_exempt(filename):
    base = os.path.basename(filename)
    if base in ZIG_EXEMPT_NAMES:
        return True
    if any(base.startswith(p) for p in ZIG_EXEMPT_PREFIXES):
        return True
    if any(base.endswith(s) for s in ZIG_EXEMPT_SUFFIXES):
        return True
    return False


def is_vendored(path):
    return any(part in VENDOR_DIRS for part in path.split(os.sep))


def count_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def scan_zig(violations):
    if not os.path.isdir(ZIG_SRC_ROOT):
        print(f"WARNING: {ZIG_SRC_ROOT} not found; skipping Zig checks.")
        return
    for root, _dirs, files in os.walk(ZIG_SRC_ROOT):
        for f in sorted(files):
            if not f.endswith(".zig"):
                continue
            path = os.path.join(root, f)
            if is_zig_exempt(path):
                continue
            count = count_lines(path)
            if count > ZIG_LINE_LIMIT:
                violations.append((path, count, ZIG_LINE_LIMIT, "zig"))


def scan_python(violations):
    if not os.path.isdir(PYTHON_BENCH_ROOT):
        print(f"WARNING: {PYTHON_BENCH_ROOT} not found; skipping Python checks.")
        return
    for root, _dirs, files in os.walk(PYTHON_BENCH_ROOT):
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            if is_vendored(path):
                continue
            count = count_lines(path)
            if count > PYTHON_LINE_LIMIT:
                violations.append((path, count, PYTHON_LINE_LIMIT, "python"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-python",
        action="store_true",
        help="Also check Python files in bench/ against the 1200-line limit.",
    )
    args = parser.parse_args()

    violations = []
    scan_zig(violations)
    if args.with_python:
        scan_python(violations)

    if not violations:
        msg = f"All Zig source files in {ZIG_SRC_ROOT} are within {ZIG_LINE_LIMIT} lines."
        if args.with_python:
            msg += f" All Python files in {PYTHON_BENCH_ROOT} are within {PYTHON_LINE_LIMIT} lines."
        print(msg)
        return 0

    violations.sort(key=lambda x: -x[1])
    print("File size violations:")
    for path, count, limit, lang in violations:
        print(f"  {count:5d}  {path}  (limit {limit} for {lang})")
    print(f"\n{len(violations)} violation(s) found.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
