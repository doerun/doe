#!/usr/bin/env python3
"""Tests for Apple Metal host preflight helper checks."""

from __future__ import annotations

import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "bench" / "runners" / "preflight_metal_host.py"


def load_module():
    spec = importlib.util.spec_from_file_location("preflight_metal_host", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load preflight_metal_host from {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MetalHostPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_check_file_rejects_missing_file(self) -> None:
        ok, message = self.module.check_file(Path("/tmp/doe-missing-metal-preflight-file"))
        self.assertFalse(ok)
        self.assertIn("missing file", message)

    def test_check_file_rejects_non_executable_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime"
            path.write_text("#!/bin/sh\n", encoding="utf-8")
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            ok, message = self.module.check_file(path, executable=True)
        self.assertFalse(ok)
        self.assertIn("not executable", message)

    def test_check_file_accepts_executable_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime"
            path.write_text("#!/bin/sh\n", encoding="utf-8")
            path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            ok, message = self.module.check_file(path, executable=True)
        self.assertTrue(ok, message)

    def test_check_dawn_library_exports_rejects_missing_file(self) -> None:
        ok, message = self.module.check_dawn_library_exports(
            Path("/tmp/doe-missing-libwebgpu-dawn.dylib")
        )
        self.assertFalse(ok)
        self.assertIn("missing file", message)

    def test_default_dawn_library_has_required_exports_when_present(self) -> None:
        path = self.module.DEFAULT_DAWN_LIBRARY_PATH
        if not path.is_file() or os.environ.get("DOE_SKIP_LOCAL_DAWN_EXPORT_TEST") == "1":
            self.skipTest(f"local Dawn library unavailable: {path}")
        ok, message = self.module.check_dawn_library_exports(path)
        self.assertTrue(ok, message)


if __name__ == "__main__":
    unittest.main()
