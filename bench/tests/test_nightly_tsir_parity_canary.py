"""Tests for the advisory TSIR nightly parity canary."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from bench.gates import nightly_tsir_parity_canary as canary


REPO_ROOT = Path(__file__).resolve().parents[2]

LOWERING_IDENTITY_KEYS = (
    "emitterDigest",
    "targetDescriptorCorrectnessHash",
    "tsirRealizationDigest",
    "tsirSemanticDigest",
)


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

    def test_canary_receipts_carry_fixture_lowering_identity(self) -> None:
        """Each canary receipt must carry the same TSIR identity digests as
        the source manifest-lowering fixture it was produced from.

        This locks the cross-artifact invariant that a parity receipt is
        bound to exactly the (semantic, realization, emitter, target)
        tuple declared by the manifest entry — not a drifted or
        recomputed version. If a future change to the parity CLI or the
        canary starts emitting receipts with different digests than the
        fixture, this test turns red and blocks the drift before it
        reaches Loop 3 promotion.
        """
        kernel_prefix = "doe.tsir.bootstrap."
        entries = canary.load_fixture_entries(canary.DEFAULT_FIXTURE_DIR)
        fixture_by_pair = {
            (
                entry["kernelRef"].removeprefix(kernel_prefix),
                entry["backend"],
            ): entry
            for _, entry in entries
        }

        with tempfile.TemporaryDirectory() as tmp:
            report = canary.build_report(
                canary.DEFAULT_FIXTURE_DIR,
                Path(tmp),
                python=sys.executable,
            )
            for result in report["results"]:
                kernel = result["kernel"]
                backend = result["backend"]
                fixture = fixture_by_pair[(kernel, backend)]
                identity = result["loweringIdentity"]
                for key in LOWERING_IDENTITY_KEYS:
                    self.assertEqual(
                        identity[key],
                        fixture[key],
                        msg=(
                            f"canary receipt {kernel}/{backend} diverged "
                            f"from fixture on {key}: receipt={identity[key]!r} "
                            f"fixture={fixture[key]!r}"
                        ),
                    )


if __name__ == "__main__":
    unittest.main()
