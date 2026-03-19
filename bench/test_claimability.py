#!/usr/bin/env python3
"""Regression tests for claimability metric-scope selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_ROOT = REPO_ROOT / "bench"
if str(BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(BENCH_ROOT))

from native_compare_modules.claimability import assess_claimability
from native_compare_modules.config_support import BenchmarkMethodologyPolicy


BENCHMARK_POLICY = BenchmarkMethodologyPolicy(
    source_path="config/benchmark-methodology-thresholds.json",
    min_dispatch_window_ns_without_encode=500000,
    min_dispatch_window_coverage_percent_without_encode=1.0,
    local_claim_min_timed_samples=19,
    release_claim_min_timed_samples=15,
    min_operation_wall_coverage_ratio=0.05,
    max_operation_wall_coverage_asymmetry_ratio=128.0,
)


def make_stats(p50: float, p95: float) -> dict[str, float]:
    return {
        "count": 19,
        "minMs": p50,
        "maxMs": p95,
        "p10Ms": p50,
        "p50Ms": p50,
        "p95Ms": p95,
        "p99Ms": p95,
        "meanMs": p50,
        "stdevMs": 0.00001,
    }


def make_timing_interpretation(
    *,
    headline_p50: float,
    headline_p95: float,
    headline_delta_p50: float,
    headline_delta_p95: float,
) -> dict[str, object]:
    return {
        "selectedTiming": {
            "scope": "operation-total",
            "scopeClass": "operation-total",
        },
        "headlineProcessWall": {
            "available": True,
            "leftStatsMs": make_stats(headline_p50, headline_p95),
            "rightStatsMs": make_stats(headline_p50 * 1.1, headline_p95 * 1.1),
            "deltaPercent": {
                "p50Percent": headline_delta_p50,
                "p95Percent": headline_delta_p95,
                "p99Percent": headline_delta_p95,
            },
        },
    }


class ClaimabilityMetricScopeTests(unittest.TestCase):
    def test_copy_prefers_headline_when_operation_total_undercovers_end_to_end(self) -> None:
        workload = SimpleNamespace(
            id="copy_texture_to_texture",
            domain="copy",
            path_asymmetry=False,
            path_asymmetry_note="",
        )
        left = {"stats": make_stats(0.00047, 0.00050), "commandSamples": []}
        right = {"stats": make_stats(0.00048, 0.00049), "commandSamples": []}
        timing_interpretation = make_timing_interpretation(
            headline_p50=0.00173,
            headline_p95=0.00178,
            headline_delta_p50=24.5,
            headline_delta_p95=22.4,
        )

        claimability = assess_claimability(
            mode="local",
            min_timed_samples=19,
            workload=workload,
            left=left,
            right=right,
            delta={"p50Percent": 2.1, "p95Percent": -0.7, "p99Percent": -0.7},
            timing_interpretation=timing_interpretation,
            comparability={"comparable": True},
            benchmark_policy=BENCHMARK_POLICY,
        )

        self.assertTrue(claimability["claimable"])
        self.assertEqual(claimability["claimMetricScope"], "headlineProcessWall")

    def test_surface_prefers_headline_when_operation_total_undercovers_end_to_end(self) -> None:
        workload = SimpleNamespace(
            id="surface_full_presentation",
            domain="surface",
            path_asymmetry=False,
            path_asymmetry_note="",
        )
        left = {"stats": make_stats(0.0202, 0.0246), "commandSamples": []}
        right = {"stats": make_stats(0.0191, 0.0240), "commandSamples": []}
        timing_interpretation = make_timing_interpretation(
            headline_p50=0.0507,
            headline_p95=0.0526,
            headline_delta_p50=7.8,
            headline_delta_p95=16.7,
        )

        claimability = assess_claimability(
            mode="local",
            min_timed_samples=19,
            workload=workload,
            left=left,
            right=right,
            delta={"p50Percent": -5.3, "p95Percent": -2.5, "p99Percent": -2.5},
            timing_interpretation=timing_interpretation,
            comparability={"comparable": True},
            benchmark_policy=BENCHMARK_POLICY,
        )

        self.assertTrue(claimability["claimable"])
        self.assertEqual(claimability["claimMetricScope"], "headlineProcessWall")

    def test_does_not_switch_when_headline_tail_is_not_positive(self) -> None:
        workload = SimpleNamespace(
            id="copy_texture_to_texture",
            domain="copy",
            path_asymmetry=False,
            path_asymmetry_note="",
        )
        left = {"stats": make_stats(0.00047, 0.00050), "commandSamples": []}
        right = {"stats": make_stats(0.00048, 0.00049), "commandSamples": []}
        timing_interpretation = make_timing_interpretation(
            headline_p50=0.00173,
            headline_p95=0.00178,
            headline_delta_p50=24.5,
            headline_delta_p95=-1.0,
        )

        claimability = assess_claimability(
            mode="local",
            min_timed_samples=19,
            workload=workload,
            left=left,
            right=right,
            delta={"p50Percent": 2.1, "p95Percent": -0.7, "p99Percent": -0.7},
            timing_interpretation=timing_interpretation,
            comparability={"comparable": True},
            benchmark_policy=BENCHMARK_POLICY,
        )

        self.assertFalse(claimability["claimable"])
        self.assertEqual(claimability["claimMetricScope"], "selectedTiming")


if __name__ == "__main__":
    unittest.main()
