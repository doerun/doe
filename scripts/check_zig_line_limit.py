#!/usr/bin/env python3
"""Enforce the 777-line limit for Zig runtime source files.

Scans runtime/zig/src/**/*.zig and reports any file exceeding 777 lines.
Test files (*_test.zig, test_*.zig) and type-definition files (wgpu_types.zig)
are exempt since they are data-heavy by nature.

Exit code 0 if all files pass, 1 if any violations found.
"""

import os
import sys

ZIG_SRC_ROOT = os.path.join("runtime", "zig", "src")
LINE_LIMIT = 777

EXEMPT_PATTERNS = (
    "_test.zig",
    "test_",
    "wgpu_types.zig",
)


def is_exempt(filename):
    base = os.path.basename(filename)
    return any(base.endswith(p) or base.startswith(p) for p in EXEMPT_PATTERNS)


def main():
    violations = []
    for root, _dirs, files in os.walk(ZIG_SRC_ROOT):
        for f in files:
            if not f.endswith(".zig"):
                continue
            path = os.path.join(root, f)
            if is_exempt(path):
                continue
            with open(path, "r") as fh:
                count = sum(1 for _ in fh)
            if count > LINE_LIMIT:
                violations.append((path, count))

    if not violations:
        print(f"All Zig source files in {ZIG_SRC_ROOT} are within {LINE_LIMIT} lines.")
        return 0

    violations.sort(key=lambda x: -x[1])
    print(f"Zig source files exceeding {LINE_LIMIT}-line limit:")
    for path, count in violations:
        print(f"  {count:5d}  {path}")
    print(f"\n{len(violations)} violation(s) found.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
