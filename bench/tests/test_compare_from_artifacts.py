"""Tests for post-hoc comparison from run artifacts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from native_compare_modules.compare_from_artifacts import (
    COMPARE_REPORT_SCHEMA_VERSION,
    build_compare_report,
    compare_workload_from_artifacts,
)


def _make_artifact(product: str, workload_id: str = "compute_test") -> dict:
    return {
        "schemaVersion": 1,
        "artifactKind": "run",
        "generatedAt": "2026-04-05T12:00:00+00:00",
        "product": product,
        "executorId": f"{product}_direct_vulkan",
        "workload": {
            "id": workload_id,
            "name": "test workload",
            "description": "unit test",
            "domain": "compute",
            "comparable": True,
            "benchmarkClass": "comparable",
            "comparabilityNotes": "test",
            "pathAsymmetry": False,
            "pathAsymmetryNote": "",
            "claimEligible": True,
            "cohorts": ["governed"],
        },
        "runParameters": {
            "iterations": 4,
            "warmup": 0,
            "commandRepeat": 1,
            "ignoreFirstOps": 0,
            "timingDivisor": 1.0,
            "uploadBufferUsage": "copy-dst",
            "uploadSubmitEvery": 1,
        },
        "host": {"os": "linux", "arch": "x86_64"},
        "commandSamples": [
            {
                "runIndex": i,
                "elapsedMs": 10.0 + i * 0.5 + (0 if product == "doe" else 2.0),
                "measuredMs": 8.0 + i * 0.3 + (0 if product == "doe" else 2.0),
                "timingSource": "doe-execution-total-ns",
                "timing": {"traceMetaSource": "doe-execution-total-ns"},
            }
            for i in range(4)
        ],
        "stats": {
            "count": 4,
            "p10Ms": 8.0 + (0 if product == "doe" else 2.0),
            "p50Ms": 8.5 + (0 if product == "doe" else 2.0),
            "p95Ms": 9.0 + (0 if product == "doe" else 2.0),
            "p99Ms": 9.0 + (0 if product == "doe" else 2.0),
            "meanMs": 8.5 + (0 if product == "doe" else 2.0),
            "minMs": 8.0 + (0 if product == "doe" else 2.0),
            "maxMs": 9.0 + (0 if product == "doe" else 2.0),
        },
        "timingsMs": [
            8.0 + i * 0.3 + (0 if product == "doe" else 2.0) for i in range(4)
        ],
        "timingSources": ["doe-execution-total-ns"],
        "timingClasses": ["operation"],
        "lastMeta": {"module": "doe-zig-runtime"},
    }


class TestCompareWorkloadFromArtifacts(unittest.TestCase):
    def test_basic_comparison(self) -> None:
        baseline = _make_artifact("doe")
        comparison = _make_artifact("dawn")
        entry = compare_workload_from_artifacts(
            baseline=baseline,
            comparison=comparison,
        )
        self.assertEqual(entry["id"], "compute_test")
        self.assertIn("doe", entry["participants"])
        self.assertIn("dawn", entry["participants"])
        # v5 compat aliases
        self.assertIn("left", entry)
        self.assertIn("right", entry)
        # delta should be positive (doe faster since lower timings)
        self.assertGreater(entry["deltaPercent"]["p50Percent"], 0)
        self.assertIn("comparability", entry)
        self.assertIn("claimability", entry)

    def test_claimability_off_by_default(self) -> None:
        entry = compare_workload_from_artifacts(
            baseline=_make_artifact("doe"),
            comparison=_make_artifact("dawn"),
        )
        self.assertFalse(entry["claimability"]["evaluated"])


class TestBuildCompareReport(unittest.TestCase):
    def test_report_structure(self) -> None:
        baseline = _make_artifact("doe")
        comparison = _make_artifact("dawn")
        entry = compare_workload_from_artifacts(
            baseline=baseline,
            comparison=comparison,
        )
        report = build_compare_report(
            workload_entries=[entry],
            baseline_artifact=baseline,
            comparison_artifact=comparison,
            comparability_mode="strict",
            required_timing_class="operation",
            claimability_mode="off",
            claimability_min_timed_samples=0,
            out_path="test.json",
            run_artifact_paths=["a.run.json", "b.run.json"],
        )
        self.assertEqual(report["schemaVersion"], COMPARE_REPORT_SCHEMA_VERSION)
        self.assertEqual(report["products"], ["doe", "dawn"])
        self.assertIn("doe", report["participants"])
        self.assertIn("dawn", report["participants"])
        # v5 compat
        self.assertIn("left", report["participants"])
        self.assertIn("right", report["participants"])
        self.assertEqual(len(report["workloads"]), 1)
        self.assertEqual(len(report["runArtifactPaths"]), 2)

    def test_report_writes_to_disk(self) -> None:
        from native_compare_modules.compare_from_artifacts import write_compare_report

        baseline = _make_artifact("doe")
        comparison = _make_artifact("dawn")
        entry = compare_workload_from_artifacts(
            baseline=baseline, comparison=comparison,
        )
        report = build_compare_report(
            workload_entries=[entry],
            baseline_artifact=baseline,
            comparison_artifact=comparison,
            comparability_mode="strict",
            required_timing_class="operation",
            claimability_mode="off",
            claimability_min_timed_samples=0,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.json"
            write_compare_report(report, path)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["schemaVersion"], COMPARE_REPORT_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
