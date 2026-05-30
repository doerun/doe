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

    def test_toolchain_info_includes_tint_warm_binary(self) -> None:
        cfg = {
            "comparison": {
                "binaryPath": "missing/tint",
                "warmBinaryPath": "missing/tint_benchmark",
            }
        }
        args = type("Args", (), {"doe_emit_binary": "missing/doe-runtime-compile-report"})()

        toolchains = self.module.build_toolchain_info(cfg, args)

        self.assertIn("tintWarm", toolchains)
        self.assertEqual(toolchains["tintWarm"]["name"], "tint-benchmark")
        self.assertEqual(toolchains["tintWarm"]["artifactSha256"], None)
        self.assertEqual(
            toolchains["tintWarm"]["command"],
            ["missing/tint_benchmark", "--benchmark_format=json"],
        )

    def test_comparability_rejects_whole_compile_only_phase_evidence(self) -> None:
        record = {
            "status": "compared",
            "comparison": {"warm": {"p50_ns": 10}},
        }
        doe_result = self.module.make_compiler_result(
            status="ok",
            diagnostic_code="",
            output_sha256="1" * 64,
            ir_sha256="2" * 64,
            validation_status="passed",
            validation_tool="validator",
            phase_total_ns=10,
            receipt_path="bench/out/scratch/doe.json",
        )
        tint_result = self.module.make_compiler_result(
            status="ok",
            diagnostic_code="",
            output_sha256="3" * 64,
            validation_status="passed",
            validation_tool="validator",
            phase_total_ns=10,
            receipt_path="bench/out/scratch/tint.json",
        )

        comparability = self.module.build_row_comparability(
            record,
            doe_result,
            tint_result,
            self.module.CLAIMABLE_REQUIRED_PHASES,
        )

        self.assertEqual(comparability["status"], "diagnostic")
        self.assertIn("doe missing phase timing: parse", comparability["reasons"])
        self.assertIn("tint missing phase timing: emit", comparability["reasons"])

    def test_compile_doe_evidence_output_reads_compile_report_phase_timings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shader_path = root / "shader.wgsl"
            shader_path.write_text(
                "@compute @workgroup_size(1)\nfn main() {}\n",
                encoding="utf-8",
            )
            script = root / "doe-runtime-compile-report"
            script.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "args = sys.argv[1:]\n"
                "emit_path = args[args.index('--emit-msl') + 1]\n"
                "out_path = args[args.index('--out') + 1]\n"
                "open(emit_path, 'w', encoding='utf-8').write('// msl\\n')\n"
                "payload = {\n"
                "  'kind': 'runtime_compile_report',\n"
                "  'phaseTimingsNs': {\n"
                "    'parse': 11,\n"
                "    'sema': 12,\n"
                "    'lower': 13,\n"
                "    'emit': 14,\n"
                "    'total': 60,\n"
                "  },\n"
                "}\n"
                "open(out_path, 'w', encoding='utf-8').write(json.dumps(payload) + '\\n')\n",
                encoding="utf-8",
            )
            script.chmod(script.stat().st_mode | 0o111)
            evidence_dir = root / "evidence"

            original_validate = self.module.validate_msl_output
            self.module.validate_msl_output = lambda _path: {
                "status": "passed",
                "tool": "test-validator",
                "reason": "",
            }
            try:
                result = self.module.compile_doe_evidence_output(
                    {
                        "name": "shader",
                        "path": str(shader_path),
                    },
                    "msl",
                    {
                        "status": "compared",
                        "baseline": {"p50_ns": 100},
                    },
                    evidence_dir,
                    str(script),
                    False,
                )
            finally:
                self.module.validate_msl_output = original_validate

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            result["phaseTimingsNs"],
            {
                "parse": 11,
                "sema": 12,
                "lower": 13,
                "emit": 14,
                "total": 60,
            },
        )


if __name__ == "__main__":
    unittest.main()
