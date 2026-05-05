#!/usr/bin/env python3
"""Reject newly staged files that match a `.gitignore` pattern.

A cleanup pass found tracked-but-gitignored files in the repo. The root
cause was `git add -A` style commits sweeping in generated artifacts that
`.gitignore` was supposed to keep out. This gate prevents the regression.

Behavior:

  - If invoked with no args, scans staged additions (`git diff --cached
    --name-only --diff-filter=A`).
  - If invoked with one or more paths, scans those paths instead. Used
    by CI or local audits to scan `git ls-files -i -c --exclude-standard`
    output as a full-tree check.
  - Exits 0 when no staged add matches a .gitignore pattern.
  - Exits 1 when one or more do, listing each offending path.

Install as a pre-commit hook:

    ln -sf ../../bench/tools/check_no_new_tracked_under_gitignore.py \\
       "$(git rev-parse --git-common-dir)/hooks/pre-commit"

Or wire into `bench/gates/run_blocking_gates.py` for CI enforcement.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[2]


def _detect_repo_root() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    return SCRIPT_REPO_ROOT


REPO_ROOT = _detect_repo_root()


def _run(args: list[str], check: bool = True) -> str:
    proc = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )
    return proc.stdout


def _staged_additions() -> list[str]:
    """Files newly added by the staged commit (not modified or deleted)."""
    out = _run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
    )
    return [line for line in out.splitlines() if line.strip()]


def _matches_gitignore(paths: list[str]) -> list[str]:
    """Return the subset of `paths` that match a .gitignore pattern.

    Uses `git check-ignore --no-index` so tracked files don't get the
    free pass git normally gives them (tracked overrides ignore).
    """
    if not paths:
        return []
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "--verbose", "--"] + paths,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # check-ignore exits 0 when at least one path matches, 1 when none.
    matched: list[str] = []
    for line in proc.stdout.splitlines():
        # --verbose format: <source>:<lineno>:<pattern>\t<path>
        parts = line.split("\t", 1)
        if len(parts) == 2:
            matched.append(parts[1])
    return matched


def main(argv: list[str]) -> int:
    if argv:
        paths = list(argv)
    else:
        paths = _staged_additions()

    if not paths:
        return 0

    matched = _matches_gitignore(paths)
    if not matched:
        return 0

    print(
        "ERROR: refusing to add files that match a .gitignore pattern.",
        file=sys.stderr,
    )
    print(
        "       This usually means `git add -A` swept in artifacts under",
        file=sys.stderr,
    )
    print(
        "       bench/out/ (or another ignored tree). Either remove them",
        file=sys.stderr,
    )
    print(
        "       from the index (`git restore --staged <path>`) or update",
        file=sys.stderr,
    )
    print(
        "       .gitignore if the file legitimately belongs in tree.",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    for path in matched:
        print(f"  {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
