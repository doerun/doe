from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.check_simfabric_budget_gate import (  # noqa: E402
    BOOTSTRAP_TOKEN,
    build_decision_receipt,
    evaluate,
)


CALIBRATION_HASH = "0" * 64


def _ceiling(
    *,
    calibration_status: str = CALIBRATION_HASH,
    grand: int = 1_000_000,
    per_phase: dict[str, int] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "schemaVersion": 1,
        "artifactKind": "doe_simfabric_wallclock_ceiling",
        "calibrationStatus": calibration_status,
        "ceilings": {
            "grandPredictedCycles": grand,
        },
    }
    if per_phase is not None:
        body["ceilings"] = {
            "grandPredictedCycles": grand,
            "perPhase": per_phase,
        }
    return body


def _budget(
    *,
    calibrated: bool = True,
    grand: int = 100,
    phase_totals: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_simfabric_wallclock_budget",
        "calibrated": calibrated,
        "grandPredictedCycles": grand,
        "phaseTotals": phase_totals or {},
    }


class EvaluateTest(unittest.TestCase):
    def test_allow_when_calibrated_and_under_ceiling(self) -> None:
        allow, schema_errors, reasons = evaluate(
            _budget(grand=100), _ceiling(grand=1000)
        )
        self.assertTrue(allow)
        self.assertEqual(schema_errors, [])
        self.assertEqual(reasons, [])

    def test_deny_when_calibration_pending(self) -> None:
        allow, schema_errors, reasons = evaluate(
            _budget(grand=10),
            _ceiling(calibration_status=BOOTSTRAP_TOKEN),
        )
        self.assertFalse(allow)
        self.assertEqual(schema_errors, [])
        self.assertEqual(len(reasons), 1)
        self.assertIn("bootstrap-pending-rung-3", reasons[0])

    def test_deny_when_budget_uncalibrated(self) -> None:
        allow, schema_errors, reasons = evaluate(
            _budget(calibrated=False, grand=10),
            _ceiling(grand=1000),
        )
        self.assertFalse(allow)
        self.assertEqual(schema_errors, [])
        self.assertEqual(len(reasons), 1)
        self.assertIn("budget.calibrated is false", reasons[0])

    def test_deny_when_grand_breaches_ceiling(self) -> None:
        allow, _, reasons = evaluate(
            _budget(grand=2000), _ceiling(grand=1000)
        )
        self.assertFalse(allow)
        self.assertTrue(any("grandPredictedCycles" in r for r in reasons))

    def test_deny_when_per_phase_breaches_ceiling(self) -> None:
        allow, _, reasons = evaluate(
            _budget(
                grand=100,
                phase_totals={
                    "prefill": {"predictedCycles": 500},
                    "decode": {"predictedCycles": 50},
                },
            ),
            _ceiling(grand=1000, per_phase={"prefill": 400, "decode": 100}),
        )
        self.assertFalse(allow)
        self.assertTrue(any("prefill" in r for r in reasons))

    def test_phase_under_ceiling_no_violation(self) -> None:
        allow, _, reasons = evaluate(
            _budget(
                grand=100,
                phase_totals={
                    "prefill": {"predictedCycles": 200},
                    "decode": {"predictedCycles": 50},
                },
            ),
            _ceiling(grand=1000, per_phase={"prefill": 400, "decode": 100}),
        )
        self.assertTrue(allow)
        self.assertEqual(reasons, [])

    def test_invalid_calibration_token_denies(self) -> None:
        allow, schema_errors, reasons = evaluate(
            _budget(grand=10),
            _ceiling(calibration_status="not-a-hash"),
        )
        self.assertFalse(allow)
        # Schema check raises errors when jsonschema is available;
        # otherwise calibration check raises in reasons. Either path
        # must deny.
        self.assertTrue(schema_errors or reasons)

    def test_schema_errors_when_artifact_kind_wrong(self) -> None:
        bad_ceiling = _ceiling()
        bad_ceiling["artifactKind"] = "wrong"
        allow, schema_errors, reasons = evaluate(
            _budget(), bad_ceiling
        )
        self.assertFalse(allow)
        self.assertTrue(schema_errors)


class BuildDecisionReceiptTest(unittest.TestCase):
    def test_receipt_contains_hashes_and_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            budget_path = tmp_path / "budget.json"
            ceiling_path = tmp_path / "ceiling.json"
            budget_path.write_text("{}", encoding="utf-8")
            ceiling_path.write_text("{}", encoding="utf-8")
            receipt = build_decision_receipt(
                budget_path=budget_path,
                budget_hash="b" * 64,
                ceiling_path=ceiling_path,
                ceiling_hash="c" * 64,
                budget=_budget(grand=42),
                ceiling=_ceiling(grand=1000),
                allow=True,
                schema_errors=[],
                reasons=[],
            )
        self.assertEqual(receipt["decision"], "allow")
        self.assertEqual(receipt["budgetHash"], "b" * 64)
        self.assertEqual(receipt["ceilingHash"], "c" * 64)
        self.assertEqual(receipt["observed"]["grandPredictedCycles"], 42)
        self.assertEqual(receipt["observed"]["calibrated"], True)
        self.assertIn("scope", receipt["claim"])
        self.assertIn("notWhat", receipt["claim"])

    def test_deny_receipt_records_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            receipt = build_decision_receipt(
                budget_path=tmp_path / "budget.json",
                budget_hash="b" * 64,
                ceiling_path=tmp_path / "ceiling.json",
                ceiling_hash="c" * 64,
                budget=_budget(),
                ceiling=_ceiling(calibration_status=BOOTSTRAP_TOKEN),
                allow=False,
                schema_errors=[],
                reasons=["calibration pending"],
            )
        self.assertEqual(receipt["decision"], "deny")
        self.assertEqual(receipt["reasons"], ["calibration pending"])
        self.assertEqual(
            receipt["calibrationStatus"], BOOTSTRAP_TOKEN
        )


class IntegrationTest(unittest.TestCase):
    def test_bootstrap_ceiling_in_repo_denies_with_default_budget_shape(
        self,
    ) -> None:
        ceiling_path = (
            REPO_ROOT / "config/manifest-simfabric-budget.json"
        )
        ceiling = json.loads(ceiling_path.read_text(encoding="utf-8"))
        budget = _budget(calibrated=False, grand=100)
        allow, schema_errors, reasons = evaluate(budget, ceiling)
        self.assertFalse(allow)
        self.assertEqual(schema_errors, [])
        # Both calibration and budget-calibrated checks should fire
        # against the in-repo bootstrap ceiling and an uncalibrated
        # budget. Order is calibration first, then budget-calibrated.
        self.assertTrue(any("bootstrap-pending-rung-3" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
