"""Regenerate or check the implementation-peer registry's documentation view."""

from __future__ import annotations

import argparse

from bench.lib.implementation_peers import (
    DOC_PATH, REPO_ROOT, load_peers, render_peers, validate_peer_document,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on drift.")
    args = parser.parse_args()
    if args.check:
        failures = validate_peer_document()
        if failures:
            print("\n".join(failures))
            return 1
    else:
        (REPO_ROOT / DOC_PATH).write_text(
            render_peers(load_peers()), encoding="utf-8",
        )
    print(f"PASS: {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
