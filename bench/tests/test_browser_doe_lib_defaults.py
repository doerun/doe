from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SUPERSET_RUNNER = REPO_ROOT / "browser/chromium/scripts/run-browser-benchmark-superset.py"
LANE_PATHS = REPO_ROOT / "browser/chromium/scripts/lane-paths.sh"
JS_RUNNERS = (
    REPO_ROOT / "browser/chromium/scripts/webgpu-playwright-smoke.mjs",
    REPO_ROOT / "browser/chromium/scripts/webgpu-playwright-layered-bench.mjs",
    REPO_ROOT / "browser/chromium/scripts/webgpu-playwright-ort-bench.mjs",
)


def _load_superset_runner() -> Any:
    spec = importlib.util.spec_from_file_location("run_browser_benchmark_superset", SUPERSET_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {SUPERSET_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BrowserDoeLibDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_superset_runner()

    def test_python_superset_runner_prefers_full_webgpu_library(self) -> None:
        old_root = self.module.REPO_ROOT
        old_env = os.environ.pop("FAWN_DOE_LIB", None)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                lib_dir = root / "runtime/zig/zig-out/lib"
                lib_dir.mkdir(parents=True)
                preferred_ext = self.module.host_doe_lib_extension()
                full = lib_dir / f"libwebgpu_doe_full.{preferred_ext}"
                compute = lib_dir / f"libwebgpu_doe.{preferred_ext}"
                full.write_text("", encoding="utf-8")
                compute.write_text("", encoding="utf-8")
                self.module.REPO_ROOT = root

                self.assertEqual(self.module.default_doe_lib(), full)
        finally:
            self.module.REPO_ROOT = old_root
            if old_env is not None:
                os.environ["FAWN_DOE_LIB"] = old_env

    def test_shell_lane_candidates_prefer_full_webgpu_library(self) -> None:
        proc = subprocess.run(
            [
                "bash",
                "-c",
                f"source {LANE_PATHS}; fawn_default_doe_lib_candidates | head -1",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("libwebgpu_doe_full.", proc.stdout.strip())

    def test_playwright_runners_prefer_full_webgpu_library(self) -> None:
        for path in JS_RUNNERS:
            text = path.read_text(encoding="utf-8")
            full_index = text.index("libwebgpu_doe_full")
            compute_index = text.index("libwebgpu_doe.")
            self.assertLess(full_index, compute_index, str(path))

    def test_python_superset_runner_accepts_auto_without_doe_lib_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_lib = Path(tmpdir) / "missing-libwebgpu_doe_full.so"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SUPERSET_RUNNER),
                    "--mode",
                    "auto",
                    "--doe-lib",
                    str(missing_lib),
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--mode auto", completed.stdout)

    def test_shell_bench_wrapper_accepts_auto_without_doe_lib_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chrome = root / "chrome"
            missing_lib = root / "missing-libwebgpu_doe_full.so"
            chrome.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            chrome.chmod(0o755)
            completed = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "browser/chromium/scripts/run-with-lane-defaults.sh"),
                    "bench",
                    "--mode",
                    "auto",
                    "--chrome",
                    str(chrome),
                    "--doe-lib",
                    str(missing_lib),
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--mode auto", completed.stdout)


if __name__ == "__main__":
    unittest.main()
