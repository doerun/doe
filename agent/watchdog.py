#!/usr/bin/env python3
"""
Fawn watchdog MVP.

Parses a source text for toggle mentions and emits normalized quirk candidates.
This is intentionally minimal and deterministic for v0 scaffolding.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


TOGGLE_RE = re.compile(r"Toggle::([A-Za-z0-9_]+)")
DEFAULT_OBSERVED_AT = "1970-01-01T00:00:00Z"


def build_candidate(
    toggle: str,
    source_repo: str,
    source_path: str,
    source_commit: str,
    vendor: str,
    api: str,
    observed_at: str,
) -> dict:
    return {
        "schemaVersion": 1,
        "quirkId": f"auto.{toggle.lower()}",
        "scope": "driver_toggle",
        "match": {"vendor": vendor, "api": api},
        "action": {"kind": "toggle", "params": {"toggle": toggle}},
        "safetyClass": "moderate",
        "verificationMode": "guard_only",
        "proofLevel": "guarded",
        "provenance": {
            "sourceRepo": source_repo,
            "sourcePath": source_path,
            "sourceCommit": source_commit,
            "observedAt": observed_at,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to source text to scan")
    parser.add_argument("--output", required=True, help="Path to write candidate JSON array")
    parser.add_argument("--source-repo", default="unknown")
    parser.add_argument("--source-path", default="unknown")
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--vendor", default="unknown")
    parser.add_argument(
        "--observed-at",
        default=DEFAULT_OBSERVED_AT,
        help="RFC3339 timestamp to store in provenance (default is deterministic).",
    )
    parser.add_argument(
        "--api",
        default="webgpu",
        choices=["vulkan", "metal", "d3d12", "webgpu"],
    )
    args = parser.parse_args()

    text = Path(args.input).read_text(encoding="utf-8")
    toggles = sorted(set(TOGGLE_RE.findall(text)))
    candidates = [
        build_candidate(
            t,
            args.source_repo,
            args.source_path,
            args.source_commit,
            args.vendor,
            args.api,
            args.observed_at,
        )
        for t in toggles
    ]
    Path(args.output).write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
