"""Compatibility wrapper for removed config-backed inline compare."""

from __future__ import annotations

from typing import Sequence

from native_compare_modules import compare_from_config as compare_from_config_mod


def main(argv: Sequence[str] | None = None) -> int:
    return compare_from_config_mod.main(argv)
