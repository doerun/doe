from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._receipt_hash_guard import (  # noqa: E402
    HashSpineReport,
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
    evaluate_receipt_hash_spine,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReceiptHashGuardTest(unittest.TestCase):
    def test_passes_when_no_hashes_cited(self) -> None:
        report = evaluate_receipt_hash_spine({"schemaVersion": 1})
        self.assertTrue(report.bound)
        self.assertEqual(report.violations, [])

    def test_pending_manifest_hash_is_advisory(self) -> None:
        report = evaluate_receipt_hash_spine({"manifestSha256": "pending"})
        self.assertTrue(report.bound, msg=report.violations)

    def test_manifest_hash_match(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            manifest = root / "manifest.json"
            payload = b'{"schemaVersion": 1}'
            manifest.write_bytes(payload)
            receipt = {
                "manifestPath": "manifest.json",
                "manifestSha256": _sha256_bytes(payload),
            }
            report = evaluate_receipt_hash_spine(receipt, repo_root=root)
            self.assertTrue(report.bound, msg=report.violations)

    def test_manifest_hash_drift_is_violation(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            manifest = root / "manifest.json"
            manifest.write_bytes(b'{"schemaVersion": 1}')
            receipt = {
                "manifestPath": "manifest.json",
                "manifestSha256": "0" * 64,
            }
            report = evaluate_receipt_hash_spine(receipt, repo_root=root)
            self.assertFalse(report.bound)
            self.assertTrue(
                any("manifestSha256 drift" in v for v in report.violations)
            )

    def test_manifest_hash_without_path_violates(self) -> None:
        receipt = {"manifestSha256": "0" * 64}
        report = evaluate_receipt_hash_spine(receipt)
        self.assertFalse(report.bound)
        self.assertTrue(
            any("manifestPath" in v for v in report.violations)
        )

    def test_host_plan_hash_match(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            host_plan = root / "host-plan.json"
            payload = b'{"hostPlan": "ok"}'
            host_plan.write_bytes(payload)
            receipt = {
                "hostPlanPath": "host-plan.json",
                "hostPlanHash": _sha256_bytes(payload),
            }
            report = evaluate_receipt_hash_spine(receipt, repo_root=root)
            self.assertTrue(report.bound, msg=report.violations)

    def test_host_plan_hash_drift_is_violation(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            host_plan = root / "host-plan.json"
            host_plan.write_bytes(b"different")
            receipt = {
                "hostPlanPath": "host-plan.json",
                "hostPlanHash": "0" * 64,
            }
            report = evaluate_receipt_hash_spine(receipt, repo_root=root)
            self.assertFalse(report.bound)
            self.assertTrue(
                any("hostPlanHash drift" in v for v in report.violations)
            )

    def test_manifest_shape_parity_requires_reference_fixture_hash(
        self,
    ) -> None:
        receipt = {
            "receiptClass": "manifest_shape_layout_receipt",
            "comparisonMode": "parity",
        }
        report = evaluate_receipt_hash_spine(receipt)
        self.assertFalse(report.bound)
        self.assertTrue(
            any(
                "referenceFixtureHash" in v for v in report.violations
            )
        )

    def test_manifest_shape_dispatch_only_does_not_require_fixture(
        self,
    ) -> None:
        receipt = {
            "receiptClass": "manifest_shape_dispatch_receipt",
            "comparisonMode": "structural",
        }
        report = evaluate_receipt_hash_spine(receipt)
        self.assertTrue(report.bound, msg=report.violations)

    def test_smoke_shape_parity_does_not_require_fixture(self) -> None:
        receipt = {
            "receiptClass": "smoke_shape_parity_receipt",
            "comparisonMode": "parity",
        }
        report = evaluate_receipt_hash_spine(receipt)
        self.assertTrue(report.bound, msg=report.violations)

    def test_enforce_raises_on_violation(self) -> None:
        receipt = {"manifestSha256": "0" * 64}
        with self.assertRaises(ReceiptHashSpineError):
            enforce_receipt_hash_spine(receipt)

    def test_report_to_dict_round_trip(self) -> None:
        receipt = {
            "receiptClass": "manifest_shape_layout_receipt",
            "comparisonMode": "parity",
        }
        report = evaluate_receipt_hash_spine(receipt)
        as_dict = report.to_dict()
        self.assertEqual(as_dict["schemaVersion"], 1)
        self.assertEqual(
            as_dict["artifactKind"], "doe_receipt_hash_spine_report"
        )
        self.assertFalse(as_dict["bound"])
        self.assertGreater(len(as_dict["violations"]), 0)
        # JSON-serializable.
        json.dumps(as_dict)


if __name__ == "__main__":
    unittest.main()
