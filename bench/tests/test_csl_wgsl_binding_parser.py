#!/usr/bin/env python3
"""Verify parse_wgsl_storage_bindings extracts storage-binding access modes.

Each test stages a minimal WGSL source and asserts the parser returns the
right `{name: access_mode}` map. This locks in the regex so future changes
don't silently break input/output role inference in the operation graph.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "runtime" / "zig" / "tools"))

from csl_sdk_driver import parse_wgsl_storage_bindings  # type: ignore[import-not-found]


def _write_wgsl(src: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".wgsl", delete=False
    )
    f.write(src)
    f.close()
    return Path(f.name)


class ParseWgslStorageBindingsTests(unittest.TestCase):
    def test_read_mode_default(self) -> None:
        """`var<storage>` without an explicit access mode defaults to `read`."""
        path = _write_wgsl(
            "@group(0) @binding(0) var<storage> input: array<f32>;\n"
        )
        self.assertEqual(parse_wgsl_storage_bindings(path), {"input": "read"})

    def test_explicit_read(self) -> None:
        path = _write_wgsl(
            "@group(0) @binding(0) var<storage, read> input: array<f32>;\n"
        )
        self.assertEqual(parse_wgsl_storage_bindings(path), {"input": "read"})

    def test_read_write(self) -> None:
        path = _write_wgsl(
            "@group(0) @binding(0) var<storage, read_write> buf: array<f32>;\n"
        )
        self.assertEqual(parse_wgsl_storage_bindings(path), {"buf": "read_write"})

    def test_write_only(self) -> None:
        path = _write_wgsl(
            "@group(0) @binding(0) var<storage, write> output: array<f32>;\n"
        )
        self.assertEqual(parse_wgsl_storage_bindings(path), {"output": "write"})

    def test_multiple_bindings_mixed_access(self) -> None:
        path = _write_wgsl(
            "@group(0) @binding(0) var<storage, read> a: array<f32>;\n"
            "@group(0) @binding(1) var<storage, read> b: array<f32>;\n"
            "@group(0) @binding(2) var<storage, read_write> out: array<f32>;\n"
        )
        self.assertEqual(
            parse_wgsl_storage_bindings(path),
            {"a": "read", "b": "read", "out": "read_write"},
        )

    def test_ignores_uniform_and_workgroup(self) -> None:
        """The parser targets storage-buffer bindings only; uniform and
        workgroup vars are not storage-binding candidates for role inference."""
        path = _write_wgsl(
            "@group(0) @binding(0) var<uniform> u: SomeStruct;\n"
            "@group(0) @binding(1) var<storage, read_write> out: array<f32>;\n"
            "var<workgroup> shared: array<f32, 64>;\n"
        )
        self.assertEqual(parse_wgsl_storage_bindings(path), {"out": "read_write"})

    def test_whitespace_and_formatting_variations(self) -> None:
        """WGSL formatting varies — extra spaces, tabs, split lines inside
        attribute args. The regex must accept these."""
        path = _write_wgsl(
            "@group( 0 )   @binding( 3 )\n"
            "var  <  storage  ,  read_write  >  buf : array<f32>;\n"
        )
        self.assertEqual(parse_wgsl_storage_bindings(path), {"buf": "read_write"})

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(
            parse_wgsl_storage_bindings(Path("/nonexistent/foo.wgsl")),
            {},
        )


if __name__ == "__main__":
    unittest.main()
