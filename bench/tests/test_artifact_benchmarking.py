#!/usr/bin/env python3
"""Tests for artifact-first product bundle execution."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.native_compare_modules.artifact_benchmarking import run_product_bundle


class _FakeWorkload:
    def __init__(self) -> None:
        self.id = "alpha"
        self.runner_type = "zig-runtime"
        self.calls: list[tuple[str, str]] = []

    def to_spec_and_configs(
        self,
        baseline_product: str = "doe",
        comparison_product: str = "dawn",
    ) -> tuple[SimpleNamespace, dict[str, SimpleNamespace]]:
        self.calls.append((baseline_product, comparison_product))
        return (
            SimpleNamespace(id=self.id),
            {
                baseline_product: SimpleNamespace(
                    product=baseline_product,
                    command_repeat=1,
                    ignore_first_ops=0,
                    upload_buffer_usage="copy-dst-copy-src",
                    upload_submit_every=1,
                    timing_divisor=1.0,
                    allow_no_execution=False,
                    dawn_filter="",
                    timing_normalization_note="",
                ),
                comparison_product: SimpleNamespace(
                    product=comparison_product,
                    command_repeat=2,
                    ignore_first_ops=0,
                    upload_buffer_usage="copy-dst-copy-src",
                    upload_submit_every=1,
                    timing_divisor=1.0,
                    allow_no_execution=False,
                    dawn_filter="",
                    timing_normalization_note="",
                ),
            },
        )


class ArtifactBenchmarkingTests(unittest.TestCase):
    @patch("bench.native_compare_modules.artifact_benchmarking.output_paths.write_run_manifest_for_outputs")
    @patch("bench.native_compare_modules.artifact_benchmarking.write_run_artifact")
    @patch("bench.native_compare_modules.artifact_benchmarking.build_run_artifact")
    @patch("bench.native_compare_modules.artifact_benchmarking.run_workload")
    def test_auto_role_uses_doe_as_baseline_and_non_doe_as_comparison(
        self,
        mock_run_workload,
        mock_build_run_artifact,
        mock_write_run_artifact,
        _mock_write_manifest,
    ) -> None:
        mock_run_workload.return_value = {"commandSamples": [], "stats": {}}
        mock_build_run_artifact.return_value = {"artifactKind": "run"}
        mock_write_run_artifact.side_effect = lambda _artifact, path: path
        workload = _FakeWorkload()
        with tempfile.TemporaryDirectory(prefix="doe-artifact-bundle-") as tmpdir:
            workspace = Path(tmpdir)
            written = run_product_bundle(
                product="doe",
                display_name="doe",
                executor_id="doe_node_webgpu",
                template="node bench/executors/run-node-webgpu-plan.js --plan {plan}",
                workloads=[workload],
                iterations=1,
                warmup=0,
                workspace=workspace,
                workload_contract_path=REPO_ROOT / "bench" / "workloads" / "workloads.apple.metal.json",
                gpu_memory_probe="none",
                resource_sample_ms=100,
                resource_sample_target_count=0,
                required_timing_class="operation",
                comparability_mode="strict",
                benchmark_policy=SimpleNamespace(source_path=""),
                workload_cooldown_ms=0,
                emit_shell=False,
                timestamp="20260406T000000Z",
            )
        self.assertEqual(len(written), 1)
        self.assertEqual(workload.calls, [("doe", "doe__comparison")])
        self.assertEqual(mock_build_run_artifact.call_args.kwargs["run_config"].product, "doe")

        workload = _FakeWorkload()
        with tempfile.TemporaryDirectory(prefix="doe-artifact-bundle-") as tmpdir:
            workspace = Path(tmpdir)
            run_product_bundle(
                product="node_webgpu_package",
                display_name="node_webgpu_package",
                executor_id="node_webgpu_package",
                template="node bench/executors/run-node-webgpu-plan.js --plan {plan}",
                workloads=[workload],
                iterations=1,
                warmup=0,
                workspace=workspace,
                workload_contract_path=REPO_ROOT / "bench" / "workloads" / "workloads.apple.metal.json",
                gpu_memory_probe="none",
                resource_sample_ms=100,
                resource_sample_target_count=0,
                required_timing_class="operation",
                comparability_mode="strict",
                benchmark_policy=SimpleNamespace(source_path=""),
                workload_cooldown_ms=0,
                emit_shell=False,
                timestamp="20260406T000000Z",
            )
        self.assertEqual(workload.calls, [("node_webgpu_package__baseline", "node_webgpu_package")])
        self.assertEqual(mock_build_run_artifact.call_args.kwargs["run_config"].product, "node_webgpu_package")


if __name__ == "__main__":
    unittest.main()
