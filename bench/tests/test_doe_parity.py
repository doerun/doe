"""Unit tests for the Doe parity harness CLI (bench/tools/doe_parity.py).

These lock the fail-closed scaffolding contract until the TSIR
reference interpreter and backend lanes land in future sessions.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import doe_parity  # noqa: E402


class TestParityScaffolding(unittest.TestCase):
    def test_valid_exactness_set_matches_rdrr_taxonomy(self) -> None:
        self.assertEqual(
            doe_parity.VALID_EXACTNESS,
            frozenset(
                {"bit_exact_solo", "algorithm_exact", "tolerance_bounded"}
            ),
        )

    def test_rejection_reasons_match_tsir_taxonomy(self) -> None:
        self.assertEqual(
            doe_parity.REJECTION_REASONS,
            frozenset(
                {
                    "tsir_subgroup_unlowerable",
                    "tsir_pe_budget_exhausted",
                    "tsir_collective_not_representable",
                    "tsir_dependence_unanalyzable",
                    "tsir_source_not_affine",
                    "tsir_target_unfit",
                }
            ),
        )

    def test_reference_interpreter_is_not_implemented(self) -> None:
        outcome = doe_parity.run_reference_interpreter("rmsnorm", "abc")
        self.assertEqual(outcome.backend, "reference")
        self.assertEqual(outcome.status, "not_implemented")

    def test_reference_interpreter_reports_rejected_tsir(self) -> None:
        outcome = doe_parity.run_reference_interpreter(
            "rmsnorm",
            "abc",
            ["tsir_collective_not_representable", "tsir_target_unfit"],
        )
        self.assertEqual(outcome.backend, "reference")
        self.assertEqual(outcome.status, "rejected")
        self.assertIn("tsir_collective_not_representable", outcome.detail or "")

    def test_backend_lanes_are_not_implemented(self) -> None:
        for backend in ("webgpu", "csl-simfabric"):
            with self.subTest(backend=backend):
                outcome = doe_parity.run_backend(backend)
                self.assertEqual(outcome.status, "not_implemented")

    def test_compare_defers_when_reference_missing(self) -> None:
        reference = doe_parity.ComparisonOutcome(
            backend="reference", status="not_implemented"
        )
        backend = doe_parity.ComparisonOutcome(
            backend="webgpu", status="not_implemented"
        )
        result = doe_parity.compare(reference, backend, "bit_exact_solo")
        self.assertEqual(result.status, "deferred")

    def test_compare_marks_backend_rejected_when_reference_rejects(self) -> None:
        reference = doe_parity.ComparisonOutcome(
            backend="reference",
            status="rejected",
            detail="TSIR rejected before execution: tsir_target_unfit",
        )
        backend = doe_parity.ComparisonOutcome(
            backend="webgpu", status="not_implemented"
        )
        result = doe_parity.compare(reference, backend, "bit_exact_solo")
        self.assertEqual(result.status, "rejected")
        self.assertIn("reference=rejected", result.detail or "")

    def test_compare_rejects_unknown_exactness_class(self) -> None:
        reference = doe_parity.ComparisonOutcome(backend="reference", status="ok")
        backend = doe_parity.ComparisonOutcome(backend="webgpu", status="ok")
        with self.assertRaises(ValueError):
            doe_parity.compare(reference, backend, "looks_good_to_me")

    def test_tolerance_bounded_refuses_without_metric_wiring(self) -> None:
        reference = doe_parity.ComparisonOutcome(
            backend="reference", status="ok", backend_hash="abc"
        )
        backend = doe_parity.ComparisonOutcome(
            backend="webgpu", status="ok", backend_hash="abc"
        )
        result = doe_parity.compare(reference, backend, "tolerance_bounded")
        self.assertEqual(result.status, "fail")
        self.assertIn("tolerance_bounded", result.detail or "")

    def test_bit_exact_pass_and_fail(self) -> None:
        ref = doe_parity.ComparisonOutcome(
            backend="reference", status="ok", backend_hash="deadbeef"
        )
        ok = doe_parity.ComparisonOutcome(
            backend="webgpu", status="ok", backend_hash="deadbeef"
        )
        self.assertEqual(
            doe_parity.compare(ref, ok, "bit_exact_solo").status, "pass"
        )
        bad = doe_parity.ComparisonOutcome(
            backend="webgpu", status="ok", backend_hash="cafef00d"
        )
        self.assertEqual(
            doe_parity.compare(ref, bad, "bit_exact_solo").status, "fail"
        )

    def test_schema_is_well_formed(self) -> None:
        schema_path = REPO_ROOT / "config" / "doe-parity-receipt.schema.json"
        parsed = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(parsed["$id"], "doe-parity-receipt.schema.json")
        self.assertIn("bit_exact_solo", parsed["properties"]["exactnessClass"]["enum"])

    def test_extract_rejection_reasons_deduplicates_and_validates(self) -> None:
        reasons = doe_parity.extract_rejection_reasons(
            {
                "rejections": [
                    {"reason": "tsir_target_unfit"},
                    {"reason": "tsir_target_unfit"},
                ]
            },
            {
                "rejections": [
                    {"reason": "tsir_collective_not_representable"},
                ]
            },
        )
        self.assertEqual(
            reasons,
            ["tsir_target_unfit", "tsir_collective_not_representable"],
        )

    def test_extract_rejection_reasons_rejects_unknown_reason(self) -> None:
        with self.assertRaises(ValueError):
            doe_parity.extract_rejection_reasons(
                {"rejections": [{"reason": "looks_fine"}]},
                {"rejections": []},
            )


if __name__ == "__main__":
    unittest.main()
