"""Tests for post-hoc comparison from run artifacts."""

from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from native_compare_modules.compare_from_artifacts import (
    COMPARE_REPORT_SCHEMA_VERSION,
    build_compare_report,
    build_legacy_compare_report_from_artifacts,
    compare_workload_from_artifacts,
    group_run_artifacts_by_workload,
    workload_from_artifact_pair,
)


def _make_artifact(product: str, workload_id: str = "compute_test") -> dict:
    return {
        "schemaVersion": 2,
        "artifactKind": "run",
        "generatedAt": "2026-04-05T12:00:00+00:00",
        "product": product,
        "executorId": f"{product}_direct_vulkan",
        "workloadContract": {
            "path": "bench/workloads/specialized/workloads.generic.json",
            "sha256": "a" * 64,
        },
        "benchmarkPolicy": {
            "path": "config/benchmark-methodology-thresholds.json",
            "schemaVersion": 1,
            "sha256": "b" * 64,
        },
        "workload": {
            "id": workload_id,
            "name": "test workload",
            "description": "unit test",
            "domain": "compute",
            "comparable": True,
            "benchmarkClass": "comparable",
            "comparabilityNotes": "test",
            "directionalReason": "",
            "pathAsymmetry": False,
            "pathAsymmetryNote": "",
            "includeByDefault": True,
            "asyncDiagnosticsMode": "",
            "strictNormalizationUnit": "",
            "comparabilityCandidate": {
                "enabled": False,
                "tier": "",
                "notes": "",
            },
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
            "allowNoExecution": product == "doe",
            "timingNormalizationNote": "",
            "comparabilityMode": "strict",
            "requiredTimingClass": "operation",
        },
        "host": {"os": "linux", "arch": "x86_64"},
        "commandSamples": [
            {
                "runIndex": i,
                "elapsedMs": 10.0 + i * 0.5 + (0 if product == "doe" else 2.0),
                "measuredMs": 8.0 + i * 0.3 + (0 if product == "doe" else 2.0),
                "timingSource": "doe-execution-total-ns",
                "timing": {"traceMetaSource": "doe-execution-total-ns"},
                "traceMeta": {
                    "executionDispatchCount": 1,
                    "executionRowCount": 1,
                    "executionSuccessCount": 1,
                    "executionTotalNs": 10_000_000,
                    "executionSetupTotalNs": 1_000_000,
                    "executionEncodeTotalNs": 3_000_000,
                    "executionSubmitWaitTotalNs": 2_000_000,
                },
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


def _benchmark_policy() -> object:
    return type(
        "Policy",
        (),
        {
            "source_path": "config/benchmark-methodology-thresholds.json",
            "min_dispatch_window_ns_without_encode": 1000,
            "min_dispatch_window_coverage_percent_without_encode": 0.5,
            "local_claim_min_timed_samples": 7,
            "release_claim_min_timed_samples": 15,
        },
    )()


def _legacy_args() -> Namespace:
    return Namespace(
        config="",
        iterations=4,
        warmup=0,
        workload_cooldown_ms=0,
        boundary="",
        runtime_host="",
        temperature="",
        comparison_view="",
        provider_set="",
        baseline_name="doe",
        baseline_provider_id="",
        baseline_executor_id="doe_direct_vulkan",
        comparison_name="dawn",
        comparison_provider_id="",
        comparison_executor_id="dawn_direct_vulkan",
        comparability="strict",
        require_timing_class="operation",
        allow_baseline_no_execution=False,
        resource_probe="none",
        resource_sample_ms=100,
        resource_sample_target_count=0,
        workload_cohort="all",
        selector={},
        claimability="off",
        claim_min_timed_samples=0,
        emit_shell=False,
    )


class TestCompareWorkloadFromArtifacts(unittest.TestCase):
    def test_basic_comparison(self) -> None:
        baseline = _make_artifact("doe")
        comparison = _make_artifact("dawn")
        entry = compare_workload_from_artifacts(
            baseline=baseline,
            comparison=comparison,
        )
        self.assertEqual(entry["id"], "compute_test")
        self.assertIn("baseline", entry["participants"])
        self.assertIn("comparison", entry["participants"])
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
        self.assertIn("baseline", report["participants"])
        self.assertIn("comparison", report["participants"])
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


class TestLegacyCompareFromArtifacts(unittest.TestCase):
    def test_groups_run_artifacts_by_workload(self) -> None:
        grouped = group_run_artifacts_by_workload(
            [_make_artifact("doe"), _make_artifact("dawn")]
        )
        self.assertEqual(sorted(grouped), ["compute_test"])
        self.assertIn("doe", grouped["compute_test"])
        self.assertIn("dawn", grouped["compute_test"])

    def test_builds_workload_proxy_from_artifacts(self) -> None:
        workload = workload_from_artifact_pair(
            baseline_artifact=_make_artifact("doe"),
            comparison_artifact=_make_artifact("dawn"),
        )
        self.assertEqual(workload.id, "compute_test")
        self.assertEqual(workload.baseline_command_repeat, 1)
        self.assertEqual(workload.comparison_command_repeat, 1)
        self.assertTrue(workload.include_by_default)

    def test_builds_legacy_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "dawn-vs-doe.json"
            workspace = Path(tmpdir) / "workspace"
            report, comparability_failures, claimability_failures = (
                build_legacy_compare_report_from_artifacts(
                    args=_legacy_args(),
                    artifacts=[_make_artifact("doe"), _make_artifact("dawn")],
                    baseline_product="doe",
                    comparison_product="dawn",
                    benchmark_policy=_benchmark_policy(),
                    output_timestamp="20260405T120000Z",
                    out=out_path,
                    workspace=workspace,
                    run_artifact_paths=["doe.run.json", "dawn.run.json"],
                )
            )
        self.assertEqual(report["schemaVersion"], 5)
        self.assertEqual(report["comparisonStatus"], "comparable")
        self.assertEqual(report["claimStatus"], "not-evaluated")
        self.assertEqual(len(report["workloads"]), 1)
        self.assertEqual(comparability_failures, [])
        self.assertEqual(claimability_failures, [])
        self.assertEqual(report["runArtifactPaths"], ["doe.run.json", "dawn.run.json"])


if __name__ == "__main__":
    unittest.main()
