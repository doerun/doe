#!/usr/bin/env python3
"""Verify csl_sdk_driver.classify_cslc_failure maps known cslc v1.4 stderr
patterns to the right taxonomy codes.

Each test case is a real stderr fragment we have first-party evidence for
(either observed while bringing up the 270M lane on SDK v1.4 or stated
verbatim in the SDK 1.4 release notes / canonical examples). Unknown
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
    check_unblock_cmd_stream,
    classify_cslc_failure,
    materialize_command,
    redact_command_for_receipt,
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


if __name__ == "__main__":
    unittest.main()
