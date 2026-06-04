"""Tests for package order-sensitivity phase-delta analysis."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from bench.tools import package_order_sensitivity as order_sensitivity


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "bench" / "tools" / "package_order_sensitivity.py"


def _phase_report(
    baseline_label: str,
    comparison_label: str,
    workload_id: str,
    timing_delta: float,
    derived_delta: float,
) -> dict:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_package_phase_delta",
        "baseline": {"label": baseline_label},
        "comparison": {"label": comparison_label},
        "workloads": {
            workload_id: {
                "timing": {
                    "workloadId": workload_id,
                    "section": "timing",
                    "phase": "measuredMs",
                    "baselineP50Ms": 1.0,
                    "comparisonP50Ms": 2.0,
                    "comparisonMinusBaselineP50Ms": timing_delta,
                    "positiveMeansBaselineLower": True,
                },
                "setup": [],
                "step": [],
                "derived": [
                    {
                        "workloadId": workload_id,
                        "section": "derived",
                        "phase": "stepSelectedTotalNs",
                        "baselineP50Ms": 1.0,
                        "comparisonP50Ms": 2.0,
                        "comparisonMinusBaselineP50Ms": derived_delta,
                        "positiveMeansBaselineLower": True,
                    }
                ],
            }
        },
        "phaseGaps": [],
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class TestPackageOrderSensitivity(unittest.TestCase):
    def test_compare_reports_flags_direction_flips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_path = root / "first.phase-delta.json"
            second_path = root / "second.phase-delta.json"
            first = _phase_report("public_bun", "direct_bun_ffi", "vector", -1.0, -2.0)
            second = _phase_report("public_bun", "direct_bun_ffi", "vector", 1.0, -3.0)
            _write(first_path, first)
            _write(second_path, second)

            report = order_sensitivity.compare_reports(
                first_path=first_path,
                first_report=first,
                first_order_label="public-then-direct",
                second_path=second_path,
                second_report=second,
                second_order_label="direct-then-public",
            )

        self.assertEqual(report["artifactKind"], "doe_package_order_sensitivity")
        self.assertEqual(report["status"], "order_sensitive_diagnostic")
        self.assertEqual(
            report["summary"]["recommendation"],
            "keep_diagnostic_until_order_sensitivity_is_explained",
        )
        timing_row = next(
            row
            for row in report["phaseRows"]
            if row["section"] == "timing" and row["phase"] == "measuredMs"
        )
        self.assertEqual(timing_row["direction"], "sign_flip")
        self.assertFalse(timing_row["directionStable"])
        derived_row = next(
            row
            for row in report["phaseRows"]
            if row["section"] == "derived" and row["phase"] == "stepSelectedTotalNs"
        )
        self.assertEqual(derived_row["direction"], "same_negative")
        self.assertTrue(derived_row["directionStable"])
        self.assertTrue(report["artifactHash"].startswith("sha256:"))

    def test_compare_reports_requires_same_side_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_path = root / "first.phase-delta.json"
            second_path = root / "second.phase-delta.json"
            first = _phase_report("public_bun", "direct_bun_ffi", "vector", -1.0, -2.0)
            second = _phase_report("direct_bun_ffi", "public_bun", "vector", 1.0, 2.0)
            _write(first_path, first)
            _write(second_path, second)

            with self.assertRaises(ValueError):
                order_sensitivity.compare_reports(
                    first_path=first_path,
                    first_report=first,
                    first_order_label="public-then-direct",
                    second_path=second_path,
                    second_report=second,
                    second_order_label="direct-then-public",
                )

    def test_cli_writes_order_sensitivity_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_path = root / "first.phase-delta.json"
            second_path = root / "second.phase-delta.json"
            out_path = root / "order-sensitivity.json"
            _write(
                first_path,
                _phase_report("public_bun", "direct_bun_ffi", "vector", -1.0, -2.0),
            )
            _write(
                second_path,
                _phase_report("public_bun", "direct_bun_ffi", "vector", 1.0, 2.0),
            )

            result = subprocess.run(
                [
                    "python3",
                    str(TOOL_PATH),
                    "--first-order-report",
                    str(first_path),
                    "--second-order-report",
                    str(second_path),
                    "--first-order-label",
                    "public-then-direct",
                    "--second-order-label",
                    "direct-then-public",
                    "--json-out",
                    str(out_path),
                    "--top",
                    "1",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("order_sensitive_diagnostic", result.stdout)
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "order_sensitive_diagnostic")
            self.assertEqual(payload["summary"]["signFlipCount"], 2)


if __name__ == "__main__":
    unittest.main()
