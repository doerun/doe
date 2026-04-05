"""Tests for run artifact build/load round-trip."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from native_compare_modules.run_artifact import (
    RUN_ARTIFACT_SCHEMA_VERSION,
    artifact_filename,
    build_run_artifact,
    load_run_artifact,
    write_run_artifact,
)
from native_compare_modules.workload_spec import ProductRunConfig, WorkloadSpec


def _make_spec() -> WorkloadSpec:
    return WorkloadSpec(
        id="compute_test",
        name="test workload",
        description="unit test workload",
        domain="compute",
        commands_path="examples/test.json",
        quirks_path="examples/quirks/noop.json",
        vendor="amd",
        api="vulkan",
        family="gfx11",
        driver="24.0.0",
        extra_args=[],
        comparable=True,
        benchmark_class="comparable",
        comparability_notes="test",
        path_asymmetry=False,
        path_asymmetry_note="",
        strict_normalization_unit="",
    )


def _make_run_config() -> ProductRunConfig:
    return ProductRunConfig(product="doe", command_repeat=1, timing_divisor=1.0)


def _make_run_result() -> dict:
    return {
        "commandSamples": [
            {"runIndex": 0, "elapsedMs": 10.0, "measuredMs": 8.0, "timingSource": "doe-execution-total-ns"},
            {"runIndex": 1, "elapsedMs": 11.0, "measuredMs": 9.0, "timingSource": "doe-execution-total-ns"},
        ],
        "stats": {"count": 2, "p50Ms": 8.5, "p95Ms": 9.0, "meanMs": 8.5},
        "timingsMs": [8.0, 9.0],
        "lastMeta": {"module": "doe-zig-runtime"},
        "timingSources": ["doe-execution-total-ns"],
        "timingClasses": ["operation"],
        "resourceStats": {},
        "timingMetricsRawStatsMs": {},
        "timingMetricsNormalizedStatsMs": {},
    }


class TestRunArtifactRoundTrip(unittest.TestCase):
    def test_build_artifact_has_required_fields(self) -> None:
        artifact = build_run_artifact(
            run_result=_make_run_result(),
            product="doe",
            executor_id="doe_direct_vulkan",
            workload_spec=_make_spec(),
            run_config=_make_run_config(),
            iterations=2,
            warmup=0,
        )
        self.assertEqual(artifact["schemaVersion"], RUN_ARTIFACT_SCHEMA_VERSION)
        self.assertEqual(artifact["artifactKind"], "run")
        self.assertEqual(artifact["product"], "doe")
        self.assertEqual(artifact["executorId"], "doe_direct_vulkan")
        self.assertEqual(artifact["workload"]["id"], "compute_test")
        self.assertEqual(artifact["runParameters"]["iterations"], 2)
        self.assertEqual(len(artifact["commandSamples"]), 2)
        self.assertEqual(len(artifact["timingsMs"]), 2)

    def test_write_and_load_round_trip(self) -> None:
        artifact = build_run_artifact(
            run_result=_make_run_result(),
            product="doe",
            executor_id="doe_direct_vulkan",
            workload_spec=_make_spec(),
            run_config=_make_run_config(),
            iterations=2,
            warmup=0,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.run.json"
            write_run_artifact(artifact, path)
            loaded = load_run_artifact(path)
            self.assertEqual(loaded["product"], "doe")
            self.assertEqual(loaded["workload"]["id"], "compute_test")
            self.assertEqual(len(loaded["timingsMs"]), 2)

    def test_load_rejects_wrong_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text(json.dumps({"artifactKind": "report", "schemaVersion": 1}))
            with self.assertRaises(ValueError):
                load_run_artifact(path)

    def test_load_rejects_wrong_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text(json.dumps({"artifactKind": "run", "schemaVersion": 999}))
            with self.assertRaises(ValueError):
                load_run_artifact(path)

    def test_load_rejects_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_run_artifact("/nonexistent/path.json")

    def test_artifact_filename(self) -> None:
        name = artifact_filename("doe", "compute_test", "20260405T120000Z")
        self.assertEqual(name, "doe-compute_test-20260405T120000Z.run.json")


class TestWorkloadSpecShim(unittest.TestCase):
    def test_to_spec_and_configs(self) -> None:
        from native_compare_modules.config_support import Workload

        wl = Workload(
            id="test",
            name="test",
            description="test",
            domain="compute",
            comparability_notes="test",
            commands_path="test.json",
            quirks_path="noop.json",
            vendor="amd",
            api="vulkan",
            family="gfx11",
            driver="24.0.0",
            extra_args=[],
            left_command_repeat=5,
            right_command_repeat=10,
            left_ignore_first_ops=1,
            right_ignore_first_ops=2,
            left_upload_buffer_usage="copy-dst",
            right_upload_buffer_usage="copy-dst-copy-src",
            left_upload_submit_every=1,
            right_upload_submit_every=2,
            dawn_filter="@autodiscover",
            comparable=True,
            benchmark_class="comparable",
            directional_reason="",
            allow_left_no_execution=True,
            include_by_default=True,
            left_timing_divisor=1.0,
            right_timing_divisor=2.0,
            timing_normalization_note="test note",
            async_diagnostics_mode="",
            comparability_candidate=False,
            comparability_candidate_tier="",
            comparability_candidate_notes="",
            path_asymmetry=False,
            path_asymmetry_note="",
            strict_normalization_unit="",
        )

        spec, configs = wl.to_spec_and_configs("doe", "dawn")
        self.assertEqual(spec.id, "test")
        self.assertEqual(spec.domain, "compute")
        self.assertEqual(spec.comparable, True)
        self.assertEqual(configs["doe"].command_repeat, 5)
        self.assertEqual(configs["doe"].ignore_first_ops, 1)
        self.assertEqual(configs["doe"].allow_no_execution, True)
        self.assertEqual(configs["dawn"].command_repeat, 10)
        self.assertEqual(configs["dawn"].timing_divisor, 2.0)
        self.assertEqual(configs["dawn"].dawn_filter, "@autodiscover")


if __name__ == "__main__":
    unittest.main()
