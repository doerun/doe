"""Tests for the shared ad-hoc claim-grade gating module."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.adhoc_claim_gating import (
    CLAIM_LOCAL_MIN_SAMPLES,
    CLAIM_RELEASE_MIN_SAMPLES,
    ClaimPolicy,
    DeltaPercentiles,
    aggregate_claim_status,
    gate_workload_claim,
)


class TestClaimPolicy(unittest.TestCase):
    def test_release_mode(self) -> None:
        p = ClaimPolicy.for_mode("release")
        self.assertEqual(p.mode, "release")
        self.assertEqual(p.min_timed_samples, CLAIM_RELEASE_MIN_SAMPLES)
        self.assertEqual(p.required_positive_percentiles, ("p50", "p95", "p99"))

    def test_local_mode(self) -> None:
        p = ClaimPolicy.for_mode("local")
        self.assertEqual(p.min_timed_samples, CLAIM_LOCAL_MIN_SAMPLES)
        self.assertEqual(p.required_positive_percentiles, ("p50", "p95"))

    def test_unknown_mode_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ClaimPolicy.for_mode("diagnostic")


class TestGateWorkloadClaim(unittest.TestCase):
    def test_release_all_positive_passes(self) -> None:
        policy = ClaimPolicy.for_mode("release")
        record = gate_workload_claim(
            shader="unity_webgpu_000002778F740030.fs.spv",
            baseline_sample_count=50,
            comparison_sample_count=50,
            delta_percent=DeltaPercentiles(p50=348.2, p95=349.86, p99=342.86),
            policy=policy,
        )
        self.assertTrue(record["claimable"])
        self.assertEqual(record["reasons"], [])

    def test_release_negative_p99_fails(self) -> None:
        policy = ClaimPolicy.for_mode("release")
        record = gate_workload_claim(
            shader="cluster-lights.wgsl",
            baseline_sample_count=50,
            comparison_sample_count=50,
            delta_percent=DeltaPercentiles(p50=+10.0, p95=+5.0, p99=-43.05),
            policy=policy,
        )
        self.assertFalse(record["claimable"])
        self.assertEqual(len(record["reasons"]), 1)
        self.assertIn("p99 delta -43.05%", record["reasons"][0])

    def test_local_ignores_p99(self) -> None:
        policy = ClaimPolicy.for_mode("local")
        record = gate_workload_claim(
            shader="cluster-lights.wgsl",
            baseline_sample_count=50,
            comparison_sample_count=50,
            delta_percent=DeltaPercentiles(p50=+10.0, p95=+5.0, p99=-43.05),
            policy=policy,
        )
        self.assertTrue(record["claimable"])

    def test_below_sample_floor_fails(self) -> None:
        policy = ClaimPolicy.for_mode("release")
        record = gate_workload_claim(
            shader="shadow-fragment.wgsl",
            baseline_sample_count=5,
            comparison_sample_count=50,
            delta_percent=DeltaPercentiles(p50=+10.0, p95=+5.0, p99=+3.0),
            policy=policy,
        )
        self.assertFalse(record["claimable"])
        self.assertIn("baseline sample count 5", record["reasons"][0])

    def test_timer_overhead_budget(self) -> None:
        policy = ClaimPolicy.for_mode("release")
        # Timer overhead 2% of smallest p50 -> exceeds default 1% budget
        record = gate_workload_claim(
            shader="trivial_noop",
            baseline_sample_count=50,
            comparison_sample_count=50,
            delta_percent=DeltaPercentiles(p50=+10.0, p95=+5.0, p99=+3.0),
            policy=policy,
            timer_overhead_p50_ns=200,
            smallest_measurement_p50_ns=10_000,
        )
        self.assertFalse(record["claimable"])
        self.assertTrue(any("timer overhead" in r for r in record["reasons"]))

    def test_warm_sample_count_gate(self) -> None:
        policy = ClaimPolicy.for_mode("release")
        record = gate_workload_claim(
            shader="atan2-const-eval.wgsl",
            baseline_sample_count=50,
            comparison_sample_count=50,
            warm_comparison_sample_count=5,
            delta_percent=DeltaPercentiles(p50=+40.0, p95=+30.0, p99=+20.0),
            policy=policy,
        )
        self.assertFalse(record["claimable"])
        self.assertTrue(any("warm comparison sample count 5" in r for r in record["reasons"]))


class TestAggregateClaimStatus(unittest.TestCase):
    def test_all_pass_aggregates_claimable(self) -> None:
        workloads = [
            {"shader": "a", "claimable": True, "reasons": []},
            {"shader": "b", "claimable": True, "reasons": []},
        ]
        status, passed, reasons = aggregate_claim_status(workloads)
        self.assertEqual(status, "claimable")
        self.assertTrue(passed)
        self.assertEqual(reasons, [])

    def test_any_fail_aggregates_not_claimable(self) -> None:
        workloads = [
            {"shader": "a", "claimable": True, "reasons": []},
            {"shader": "b", "claimable": False, "reasons": ["p99 delta -5.0% not positive"]},
        ]
        status, passed, reasons = aggregate_claim_status(workloads)
        self.assertEqual(status, "not_claimable")
        self.assertFalse(passed)
        self.assertEqual(reasons, ["1 of 2 rows not claimable"])


class TestClaimPolicyDict(unittest.TestCase):
    def test_with_timer_overhead(self) -> None:
        p = ClaimPolicy.for_mode("release")
        d = p.to_dict(timer_overhead_p50_ns=50)
        self.assertEqual(d["mode"], "release")
        self.assertEqual(d["timerOverheadP50Ns"], 50)
        self.assertEqual(d["requiredPositivePercentiles"], ["p50", "p95", "p99"])

    def test_without_timer_overhead(self) -> None:
        p = ClaimPolicy.for_mode("local")
        d = p.to_dict()
        self.assertNotIn("timerOverheadP50Ns", d)
        self.assertEqual(d["minTimedSamples"], CLAIM_LOCAL_MIN_SAMPLES)


if __name__ == "__main__":
    unittest.main()
