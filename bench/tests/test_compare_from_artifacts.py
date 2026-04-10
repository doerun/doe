"""Tests for compare-only reports from run receipts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from native_compare_modules.claim_report import build_claim_report
from native_compare_modules.compare_from_artifacts import (
    COMPARE_REPORT_KIND,
    COMPARE_REPORT_SCHEMA_VERSION,
    build_compare_report,
    compare_workload_from_artifacts,
    group_run_artifacts_by_workload,
    receipt_run_view,
    write_compare_report,
)
from native_compare_modules.run_artifact import load_run_artifact


def _make_receipt(product: str, manifest_hash: str = "a" * 64) -> dict:
    measured_ms = 8.0 if product == "doe" else 10.0
    wall_ms = 9.0 if product == "doe" else 11.0
    return {
        "schemaVersion": 1,
        "artifactKind": "run-receipt",
        "generatedAt": "2026-04-09T12:00:00+00:00",
        "product": product,
        "executorId": f"{product}_direct_vulkan",
        "invocation": {
            "command": ["runtime/zig/zig-out/bin/doe-zig-runtime"],
            "iterations": 4,
            "warmup": 0,
            "resourceProbe": "none",
            "resourceSampleMs": 100,
            "resourceSampleTargetCount": 0,
        },
        "workloadManifest": {
            "path": "bench/workloads/workloads.package.gemma270m.json",
            "sha256": manifest_hash,
            "ownership": "standalone",
            "inputFreshness": "unknown",
            "freshnessReason": "standalone manifest; no backend workload catalog freshness check applies",
        },
        "workload": {
            "id": "compute_test",
            "name": "test workload",
            "description": "unit test",
            "domain": "compute",
            "commandsPath": "examples/test.json",
            "quirksPath": "examples/quirks/noop.json",
            "planPath": "",
            "vendor": "amd",
            "api": "metal",
            "family": "gfx11",
            "driver": "24.0.0",
            "comparable": True,
            "benchmarkClass": "comparable",
            "comparabilityNotes": "test",
            "directionalReason": "",
            "pathAsymmetry": False,
            "pathAsymmetryNote": "",
            "claimEligible": True,
            "strictNormalizationUnit": "",
        },
        "normalization": {
            "commandRepeat": 1,
            "ignoreFirstOps": 0,
            "timingDivisor": 2.0,
            "uploadBufferUsage": "copy-dst-copy-src",
            "uploadSubmitEvery": 1,
            "timingNormalizationNote": "",
            "allowNoExecution": False,
        },
        "runtimeIdentity": {
            "runtimeHost": "native",
            "binaryPath": "runtime/zig/zig-out/bin/doe-zig-runtime",
            "binarySha256": "b" * 64,
            "executionBackend": "doe_metal" if product == "doe" else "dawn_delegate",
            "providerId": product,
            "providerName": product,
            "packageName": "",
            "packageVersion": "",
            "packageLockHash": "",
        },
        "hostIdentity": {
            "hostname": "bench-host",
            "os": "linux",
            "kernel": "6.8.0",
            "arch": "x86_64",
            "api": "metal",
            "driver": "24.0.0",
            "adapter": {
                "vendor": "amd",
                "device": "gfx1100",
                "architecture": "rdna3",
                "description": "AMD Radeon Graphics",
            },
        },
        "execution": {
            "success": True,
            "timedSampleCount": 4,
            "returnCodes": [0],
            "timingSources": ["doe-execution-total-ns"],
            "timingClasses": ["operation"],
        },
        "samples": [
            {
                "runIndex": index,
                "command": ["runtime/zig/zig-out/bin/doe-zig-runtime"],
                "wallMs": wall_ms + index * 0.1,
                "measuredRawMs": measured_ms + index * 0.1,
                "measuredMs": measured_ms + index * 0.1,
                "timingSource": "doe-execution-total-ns",
                "timingClass": "operation",
                "timing": {
                    "commandRepeat": 1,
                    "timingNormalizationDivisor": 2.0,
                    "timingConfiguredDivisor": 2.0,
                    "workloadUnitNormalizationDivisor": 2.0,
                    "traceMetaSource": "doe-execution-total-ns",
                },
                "traceArtifacts": {
                    "jsonlPath": f"bench/out/{product}.{index}.ndjson",
                    "metaPath": f"bench/out/{product}.{index}.meta.json",
                },
                "subphasesMs": {
                    "executionMs": measured_ms + index * 0.1,
                    "setupMs": 1.0,
                    "encodeMs": 2.0,
                    "submitWaitMs": 3.0,
                    "gpuTimestampMs": None,
                },
                "resource": {},
                "returnCode": 0,
                "success": True,
                "commandRepeat": 1,
                "uploadIgnoreFirstOps": 0,
                "uploadBufferUsage": "copy-dst-copy-src",
                "uploadSubmitEvery": 1,
                "timingNormalizationDivisor": 2.0,
                "workloadUnitNormalizationDivisor": 2.0,
                "traceMeta": {
                    "executionDispatchCount": 1,
                    "executionRowCount": 1,
                    "executionSuccessCount": 1,
                    "executionTotalNs": int((measured_ms + index * 0.1) * 1_000_000),
                    "executionSetupTotalNs": 1_000_000,
                    "executionEncodeTotalNs": 2_000_000,
                    "executionSubmitWaitTotalNs": 3_000_000,
                    "executionBackend": "doe_metal" if product == "doe" else "dawn_delegate",
                },
            }
            for index in range(4)
        ],
    }


def _benchmark_policy() -> object:
    return type(
        "Policy",
        (),
        {
            "source_path": "config/benchmark-methodology-thresholds.json",
            "min_dispatch_window_ns_without_encode": 1000,
            "min_dispatch_window_coverage_percent_without_encode": 0.5,
            "local_claim_min_timed_samples": 3,
            "release_claim_min_timed_samples": 15,
            "min_operation_wall_coverage_ratio": 0.0,
            "max_operation_wall_coverage_asymmetry_ratio": 10.0,
            "min_row_timing_floor_ns": 0,
        },
    )()


class TestCompareFromArtifacts(unittest.TestCase):
    def test_compare_entry_is_compare_only(self) -> None:
        baseline = _make_receipt("doe")
        comparison = _make_receipt("dawn")
        entry = compare_workload_from_artifacts(
            baseline=baseline,
            comparison=comparison,
        )
        self.assertEqual(entry["id"], "compute_test")
        self.assertGreater(entry["deltaPercent"]["p50Percent"], 0)
        self.assertIn("comparability", entry)
        self.assertNotIn("claimability", entry)

    def test_manifest_mismatch_is_reported_not_raised(self) -> None:
        entry = compare_workload_from_artifacts(
            baseline=_make_receipt("doe", manifest_hash="a" * 64),
            comparison=_make_receipt("dawn", manifest_hash="b" * 64),
        )
        self.assertFalse(entry["workloadMatching"]["matched"])
        self.assertFalse(entry["comparability"]["comparable"])
        self.assertTrue(
            any("workload manifest hash mismatch" in reason for reason in entry["comparability"]["reasons"])
        )

    def test_build_compare_report_and_claim_report(self) -> None:
        baseline = _make_receipt("doe")
        comparison = _make_receipt("dawn")
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline_path = Path(tmpdir) / "doe.run.json"
            comparison_path = Path(tmpdir) / "dawn.run.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            comparison_path.write_text(json.dumps(comparison), encoding="utf-8")
            baseline_loaded = load_run_artifact(baseline_path)
            comparison_loaded = load_run_artifact(comparison_path)
            baseline_loaded["_receiptPath"] = str(baseline_path)
            comparison_loaded["_receiptPath"] = str(comparison_path)
            entry = compare_workload_from_artifacts(
                baseline=baseline_loaded,
                comparison=comparison_loaded,
            )
            report = build_compare_report(
                workload_entries=[entry],
                baseline_artifact=baseline_loaded,
                comparison_artifact=comparison_loaded,
                comparability_mode="strict",
                required_timing_class="operation",
                out_path=str(Path(tmpdir) / "sample.compare.json"),
                run_artifact_paths=[str(baseline_path), str(comparison_path)],
            )
            self.assertEqual(report["schemaVersion"], COMPARE_REPORT_SCHEMA_VERSION)
            self.assertEqual(report["artifactKind"], COMPARE_REPORT_KIND)
            self.assertEqual(report["comparisonStatus"], "comparable")
            self.assertNotIn("claimStatus", report)
            self.assertAlmostEqual(
                report["overallWorkloadUnitWall"]["baselineStatsMs"]["p50Ms"],
                4.55,
            )

            compare_path = Path(tmpdir) / "sample.compare.json"
            write_compare_report(report, compare_path)
            claim_report = build_claim_report(
                compare_report=report,
                compare_report_path=compare_path,
                benchmark_policy=_benchmark_policy(),
                mode="local",
                min_timed_samples=3,
            )
            self.assertEqual(claim_report["claimStatus"], "claimable")
            self.assertTrue(claim_report["pass"])

    def test_group_run_artifacts_by_workload(self) -> None:
        grouped = group_run_artifacts_by_workload(
            [_make_receipt("doe"), _make_receipt("dawn")]
        )
        self.assertEqual(sorted(grouped), ["compute_test"])
        self.assertIn("doe", grouped["compute_test"])
        self.assertIn("dawn", grouped["compute_test"])

    def test_receipt_run_view_exposes_legacy_stats(self) -> None:
        view = receipt_run_view(_make_receipt("doe"))
        self.assertEqual(view["stats"]["count"], 4)
        self.assertEqual(view["timingClasses"], ["operation"])
        self.assertEqual(
            view["commandSamples"][0]["timing"]["workloadUnitNormalizationDivisor"],
            2.0,
        )
        self.assertEqual(view["commandSamples"][0]["strictNormalizationUnit"], "")


if __name__ == "__main__":
    unittest.main()
