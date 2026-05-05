#!/usr/bin/env python3
"""Verify csl_sdk_driver.classify_cslc_failure maps known cslc stderr
patterns to the right taxonomy codes.

Each test case is a real stderr fragment we have first-party evidence for
(either observed while bringing up the 270M lane or stated
verbatim in SDK release notes / canonical examples). Unknown
patterns are expected to fall through to `csl_compile_unclassified` so
the stderr log stays the evidence of record.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "runtime" / "zig" / "tools"))

from csl_sdk_driver import (  # type: ignore[import-not-found]
    ROW_KERNEL_TARGETS,
    check_unblock_cmd_stream,
    classify_cslc_failure,
    compile_targets,
    materialize_command,
    redact_command_for_receipt,
    run_command,
)


def _with_stderr(stderr_text: str) -> str:
    """Write stderr_text to a temp file and return the path; used so the
    classifier sees the exact payload it would see from a real cslc run."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".stderr.log", delete=False
    )
    tmp.write(stderr_text)
    tmp.close()
    return tmp.name


class ClassifyCslcFailureTests(unittest.TestCase):
    def test_deprecated_cselfrunner(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "RuntimeError: n_channels=0 corresponds to the deprecated runtime CSELFRunner\n"
                "Please use n_channels>0 with SdkRuntime\n"
            )
        )
        self.assertEqual(code, "csl_compile_deprecated_cselfrunner")

    def test_fabric_offsets_required(self) -> None:
        code = classify_cslc_failure(
            _with_stderr("RuntimeError: The core must have --fabric-offsets=4+width_west_buf,1\n")
        )
        self.assertEqual(code, "csl_compile_fabric_offsets_required")

    def test_uninitialized_param(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "layout.csl:4:1: error: only 'var' and 'extern const' variables may be uninitialized\n"
                "param width: i16;\n"
            )
        )
        self.assertEqual(code, "csl_compile_uninitialized_param")

    def test_export_type_mismatch(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:42:20: error: exported symbol type mismatch. Expected type: '[*]u32', got '[*]f32'\n"
            )
        )
        self.assertEqual(code, "csl_compile_export_type_mismatch")

    def test_undeclared_identifier(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:41:20: error: use of undeclared identifier\n"
                "    @export_symbol(u_ptr, \"u\");\n"
            )
        )
        self.assertEqual(code, "csl_compile_undeclared_identifier")

    def test_layout_undeclared_symbol(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:115:5: error: name 'A' was not declared during layout evaluation\n"
                "    @export_symbol(A_ptr, \"A\");\n"
            )
        )
        self.assertEqual(code, "csl_compile_undeclared_identifier")

    def test_builtin_shadow(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:28:13: error: declaration shadows builtin type\n"
                "            const i0 = @as(u32, p) * 2;\n"
            )
        )
        self.assertEqual(code, "csl_compile_builtin_shadow")

    def test_color_config_conflict(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:108:5: error: config for this color has already been set\n"
                "    @set_local_color_config(reduce_color, .{ .recv_task = reduce_task_id });\n"
            )
        )
        self.assertEqual(code, "csl_compile_color_config_conflict")

    def test_pe_memory_exhausted(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "ld.lld: error: ran out of PE memory for task table\n"
                "ld.lld: error: ran out of PE memory for data (section .data.hi)\n"
            )
        )
        self.assertEqual(code, "csl_compile_pe_memory_exhausted")

    def test_type_mismatch(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:22:39: error: expected type 'u32', got: 'i16'\n"
            )
        )
        self.assertEqual(code, "csl_compile_type_mismatch")

    def test_f16_fmacs_unsupported(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:91:13: error: operand types do not match expectations\n"
                "            @fmacs(C_dsd, C_dsd, A_dsd, b_val);\n"
                "pe_program.csl:91:13: note: got type(s): mem1d_dsd, mem1d_dsd, mem1d_dsd, f16\n"
                "pe_program.csl:91:13: note:     expected type(s): DSD/DSR, DSD/DSR, DSD/DSR, f32\n"
            )
        )
        self.assertEqual(code, "csl_compile_f16_fmacs_unsupported")

    def test_f16_reduce_fadds_unsupported(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:64:47: error: expected type '[*]f32', got: '[*]f16'\n"
                "    mpi_x.reduce_fadds(@as(u16, num_pes - 1), @ptrcast([*]f16, &partial), @ptrcast([*]f16, &output), @as(u16, out_dim_per_pe), reduce_done_id);\n"
            )
        )
        self.assertEqual(code, "csl_compile_f16_reduce_fadds_unsupported")

    def test_f16_literal_overflow(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:23:26: error: cast from 'comptime_float' to 'f16' failed\n"
                "var local_max_val: f16 = -3.4028235e+38;\n"
                "pe_program.csl:23:26: note: operand overflowed precision of 'f16'\n"
            )
        )
        self.assertEqual(code, "csl_compile_f16_literal_overflow")

    def test_f16_bitcast_width_mismatch(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:75:56: error: expected equal bit width for operands, got: 16 and 32 bit(s)\n"
                "        const inv_rms: f16 = (1.0 / sqrt_nr((mean_sq + @bitcast(f16, u[1]))));\n"
            )
        )
        self.assertEqual(code, "csl_compile_f16_bitcast_width_mismatch")

    def test_arity_mismatch(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:22:16: error: function expects 2 arguments, 3 provided\n"
            )
        )
        self.assertEqual(code, "csl_compile_arity_mismatch")

    def test_parser_reject(self) -> None:
        code = classify_cslc_failure(
            _with_stderr(
                "pe_program.csl:13:29: error: Unexpected character at this location\n"
                "var matrixData: [chunk_size][4]f32 = @zeros([chunk_size][4]f32);\n"
            )
        )
        self.assertEqual(code, "csl_compile_parser_reject")

    def test_sandbox_runtime_missing(self) -> None:
        code = classify_cslc_failure(
            _with_stderr("[ERROR] singularity not in $PATH\n")
        )
        self.assertEqual(code, "csl_compile_sandbox_runtime_missing")

    def test_unknown_pattern_falls_through(self) -> None:
        code = classify_cslc_failure(
            _with_stderr("some new v1.5 error message we haven't seen\n")
        )
        self.assertEqual(code, "csl_compile_unclassified")

    def test_missing_stderr_falls_through(self) -> None:
        code = classify_cslc_failure("/nonexistent/path/stderr.log")
        self.assertEqual(code, "csl_compile_unclassified")


