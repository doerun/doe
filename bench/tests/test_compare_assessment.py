#!/usr/bin/env python3
"""Tests for per-workload compare assessment obligations."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
if str(BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(BENCH_ROOT))

from native_compare_modules.comparability import compare_assessment  # noqa: E402


def _sample(*, backend: str, command_replay_ns: int) -> dict:
    return {
        "runIndex": 0,
        "measuredMs": 1.0,
        "timingSource": "doe-execution-total-ns",
        "timingClass": "operation",
        "timing": {
            "traceMetaSource": "doe-execution-total-ns",
        },
        "traceMeta": {
            "executionBackend": backend,
            "executionTotalNs": 10_000_000,
            "executionSetupTotalNs": 2_000_000,
            "executionEncodeTotalNs": 1_000_000,
            "executionSubmitWaitTotalNs": 7_000_000,
            "executionDispatchCount": 1,
            "executionRowCount": 3,
            "executionSuccessCount": 3,
            "queueSyncMode": "per-command",
            "packageStepBreakdownNs": {
                "submitAddonCommandReplayTotalNs": command_replay_ns,
                "submitAddonFlushTotalNs": 0,
                "submitQueueWaitTotalNs": 0,
            },
            "adapterInfo": {
                "vendor": "apple",
                "device": "Apple M3",
                "architecture": "M3",
                "description": "Apple M3",
            },
        },
    }


def _wall_coverage_sample(
    *,
    backend: str,
    measured_ms: float,
    elapsed_ms: float,
) -> dict:
    sample = _sample(backend=backend, command_replay_ns=0)
    sample["measuredMs"] = measured_ms
    sample["elapsedMs"] = elapsed_ms
    sample["timing"]["workloadUnitNormalizationDivisor"] = 1.0
    return sample


class CompareAssessmentTests(unittest.TestCase):
    def test_submit_scope_mismatch_is_advisory_for_package_totals(self) -> None:
        result = compare_assessment(
            workload_id="package_upload_readback",
            workload_comparable=True,
            workload_domain="upload-readback",
            workload_api="webgpu",
            workload_commands_path="",
            workload_path_asymmetry=False,
            workload_path_asymmetry_note="",
            baseline_command_repeat=1,
            comparison_command_repeat=1,
            baseline={
                "commandSamples": [
                    _sample(backend="doe_node_webgpu", command_replay_ns=2_000_000)
                    for _ in range(7)
                ],
            },
            comparison={
                "commandSamples": [
                    _sample(backend="node_webgpu_package", command_replay_ns=0)
                    for _ in range(7)
                ],
            },
            required_timing_class="operation",
            allow_baseline_no_execution=False,
            resource_probe="none",
            comparability_mode="strict",
            resource_sample_target_count=0,
        )

        self.assertTrue(result["comparable"])
        self.assertNotIn(
            "baseline_comparison_submit_scope_match",
            result["blockingFailedObligations"],
        )
        self.assertIn(
            "baseline_comparison_submit_scope_match",
            result["advisoryFailedObligations"],
        )

    def test_timing_plausibility_allows_symmetric_low_operation_coverage(self) -> None:
        result = compare_assessment(
            workload_id="package_image_rgba_invert_1024",
            workload_comparable=True,
            workload_domain="surface",
            workload_api="webgpu",
            workload_commands_path="",
            workload_path_asymmetry=False,
            workload_path_asymmetry_note="",
            baseline_command_repeat=1,
            comparison_command_repeat=1,
            baseline={
                "commandSamples": [
                    _wall_coverage_sample(
                        backend="doe_bun_package",
                        measured_ms=0.05,
                        elapsed_ms=10.0,
                    )
                    for _ in range(7)
                ],
            },
            comparison={
                "commandSamples": [
                    _wall_coverage_sample(
                        backend="bun_webgpu_package",
                        measured_ms=0.06,
                        elapsed_ms=12.0,
                    )
                    for _ in range(7)
                ],
            },
            required_timing_class="operation",
            allow_baseline_no_execution=False,
            resource_probe="none",
            comparability_mode="strict",
            resource_sample_target_count=0,
        )

        self.assertTrue(result["comparable"], result["reasons"])
        self.assertNotIn(
            "baseline_comparison_timing_plausibility",
            result["blockingFailedObligations"],
        )

    def test_timing_plausibility_blocks_asymmetric_low_operation_coverage(self) -> None:
        result = compare_assessment(
            workload_id="package_image_rgba_invert_1024",
            workload_comparable=True,
            workload_domain="surface",
            workload_api="webgpu",
            workload_commands_path="",
            workload_path_asymmetry=False,
            workload_path_asymmetry_note="",
            baseline_command_repeat=1,
            comparison_command_repeat=1,
            baseline={
                "commandSamples": [
                    _wall_coverage_sample(
                        backend="doe_bun_package",
                        measured_ms=0.05,
                        elapsed_ms=10.0,
                    )
                    for _ in range(7)
                ],
            },
            comparison={
                "commandSamples": [
                    _wall_coverage_sample(
                        backend="bun_webgpu_package",
                        measured_ms=0.75,
                        elapsed_ms=12.0,
                    )
                    for _ in range(7)
                ],
            },
            required_timing_class="operation",
            allow_baseline_no_execution=False,
            resource_probe="none",
            comparability_mode="strict",
            resource_sample_target_count=0,
        )

        self.assertFalse(result["comparable"])
        self.assertIn(
            "baseline_comparison_timing_plausibility",
            result["blockingFailedObligations"],
        )


if __name__ == "__main__":
    unittest.main()
