"""Tests for the advisory TSIR nightly parity canary."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from bench.gates import nightly_tsir_parity_canary as canary


REPO_ROOT = Path(__file__).resolve().parents[2]


class NightlyTsirParityCanaryTests(unittest.TestCase):
    def test_loads_exact_bootstrap_fixture_set(self) -> None:
        entries = canary.load_fixture_entries(canary.DEFAULT_FIXTURE_DIR)
        pairs = {
            (entry["kernelRef"], entry["backend"])
            for _, entry in entries
        }
        self.assertEqual(len(entries), 6)
        self.assertEqual(
            pairs,
            {
                ("doe.tsir.bootstrap.fused_gemv", "webgpu-generic"),
                ("doe.tsir.bootstrap.fused_gemv", "wse3"),
                ("doe.tsir.bootstrap.gather", "webgpu-generic"),
                ("doe.tsir.bootstrap.gather", "wse3"),
                ("doe.tsir.bootstrap.rms_norm", "webgpu-generic"),
                ("doe.tsir.bootstrap.rms_norm", "wse3"),
            },
        )

    def test_canary_runs_fixture_receipts_without_claiming_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = canary.build_report(
                canary.DEFAULT_FIXTURE_DIR,
                Path(tmp),
                python=sys.executable,
            )
        self.assertEqual(report["artifactKind"], "tsir_nightly_parity_canary")
        self.assertEqual(report["fixtureCount"], 6)
        self.assertEqual(report["failures"], [])
        for result in report["results"]:
            self.assertIn("loweringIdentity", result)
            self.assertIn("not_implemented", result["statuses"])
            self.assertIn("deferred", result["statuses"])
            self.assertEqual(result["cliExitCode"], 1)


if __name__ == "__main__":
    unittest.main()
