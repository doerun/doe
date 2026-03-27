#!/usr/bin/env python3
"""Regression tests for timing-interpretation metric naming."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
if str(BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(BENCH_ROOT))

from native_compare_modules.timing_interpretation import build_timing_interpretation


def make_side(timing_source: str) -> dict[str, object]:
    return {
        "timingSources": [timing_source],
        "timingClasses": ["operation"],
        "commandSamples": [
            {
                "elapsedMs": 10.0,
                "measuredMs": 4.0,
                "commandRepeat": 2,
                "timingNormalizationDivisor": 1.0,
                "traceMeta": {
                    "hostInputReadTotalNs": 1_000_000,
                    "hostInputParseTotalNs": 2_000_000,
                    "hostCommandOrchestrationTotalNs": 500_000,
                },
            },
            {
                "elapsedMs": 12.0,
                "measuredMs": 5.0,
                "commandRepeat": 2,
                "timingNormalizationDivisor": 1.0,
                "traceMeta": {
                    "hostInputReadTotalNs": 1_000_000,
                    "hostInputParseTotalNs": 2_000_000,
                    "hostCommandOrchestrationTotalNs": 500_000,
                },
            },
        ],
    }


def make_prepared_session_side() -> dict[str, object]:
    return {
        "timingSources": ["doe-execution-total-ns"],
        "timingClasses": ["operation"],
        "commandSamples": [
            {
                "elapsedMs": 30.0,
                "measuredMs": 20.0,
                "commandRepeat": 1,
                "timingNormalizationDivisor": 1.0,
                "traceMeta": {
                    "workloadUnitWallSource": "trace-meta-process-wall",
                    "packagePreparedSession": True,
                    "hostInputReadTotalNs": 0,
                    "hostInputParseTotalNs": 0,
                    "hostWorkloadPrepareTotalNs": 0,
                    "hostExecutorInitTotalNs": 0,
                    "hostCommandOrchestrationTotalNs": 3_000_000,
                    "hostArtifactFinalizeTotalNs": 2_000_000,
                },
            },
            {
                "elapsedMs": 32.0,
                "measuredMs": 21.0,
                "commandRepeat": 1,
                "timingNormalizationDivisor": 1.0,
                "traceMeta": {
                    "workloadUnitWallSource": "trace-meta-process-wall",
                    "packagePreparedSession": True,
                    "hostInputReadTotalNs": 0,
                    "hostInputParseTotalNs": 0,
                    "hostWorkloadPrepareTotalNs": 0,
                    "hostExecutorInitTotalNs": 0,
                    "hostCommandOrchestrationTotalNs": 4_000_000,
                    "hostArtifactFinalizeTotalNs": 2_000_000,
                },
            },
        ],
    }


class TimingInterpretationNamingTests(unittest.TestCase):
    def test_emits_workload_unit_wall_with_legacy_alias(self) -> None:
        interpretation = build_timing_interpretation(
            left=make_side("doe-execution-total-ns"),
            right=make_side("doe-execution-total-ns"),
        )

        workload_unit_wall = interpretation.get("workloadUnitWall")
        legacy_alias = interpretation.get("headlineProcessWall")

        self.assertIsInstance(workload_unit_wall, dict)
        self.assertEqual(workload_unit_wall.get("scopeClass"), "workload-unit-wall")
        self.assertTrue(workload_unit_wall.get("available"))
        self.assertAlmostEqual(workload_unit_wall["leftStatsMs"]["p50Ms"], 5.0)
        self.assertAlmostEqual(workload_unit_wall["rightStatsMs"]["p50Ms"], 5.0)

        self.assertIsInstance(legacy_alias, dict)
        self.assertEqual(legacy_alias.get("deprecatedAliasFor"), "workloadUnitWall")
        self.assertEqual(
            legacy_alias.get("deltaPercent"),
            workload_unit_wall.get("deltaPercent"),
        )

        host_overhead = interpretation.get("hostOverheadBreakdown")
        self.assertIsInstance(host_overhead, dict)
        self.assertTrue(host_overhead.get("available"))
        self.assertAlmostEqual(host_overhead["selectedGap"]["leftStatsMs"]["p50Ms"], 1.0)
        self.assertAlmostEqual(host_overhead["attributedHostOverhead"]["leftStatsMs"]["p50Ms"], 1.75)
        self.assertAlmostEqual(
            host_overhead["unattributedGapRemainder"]["leftStatsMs"]["p50Ms"],
            -0.75,
        )
        self.assertIn("inputRead", host_overhead.get("buckets", {}))
        self.assertEqual(
            host_overhead["buckets"]["inputRead"].get("traceMetaField"),
            "hostInputReadTotalNs",
        )

    def test_prepared_session_host_overhead_stays_within_selected_gap(self) -> None:
        interpretation = build_timing_interpretation(
            left=make_prepared_session_side(),
            right=make_prepared_session_side(),
        )

        host_overhead = interpretation.get("hostOverheadBreakdown")
        self.assertIsInstance(host_overhead, dict)
        self.assertTrue(host_overhead.get("available"))
        self.assertLessEqual(
            host_overhead["attributedHostOverhead"]["leftStatsMs"]["p50Ms"],
            host_overhead["selectedGap"]["leftStatsMs"]["p50Ms"],
        )
        self.assertGreaterEqual(
            host_overhead["unattributedGapRemainder"]["leftStatsMs"]["p50Ms"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
