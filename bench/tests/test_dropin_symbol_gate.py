#!/usr/bin/env python3
"""Regression tests for drop-in symbol extraction."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "bench" / "drop-in" / "dropin_symbol_gate.py"

_SPEC = importlib.util.spec_from_file_location("dropin_symbol_gate", MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
dropin_symbol_gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dropin_symbol_gate)


class DropinSymbolGateTests(unittest.TestCase):
    def test_extract_symbols_from_output_accepts_macos_nm_symbols(self) -> None:
        output = "_wgpuAdapterRequestDevice\n_wgpuQueueWriteBuffer\n"
        symbols = dropin_symbol_gate.extract_symbols_from_output(output)
        self.assertEqual(symbols, {"wgpuAdapterRequestDevice", "wgpuQueueWriteBuffer"})

    def test_extract_symbols_from_output_accepts_linux_nm_table_rows(self) -> None:
        output = "0000000000000f18 T wgpuAdapterRequestDevice\n0000000000001010 T wgpuQueueWriteBuffer\n"
        symbols = dropin_symbol_gate.extract_symbols_from_output(output)
        self.assertEqual(symbols, {"wgpuAdapterRequestDevice", "wgpuQueueWriteBuffer"})

    def test_tool_candidates_use_dylib_friendly_nm_flags_on_macos(self) -> None:
        candidates = dropin_symbol_gate.tool_candidates_for_artifact(
            Path("/tmp/libwebgpu_doe.dylib"),
            platform_name="darwin",
        )
        self.assertEqual(candidates[0][:2], ["nm", "-gUj"])
        self.assertEqual(candidates[1][:2], ["nm", "-gU"])


if __name__ == "__main__":
    unittest.main()
