from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.predict_simfabric_wallclock import (  # noqa: E402
    SizeExprError,
    evaluate_size_expr,
    output_bytes_for_target,
    predict_wallclock,
)


class EvaluateSizeExprTest(unittest.TestCase):
    def test_literal(self) -> None:
        self.assertEqual(evaluate_size_expr("16", {}), 16)

    def test_identifier(self) -> None:
        self.assertEqual(evaluate_size_expr("hidden_per_pe", {"hidden_per_pe": 22}), 22)

    def test_multiplication(self) -> None:
        self.assertEqual(
            evaluate_size_expr(
                "rows_per_pe * hidden_per_pe",
                {"rows_per_pe": 5, "hidden_per_pe": 22},
            ),
            110,
        )

    def test_addition_and_precedence(self) -> None:
        self.assertEqual(
            evaluate_size_expr(
                "a + b * c", {"a": 1, "b": 2, "c": 3}
            ),
            7,
        )

    def test_parens(self) -> None:
        self.assertEqual(
            evaluate_size_expr(
                "(a + b) * c", {"a": 1, "b": 2, "c": 3}
            ),
            9,
        )

    def test_at_as_cast_passthrough(self) -> None:
        self.assertEqual(
            evaluate_size_expr(
                "@as(u32, hidden) * @as(u32, tokens)",
                {"hidden": 4, "tokens": 8},
            ),
            32,
        )

    def test_unknown_identifier_raises(self) -> None:
        with self.assertRaises(SizeExprError):
            evaluate_size_expr("ghost", {})

    def test_division(self) -> None:
        self.assertEqual(
            evaluate_size_expr("hidden / 2", {"hidden": 1024}),
            512,
        )

    def test_division_by_zero_raises(self) -> None:
        with self.assertRaises(SizeExprError):
            evaluate_size_expr("a / 0", {"a": 1})

    def test_unrecognized_character_raises(self) -> None:
        with self.assertRaises(SizeExprError):
            evaluate_size_expr("a $ b", {"a": 1, "b": 2})


class OutputBytesTest(unittest.TestCase):
    def test_picks_output_symbols_only(self) -> None:
        metadata = {
            "exports": [
                {
                    "symbol": "indices",
                    "sizeExpr": "16",
                    "elemType": "u32",
                },
                {
                    "symbol": "table",
                    "sizeExpr": "5 * 22",
                    "elemType": "f32",
                },
                {
                    "symbol": "output",
                    "sizeExpr": "tokens * hidden",
                    "elemType": "f32",
                },
            ]
        }
        out_bytes = output_bytes_for_target(
            metadata, {"tokens": 16, "hidden": 22}
        )
        self.assertEqual(out_bytes, 16 * 22 * 4)

    def test_unknown_size_expr_skipped(self) -> None:
        metadata = {
            "exports": [
                {
                    "symbol": "output",
                    "sizeExpr": "ghost",
                    "elemType": "f32",
                }
            ]
        }
        out_bytes = output_bytes_for_target(metadata, {})
        self.assertEqual(out_bytes, 0)

    def test_picks_kv_cache_symbols(self) -> None:
        metadata = {
            "exports": [
                {
                    "symbol": "key_cache",
                    "sizeExpr": "kv_len * head_dim",
                    "elemType": "f16",
                },
                {
                    "symbol": "value_cache",
                    "sizeExpr": "kv_len * head_dim",
                    "elemType": "f16",
                },
            ]
        }
        out_bytes = output_bytes_for_target(
            metadata, {"kv_len": 64, "head_dim": 256}
        )
        self.assertEqual(out_bytes, 2 * 64 * 256 * 2)

    def test_picks_manifest_shape_matmul_and_sample_outputs(self) -> None:
        metadata = {
            "exports": [
                {"symbol": "a", "sizeExpr": "m * k", "elemType": "f32"},
                {"symbol": "b", "sizeExpr": "k * n", "elemType": "f32"},
                {"symbol": "c", "sizeExpr": "m * n", "elemType": "f32"},
                {"symbol": "tokens", "sizeExpr": "1", "elemType": "u32"},
                {"symbol": "val_cache", "sizeExpr": "kv * h", "elemType": "f16"},
            ]
        }
        out_bytes = output_bytes_for_target(
            metadata, {"m": 2, "n": 3, "k": 4, "kv": 5, "h": 6}
        )
        self.assertEqual(out_bytes, (2 * 3 * 4) + 4 + (5 * 6 * 2))


