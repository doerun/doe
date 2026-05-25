from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "native-compare"
    / "compare_doe_vs_tint_compilation.py"
)


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "compare_doe_vs_tint_compilation",
        MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCompareDoeVsTintCompilation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module()

    def test_command_version_uses_fallback_on_probe_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "tool"
            script.write_text(
                "#!/bin/sh\n"
                "echo usage >&2\n"
                "exit 2\n",
                encoding="utf-8",
            )
            script.chmod(script.stat().st_mode | 0o111)

            version = self.module.command_version([str(script)], "fallback-version")

        self.assertEqual(version, "fallback-version")

    def test_command_version_reads_first_success_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "tool"
            script.write_text(
                "#!/bin/sh\n"
                "echo tool-version\n"
                "echo detail\n",
                encoding="utf-8",
            )
            script.chmod(script.stat().st_mode | 0o111)

            version = self.module.command_version([str(script)], "fallback-version")

        self.assertEqual(version, "tool-version")

    def test_tint_warm_alias_map_includes_materialized_workload_name(self) -> None:
        aliases = self.module.build_tint_warm_alias_map(
            [
                {
                    "name": "compilation_alpha_msl",
                    "workloadId": "compilation_alpha_msl",
                    "path": "/repo/bench/kernels/alpha.wgsl",
                }
            ]
        )

        self.assertEqual(aliases["compilation_alpha_msl"], "compilation_alpha_msl")
        self.assertEqual(aliases["compilation_alpha_msl.wgsl"], "compilation_alpha_msl")
        self.assertEqual(aliases["alpha.wgsl"], "compilation_alpha_msl")

    def test_preferred_tint_warm_benchmark_name_uses_materialized_workload(self) -> None:
        name = self.module.preferred_tint_warm_benchmark_name(
            {
                "name": "compilation_alpha_msl",
                "workloadId": "compilation_alpha_msl",
                "path": "/repo/bench/kernels/alpha.wgsl",
            }
        )

        self.assertEqual(name, "compilation_alpha_msl.wgsl")

    def test_parse_google_benchmark_json_skips_warning_prefix(self) -> None:
        payload = self.module.parse_google_benchmark_json(
            "warning text\n"
            "{\n"
            "  \"benchmarks\": []\n"
            "}\n"
        )

        self.assertEqual(payload, {"benchmarks": []})

    def test_google_benchmark_filter_literal_keeps_hyphen_plain(self) -> None:
        escaped = self.module.google_benchmark_filter_literal("atan2-const-eval.wgsl")

        self.assertEqual(escaped, "atan2-const-eval\\.wgsl")


if __name__ == "__main__":
    unittest.main()