class CheckUnblockCmdStreamTests(unittest.TestCase):
    def test_unblock_present_in_compute(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csl", delete=False
        ) as f:
            f.write(
                "fn compute() void {\n"
                "    outData[0] = 1.0;\n"
                "    sys_mod.unblock_cmd_stream();\n"
                "}\n"
            )
            path = Path(f.name)
        self.assertEqual(check_unblock_cmd_stream(path, "compute"), "unblock_present")

    def test_unblock_missing(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csl", delete=False
        ) as f:
            f.write(
                "fn compute() void {\n"
                "    outData[0] = 1.0;\n"
                "    // forgot unblock — host memcpy queue will hang\n"
                "}\n"
            )
            path = Path(f.name)
        self.assertEqual(check_unblock_cmd_stream(path, "compute"), "unblock_missing")

    def test_unblock_unknown_when_fn_absent(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csl", delete=False
        ) as f:
            f.write("// no compute fn declared\n")
            path = Path(f.name)
        self.assertEqual(check_unblock_cmd_stream(path, "compute"), "unblock_unknown")


class RuntimeCommandReceiptTests(unittest.TestCase):
    def test_empty_cmaddr_arg_is_removed(self) -> None:
        command = materialize_command(
            ["cs_python", "run.py", "--name", "{compile_output_dir}", "{cmaddr_arg}"],
            {
                "compile_output_dir": "out",
                "cmaddr_arg": "",
            },
        )
        self.assertEqual(command, ["cs_python", "run.py", "--name", "out"])

    def test_cmaddr_arg_is_rendered_when_present(self) -> None:
        command = materialize_command(
            ["cs_python", "run.py", "--name", "{compile_output_dir}", "{cmaddr_arg}"],
            {
                "compile_output_dir": "out",
                "cmaddr_arg": "--cmaddr=10.1.2.3:9000",
            },
        )
        self.assertEqual(
            command,
            ["cs_python", "run.py", "--name", "out", "--cmaddr=10.1.2.3:9000"],
        )

    def test_cmaddr_is_redacted_from_persisted_receipt_command(self) -> None:
        command = [
            "cs_python",
            "run.py",
            "--name",
            "out",
            "--cmaddr=10.1.2.3:9000",
        ]
        self.assertEqual(
            redact_command_for_receipt(command, "10.1.2.3:9000"),
            ["cs_python", "run.py", "--name", "out", "--cmaddr=$DOE_CSL_CMADDR"],
        )

    def test_run_command_records_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            return_code, stdout_path, stderr_path, timed_out = run_command(
                [
                    sys.executable,
                    "-c",
                    "import time; print('started', flush=True); time.sleep(5)",
                ],
                root / "stdout.log",
                root / "stderr.log",
                timeout_seconds=1,
            )
            self.assertEqual(return_code, 124)
            self.assertTrue(timed_out)
            self.assertIn("started", Path(stdout_path).read_text(encoding="utf-8"))
            self.assertIn(
                "DOE command timed out after 1 seconds",
                Path(stderr_path).read_text(encoding="utf-8"),
            )


class CompileTargetBlockerTests(unittest.TestCase):
    def test_phase_rmsnorm_targets_compile_as_row_kernels(self) -> None:
        self.assertIn("rmsnorm_prefill", ROW_KERNEL_TARGETS)
        self.assertIn("rmsnorm_decode", ROW_KERNEL_TARGETS)

    def test_31b_q4_aliases_are_row_kernels(self) -> None:
        self.assertIn("q4_widetile", ROW_KERNEL_TARGETS)
        self.assertIn("q4_decode_gemv", ROW_KERNEL_TARGETS)

    def test_lm_head_gemv_keeps_2d_compile_geometry(self) -> None:
        self.assertNotIn("lm_head_gemv", ROW_KERNEL_TARGETS)

    def test_compile_blocked_reason_skips_cslc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "simulator-plan.json"
            plan = {
                "target": "wse3",
                "inputs": {
                    "compileRootPath": "compile",
                    "compileTargets": [
                        {
                            "name": "embed",
                            "layout": "embed/layout.csl",
                            "peProgram": "embed/pe_program.csl",
                            "compileBlockedReason": (
                                "csl_compile_params_infeasible_embed_grid_budget"
                            ),
                            "compileParams": {
                                "height": 127,
                                "hidden_size": 1536,
                                "num_tokens": 23,
                                "rows_per_pe": 16,
                            },
                        }
                    ],
                },
                "runtime": {
                    "peGrid": {"width": 130, "height": 127},
                },
            }

            summary, targets, _paths = compile_targets(
                plan_path=plan_path,
                plan=plan,
                cslc_executable="/bin/false",
            )

        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(
            summary["reason"],
            "csl_compile_params_infeasible_embed_grid_budget",
        )
        self.assertEqual(targets[0]["status"], "blocked")
        self.assertEqual(
            targets[0]["reason"],
            "csl_compile_params_infeasible_embed_grid_budget",
        )


if __name__ == "__main__":
    unittest.main()