def _write_target(
    compile_root: Path,
    name: str,
    *,
    output_size_expr: str = "tokens * hidden",
    output_dtype: str = "f32",
) -> None:
    target_dir = compile_root / name
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "variables": [],
        "pointers": [],
        "exports": [
            {
                "symbol": "output",
                "sizeExpr": output_size_expr,
                "elemType": output_dtype,
            }
        ],
        "compileTimeConstants": [],
    }
    (target_dir / "pe_program.metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


class PredictWallclockTest(unittest.TestCase):
    def _build_host_plan(self) -> dict:
        return {
            "schemaVersion": 1,
            "artifactKind": "doe_csl_host_plan_v1",
            "target": "wse3",
            "compileTargets": [
                {
                    "name": "embed",
                    "layout": "compile/embed/layout.csl",
                    "peProgram": "compile/embed/pe_program.csl",
                    "compileParams": {
                        "width": 246,
                        "height": 236,
                        "tokens": 16,
                        "hidden": 22,
                    },
                },
                {
                    "name": "rmsnorm",
                    "layout": "compile/rmsnorm/layout.csl",
                    "peProgram": "compile/rmsnorm/pe_program.csl",
                    "compileParams": {
                        "width": 246,
                        "height": 236,
                        "tokens": 16,
                        "hidden": 22,
                    },
                },
            ],
            "hostPlan": {
                "peGrid": {"width": 246, "height": 236},
                "kernels": [
                    {"name": "embed", "pattern": "gather", "count": 1},
                    {
                        "name": "rmsnorm",
                        "pattern": "reduction",
                        "count": 1,
                    },
                ],
                "phases": {
                    "prefill": [
                        {"kernelName": "embed", "repeat": 1},
                        {"kernelName": "rmsnorm", "repeat": 2},
                    ],
                    "decode": [
                        {"kernelName": "rmsnorm", "repeat": 1},
                    ],
                },
            },
        }

    def test_uncalibrated_run_emits_null_predicted(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            compile_root = Path(scratch) / "compile"
            _write_target(compile_root, "embed")
            _write_target(compile_root, "rmsnorm")
            host_plan = self._build_host_plan()
            receipt = predict_wallclock(host_plan, compile_root, throughput=None)
            self.assertFalse(receipt["calibrated"])
            self.assertIsNone(receipt["bytesPerCycle"])
            self.assertEqual(len(receipt["perKernel"]), 2)
            self.assertEqual(
                receipt["perKernel"][0]["outputBytesPerCall"], 16 * 22 * 4
            )
            self.assertIsNone(
                receipt["phaseTotals"]["prefill"]["predictedCycles"]
            )
            self.assertIsNone(receipt["grandPredictedCycles"])

    def test_calibrated_run_fills_predicted_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            compile_root = Path(scratch) / "compile"
            _write_target(compile_root, "embed")
            _write_target(compile_root, "rmsnorm")
            host_plan = self._build_host_plan()
            throughput = {
                "bytesPerCycle": 8.0,
                "perPatternCyclesPerCall": {
                    "gather": 100.0,
                    "reduction": 200.0,
                },
            }
            receipt = predict_wallclock(host_plan, compile_root, throughput=throughput)
            self.assertTrue(receipt["calibrated"])
            prefill = receipt["phaseTotals"]["prefill"]
            # embed: 1 call * 16 * 22 * 4 bytes = 1408
            # rmsnorm: 2 calls * 16 * 22 * 4 = 2816
            self.assertEqual(prefill["totalOutputBytes"], 1408 + 2816)
            self.assertEqual(prefill["totalCycles"], 100 + 400)
            self.assertGreaterEqual(
                prefill["predictedCycles"], prefill["totalCycles"]
            )
            self.assertGreater(
                receipt["grandPredictedCycles"], 0
            )

    def test_phase_call_count_aggregation(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            compile_root = Path(scratch) / "compile"
            _write_target(compile_root, "embed")
            _write_target(compile_root, "rmsnorm")
            host_plan = self._build_host_plan()
            receipt = predict_wallclock(host_plan, compile_root, throughput=None)
            prefill = receipt["phaseTotals"]["prefill"]
            self.assertEqual(prefill["perKernelCalls"]["embed"], 1)
            self.assertEqual(prefill["perKernelCalls"]["rmsnorm"], 2)
            decode = receipt["phaseTotals"]["decode"]
            self.assertEqual(decode["perKernelCalls"]["rmsnorm"], 1)

    def test_missing_metadata_recorded_as_issue(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            compile_root = Path(scratch) / "compile"
            _write_target(compile_root, "embed")
            host_plan = self._build_host_plan()
            receipt = predict_wallclock(host_plan, compile_root, throughput=None)
            self.assertTrue(
                any("rmsnorm" in i for i in receipt["issues"])
            )
            kernel_names = {r["name"] for r in receipt["perKernel"]}
            self.assertNotIn("rmsnorm", kernel_names)

    def test_phase_repeat_is_the_call_count(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            compile_root = Path(scratch) / "compile"
            _write_target(compile_root, "rmsnorm")
            host_plan = {
                "compileTargets": [
                    {
                        "name": "rmsnorm",
                        "compileParams": {
                            "width": 1,
                            "height": 1,
                            "tokens": 1,
                            "hidden": 1,
                        },
                    }
                ],
                "hostPlan": {
                    "kernels": [
                        {
                            "name": "rmsnorm",
                            "pattern": "reduction",
                            "count": 3,
                        }
                    ],
                    "phases": {
                        "prefill": [
                            {"kernelName": "rmsnorm", "repeat": 2}
                        ]
                    },
                },
            }
            receipt = predict_wallclock(host_plan, compile_root, throughput=None)
            self.assertEqual(
                receipt["phaseTotals"]["prefill"]["perKernelCalls"][
                    "rmsnorm"
                ],
                2,
            )


if __name__ == "__main__":
    unittest.main()
