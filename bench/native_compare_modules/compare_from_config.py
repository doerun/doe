"""Config-backed inline compare is removed; receipt-first flow is required."""

from __future__ import annotations

import sys
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    argv_list = list(argv or [])
    config_path = ""
    for index, token in enumerate(argv_list):
        if token == "--config" and index + 1 < len(argv_list):
            config_path = argv_list[index + 1]
            break
        if token.startswith("--config="):
            config_path = token.split("=", 1)[1]
            break
    print(
        "error: config-backed inline compare has been removed; "
        "run each side independently and compare receipts post-hoc.",
        file=sys.stderr,
    )
    if config_path:
        print("\nRun each side explicitly:", file=sys.stderr)
        print(
            f"  {sys.executable} bench/cli.py run-config --config {config_path} --side baseline",
            file=sys.stderr,
        )
        print(
            f"  {sys.executable} bench/cli.py run-config --config {config_path} --side comparison",
            file=sys.stderr,
        )
    print(
        "\nThen compare the emitted .run.json receipts with:\n"
        f"  {sys.executable} bench/cli.py compare <baseline.run.json> <comparison.run.json>",
        file=sys.stderr,
    )
    return 1
