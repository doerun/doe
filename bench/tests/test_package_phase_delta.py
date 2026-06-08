"""Tests for package phase delta receipt analysis."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bench.tools import package_phase_delta as phase_delta


def _sample(
    measured_ms: float,
    setup_ns: dict[str, int],
    step_ns: dict[str, int],
) -> dict:
    return {
        "success": True,
        "measuredMs": measured_ms,
        "wallMs": measured_ms + 1.0,
        "traceMeta": {
            "packageSetupBreakdownNs": setup_ns,
            "packageStepBreakdownNs": step_ns,
        },
    }


def _artifact(workload_id: str, samples: list[dict]) -> dict:
    return {
        "schemaVersion": 1,
        "artifactKind": "run-receipt",
        "product": "doe",
        "executorId": "doe_gpu_node_package",
        "invocation": {},
        "workloadManifest": {},
        "workload": {"id": workload_id},
        "normalization": {},
        "runtimeIdentity": {"runtimeHost": "node"},
        "hostIdentity": {},
        "execution": {},
        "samples": samples,
    }


def _write_artifact(root: Path, name: str, artifact: dict) -> Path:
    path = root / name
    path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


class TestPackagePhaseDelta(unittest.TestCase):
    def test_compare_summaries_reports_timing_and_phase_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline_path = _write_artifact(
                root,
                "baseline.run.json",
                _artifact(
                    "package_vector_scale_add_1m",
                    [
                        _sample(
                            1.0,
                            {"bufferCreateTotalNs": 1_000_000},
                            {"dispatchEncodeApiTotalNs": 100_000},
                        ),
                        _sample(
                            2.0,
                            {"bufferCreateTotalNs": 2_000_000},
                            {"dispatchEncodeApiTotalNs": 200_000},
                        ),
                        _sample(
                            3.0,
                            {"bufferCreateTotalNs": 3_000_000},
                            {"dispatchEncodeApiTotalNs": 300_000},
                        ),
                    ],
                ),
            )
            comparison_path = _write_artifact(
                root,
                "comparison.run.json",
                _artifact(
                    "package_vector_scale_add_1m",
                    [
                        _sample(
                            4.0,
                            {"bufferCreateTotalNs": 4_000_000},
                            {"dispatchEncodeApiTotalNs": 400_000},
                        ),
                        _sample(
                            5.0,
                            {"bufferCreateTotalNs": 5_000_000},
                            {"dispatchEncodeApiTotalNs": 500_000},
                        ),
                        _sample(
                            6.0,
                            {"bufferCreateTotalNs": 6_000_000},
                            {"dispatchEncodeApiTotalNs": 600_000},
                        ),
                    ],
                ),
            )

            baseline = phase_delta.summarize_artifact_set(
                phase_delta.ArtifactSet(
                    label="doe",
                    paths=[baseline_path],
                    artifacts=[phase_delta.load_run_artifact(baseline_path)],
                )
            )
            comparison = phase_delta.summarize_artifact_set(
                phase_delta.ArtifactSet(
                    label="node-webgpu",
                    paths=[comparison_path],
                    artifacts=[phase_delta.load_run_artifact(comparison_path)],
                )
            )

        report = phase_delta.compare_summaries(baseline, comparison)
        workload = report["workloads"]["package_vector_scale_add_1m"]
        self.assertEqual(
            workload["timing"]["comparisonMinusBaselineP50Ms"],
            3.0,
        )
        self.assertEqual(
            workload["setup"][0]["comparisonMinusBaselineP50Ms"],
            3.0,
        )
        self.assertEqual(
            workload["step"][0]["comparisonMinusBaselineP50Ms"],
            0.3,
        )
        derived = {
            row["phase"]: row
            for row in workload["derived"]
        }
        self.assertEqual(
            derived["setupTotalNs"]["comparisonMinusBaselineP50Ms"],
            3.0,
        )
        self.assertEqual(
            derived["stepSelectedTotalNs"]["comparisonMinusBaselineP50Ms"],
            0.3,
        )
        self.assertEqual(report["phaseGaps"][0]["section"], "timing")

    def test_derived_breakdowns_group_setup_and_step_buckets(self) -> None:
        values = phase_delta._derived_breakdown_values(
            {
                "bufferCreateTotalNs": 1_000_000,
                "initialDataWriteTotalNs": 2_000_000,
                "shaderModuleCreateTotalNs": 3_000_000,
                "bindGroupLayoutCreateTotalNs": 4_000_000,
                "pipelineLayoutCreateTotalNs": 5_000_000,
                "pipelineCreateTotalNs": 6_000_000,
                "bindGroupCreateTotalNs": 7_000_000,
            },
            {
                "writeMaterializeTotalNs": 8_000_000,
                "writeQueueWriteTotalNs": 9_000_000,
                "dispatchEncodeApiTotalNs": 10_000_000,
                "copyEncodeApiTotalNs": 11_000_000,
                "submitCommandEncoderFinishTotalNs": 12_000_000,
                "submitQueueSubmitTotalNs": 13_000_000,
                "submitQueueWaitTotalNs": 14_000_000,
                "readbackTotalNs": 15_000_000,
                "submitCommandPrepTotalNs": 16_000_000,
                "submitAddonCallTotalNs": 17_000_000,
                "submitPostSubmitBookkeepingTotalNs": 18_000_000,
                "submitQueueWaitBookkeepingTotalNs": 19_000_000,
                "submitAddonCommandReplayTotalNs": 20_000_000,
                "submitAddonCommandReplayPrepareTotalNs": 38_000_000,
                "submitAddonCommandReplayRecordTotalNs": 39_000_000,
                "submitAddonCommandReplayCopyTotalNs": 40_000_000,
                "submitAddonQueueSubmitTotalNs": 21_000_000,
                "submitAddonCommandBufferEndTotalNs": 35_000_000,
                "submitAddonSyncPrepareTotalNs": 36_000_000,
                "submitAddonDriverSubmitTotalNs": 37_000_000,
                "submitAddonFlushTotalNs": 22_000_000,
                "submitQueueFlushTotalNs": 23_000_000,
                "submitQueueFlushWaitCompletedTotalNs": 24_000_000,
                "submitQueueFlushDeferredCopyTotalNs": 25_000_000,
                "submitQueueFlushDeferredResolveTotalNs": 26_000_000,
                "readbackMapReadCopyUnmapTotalNs": 27_000_000,
                "readbackMapAsyncTotalNs": 28_000_000,
                "readbackGetMappedRangeTotalNs": 29_000_000,
                "readbackHostCopyTotalNs": 30_000_000,
                "readbackNativeReadCopyTotalNs": 31_000_000,
                "readbackUnmapTotalNs": 32_000_000,
                "readbackValidationTotalNs": 33_000_000,
                "readbackCaptureTotalNs": 34_000_000,
            },
        )

        self.assertEqual(values["setupTotalNs"], 28.0)
        self.assertEqual(values["setupBufferDataTotalNs"], 3.0)
        self.assertEqual(values["setupShaderPipelineTotalNs"], 14.0)
        self.assertEqual(values["setupBindingTotalNs"], 11.0)
        self.assertEqual(values["stepSelectedTotalNs"], 92.0)
        self.assertEqual(values["stepSubmitApiEnvelopeNs"], 39.0)
        self.assertEqual(values["stepDoeSubmitWrapperNs"], 70.0)
        self.assertEqual(values["stepDoeSubmitNativeBreakdownNs"], 386.0)
        self.assertEqual(values["stepReadbackTotalNs"], 15.0)
        self.assertEqual(values["stepReadbackApiEnvelopeNs"], 177.0)
        self.assertEqual(values["stepReadbackHarnessNs"], 67.0)
        self.assertEqual(values["stepReadbackValidationNs"], 33.0)
        self.assertEqual(values["stepReadbackCaptureNs"], 34.0)

    def test_phase_breakdowns_follow_timing_normalization_divisor(self) -> None:
        sample = _sample(
            2.0,
            {"bufferCreateTotalNs": 10_000_000},
            {"dispatchEncodeApiTotalNs": 4_000_000},
        )
        sample["timingNormalizationDivisor"] = 5
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_artifact(
                root,
                "repeat.run.json",
                _artifact("package_repeat", [sample]),
            )
            summary = phase_delta.summarize_artifact_set(
                phase_delta.ArtifactSet(
                    label="doe",
                    paths=[path],
                    artifacts=[phase_delta.load_run_artifact(path)],
                )
            )

        workload = summary["workloads"]["package_repeat"]
        self.assertEqual(
            workload["setupBreakdownMs"]["bufferCreateTotalNs"]["p50Ms"],
            2.0,
        )
        self.assertEqual(
            workload["stepBreakdownMs"]["dispatchEncodeApiTotalNs"]["p50Ms"],
            0.8,
        )
        self.assertEqual(
            workload["derivedBreakdownMs"]["setupTotalNs"]["p50Ms"],
            2.0,
        )

    def test_duplicate_workload_receipts_are_aggregated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_path = _write_artifact(
                root,
                "first.run.json",
                _artifact(
                    "package_repeat",
                    [
                        _sample(
                            1.0,
                            {"bufferCreateTotalNs": 1_000_000},
                            {"dispatchEncodeApiTotalNs": 1_000_000},
                        )
                    ],
                ),
            )
            second_path = _write_artifact(
                root,
                "second.run.json",
                _artifact(
                    "package_repeat",
                    [
                        _sample(
                            5.0,
                            {"bufferCreateTotalNs": 5_000_000},
                            {"dispatchEncodeApiTotalNs": 5_000_000},
                        )
                    ],
                ),
            )
            third_path = _write_artifact(
                root,
                "third.run.json",
                _artifact(
                    "package_repeat",
                    [
                        _sample(
                            9.0,
                            {"bufferCreateTotalNs": 9_000_000},
                            {"dispatchEncodeApiTotalNs": 9_000_000},
                        )
                    ],
                ),
            )
            summary = phase_delta.summarize_artifact_set(
                phase_delta.ArtifactSet(
                    label="doe",
                    paths=[first_path, second_path, third_path],
                    artifacts=[
                        phase_delta.load_run_artifact(first_path),
                        phase_delta.load_run_artifact(second_path),
                        phase_delta.load_run_artifact(third_path),
                    ],
                )
            )

        workload = summary["workloads"]["package_repeat"]
        self.assertEqual(workload["artifactCount"], 3)
        self.assertEqual(workload["sampleCount"], 3)
        self.assertEqual(len(workload["paths"]), 3)
        self.assertEqual(workload["timing"]["measuredMs"]["p50Ms"], 5.0)
        self.assertEqual(
            workload["stepBreakdownMs"]["dispatchEncodeApiTotalNs"]["p50Ms"],
            5.0,
        )

    def test_write_breakdown_follows_timing_normalization_divisor(self) -> None:
        sample = _sample(
            2.0,
            {},
            {},
        )
        sample["timingNormalizationDivisor"] = 2
        sample["traceMeta"]["packageWriteBreakdown"] = {
            "totalCount": 20,
            "totalBytes": 2048,
            "staticBufferLoadCount": 14,
            "staticBufferLoadBytes": 2000,
            "dynamicWriteCount": 6,
            "dynamicWriteBytes": 48,
            "byDataKind": {
                "file": {"count": 14, "bytes": 2000},
                "u32": {"count": 6, "bytes": 48},
            },
            "bySemanticPhase": {
                "buffer_load": {"count": 14, "bytes": 2000},
                "dynamic_write": {"count": 6, "bytes": 48},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_artifact(
                root,
                "write-breakdown.run.json",
                _artifact("package_repeat", [sample]),
            )
            summary = phase_delta.summarize_artifact_set(
                phase_delta.ArtifactSet(
                    label="doe",
                    paths=[path],
                    artifacts=[phase_delta.load_run_artifact(path)],
                )
            )

        write_breakdown = summary["workloads"]["package_repeat"]["writeBreakdown"]
        self.assertEqual(write_breakdown["totalCount"]["p50"], 10.0)
        self.assertEqual(write_breakdown["totalBytes"]["p50"], 1024.0)
        self.assertEqual(write_breakdown["byDataKind.file.bytes"]["p50"], 1000.0)
        self.assertEqual(write_breakdown["byDataKind.u32.count"]["p50"], 3.0)
        self.assertEqual(write_breakdown["bySemanticPhase.dynamic_write.bytes"]["p50"], 24.0)

    def test_resident_buffer_load_breakdown_follows_timing_normalization_divisor(self) -> None:
        sample = _sample(
            2.0,
            {},
            {},
        )
        sample["timingNormalizationDivisor"] = 2
        sample["traceMeta"]["packageResidentBufferLoadBreakdown"] = {
            "count": 14,
            "bytes": 2000,
            "materializeTotalNs": 10_000_000,
            "queueWriteTotalNs": 8_000_000,
            "queueWaitTotalNs": 2_000_000,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_artifact(
                root,
                "resident-breakdown.run.json",
                _artifact("package_repeat", [sample]),
            )
            summary = phase_delta.summarize_artifact_set(
                phase_delta.ArtifactSet(
                    label="doe",
                    paths=[path],
                    artifacts=[phase_delta.load_run_artifact(path)],
                )
            )

        workload = summary["workloads"]["package_repeat"]
        resident_counts = workload["residentBufferLoadBreakdown"]
        resident_timing = workload["residentBufferLoadBreakdownMs"]
        amortized_counts = workload["residentBufferLoadBreakdownAmortized"]
        amortized_timing = workload["residentBufferLoadBreakdownAmortizedMs"]
        self.assertEqual(resident_counts["count"]["p50"], 14.0)
        self.assertEqual(resident_counts["bytes"]["p50"], 2000.0)
        self.assertEqual(resident_timing["materializeTotalNs"]["p50Ms"], 10.0)
        self.assertEqual(resident_timing["queueWriteTotalNs"]["p50Ms"], 8.0)
        self.assertEqual(resident_timing["queueWaitTotalNs"]["p50Ms"], 2.0)
        self.assertEqual(amortized_counts["count"]["p50"], 7.0)
        self.assertEqual(amortized_counts["bytes"]["p50"], 1000.0)
        self.assertEqual(amortized_timing["materializeTotalNs"]["p50Ms"], 5.0)
        self.assertEqual(amortized_timing["queueWriteTotalNs"]["p50Ms"], 4.0)
        self.assertEqual(amortized_timing["queueWaitTotalNs"]["p50Ms"], 1.0)

    def test_compare_summaries_requires_matching_workloads(self) -> None:
        baseline = {
            "label": "doe",
            "workloads": {"one": {"timing": {}, "setupBreakdownMs": {}}},
        }
        comparison = {
            "label": "node-webgpu",
            "workloads": {"two": {"timing": {}, "setupBreakdownMs": {}}},
        }
        with self.assertRaises(ValueError):
            phase_delta.compare_summaries(baseline, comparison)

    def test_resolve_patterns_fails_when_glob_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pattern = str(Path(tmp) / "*.run.json")
            with self.assertRaises(FileNotFoundError):
                phase_delta.resolve_patterns([pattern])

    def test_format_text_report_includes_sign_convention(self) -> None:
        report = {
            "baseline": {"label": "doe"},
            "comparison": {"label": "node-webgpu"},
            "phaseGaps": [
                {
                    "workloadId": "package_vector_scale_add_1m",
                    "section": "step",
                    "phase": "dispatchEncodeApiTotalNs",
                    "baselineP50Ms": 0.2,
                    "comparisonP50Ms": 0.5,
                    "comparisonMinusBaselineP50Ms": 0.3,
                    "baselineDeltaPctOfComparison": 60.0,
                }
            ],
        }
        text = phase_delta.format_text_report(report, top=1)
        self.assertIn("positive delta means baseline", text)
        self.assertIn("dispatchEncodeApiTotalNs", text)


if __name__ == "__main__":
    unittest.main()
