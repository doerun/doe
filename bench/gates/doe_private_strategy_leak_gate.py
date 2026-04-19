#!/usr/bin/env python3
"""Fail the build if public Doe docs leak references to private strategy.

Doe's public docs describe what the code does, what the contracts are, and
what measurable artifact state is. Private strategy — GTM, outreach, named
prospects, competitive framing ("moat", "dominance"), cross-repo integration
plans — lives in the Ouroboros repo. Public Doe docs must not link into
`ouroboros/**` paths or adopt competitive framing, because:

  1. Public readers can't resolve those paths.
  2. Leaked prospect names and outreach timing harm commercial relationships.
  3. Competitive framing in a public engineering repo invites scrutiny that
     product-side messaging (owned by Ouroboros) is better positioned for.

The gate scans every tracked text file and fails on any forbidden pattern.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".py",
    ".zig",
    ".csl",
    ".wgsl",
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
}

# Paths whose contents are skipped — vendor trees, browser embed, node_modules.
SKIP_PREFIXES: tuple[str, ...] = (
    "browser/chromium/src/",
    "browser/chromium/node_modules/",
    "browser/chromium/depot_tools/",
    "node_modules/",
    "packages/doe-gpu/node_modules/",
    "demos/gaussian-splat-viewer/data/",
    # The gate and its own doc are allowed to name the rule they enforce.
    "bench/gates/doe_private_strategy_leak_gate.py",
    "docs/licensing.md",
)


@dataclass(frozen=True)
class Rule:
    label: str
    pattern: re.Pattern[bytes]


# Patterns that indicate a leak into Doe's public surface.
RULES: list[Rule] = [
    Rule(
        "cross-repo path reference to ouroboros/",
        re.compile(rb"\bouroboros/"),
    ),
    Rule(
        "competitive framing token 'moat'",
        re.compile(rb"\bmoat(?:s|ed|ing)?\b", re.IGNORECASE),
    ),
    Rule(
        "competitive framing phrase 'infrastructure dominance'",
        re.compile(rb"infrastructure[- ]dominance", re.IGNORECASE),
    ),
    Rule(
        "GTM framing 'go-to-market'",
        re.compile(rb"go[- ]to[- ]market", re.IGNORECASE),
    ),
    Rule(
        "outreach framing 'pilot outreach'",
        re.compile(rb"pilot[- ]outreach", re.IGNORECASE),
    ),
]


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def is_text_path(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_SUFFIXES


def is_skipped(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in SKIP_PREFIXES)


def scan(path: str) -> list[tuple[str, int, str]]:
    full = REPO_ROOT / path
    try:
        data = full.read_bytes()
    except OSError:
        return []
    hits: list[tuple[str, int, str]] = []
    for rule in RULES:
        for match in rule.pattern.finditer(data):
            line_no = data.count(b"\n", 0, match.start()) + 1
            snippet = match.group(0).decode("utf-8", "replace")
            hits.append((rule.label, line_no, snippet))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Print every violation. Default shows first 40 then counts.",
    )
    args = parser.parse_args()

    violations: list[tuple[str, str, int, str]] = []
    for path in tracked_files():
        if not is_text_path(path) or is_skipped(path):
            continue
        for label, line_no, snippet in scan(path):
            violations.append((path, label, line_no, snippet))

    if not violations:
        print("doe_private_strategy_leak_gate: PASS")
        return 0

    print("doe_private_strategy_leak_gate: FAIL", file=sys.stderr)
    shown = violations if args.show_all else violations[:40]
    for path, label, line_no, snippet in shown:
        print(f"  {path}:{line_no}  {label}  ({snippet!r})", file=sys.stderr)
    if not args.show_all and len(violations) > len(shown):
        print(
            f"  ... and {len(violations) - len(shown)} more. Use --show-all.",
            file=sys.stderr,
        )
    print(f"\n{len(violations)} violation(s). Private strategy belongs in the Ouroboros repo.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
