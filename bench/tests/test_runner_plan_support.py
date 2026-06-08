#!/usr/bin/env python3
"""Tests for plan-aware native compare runner helpers."""

from __future__ import annotations

import json
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

from bench.native_compare_modules.runner import (
    command_for,
    extract_timing_metrics_ms,
    materialize_repeated_plan,
    run_workload,
    run_compilation_workload,
    trace_meta_records_terminal_execution_outcome,
    workload_unit_wall_from_trace_meta,
)
from bench.native_compare_modules.comparability_upload_contract import (
    verify_fawn_upload_runtime_contract,
)
from bench.native_compare_modules.workload_validation import (
    infer_workload_queue_sync_mode,
)
from bench.native_compare_modules.workload_validation import (
    enforce_strict_plan_boundary_symmetry,
)


class _Workload:
    quirks_path = "examples/quirks/noop.json"
    vendor = "apple"
    api = "metal"
    family = "m3"
    driver = "1.0.0"
    dawn_filter = "alpha"


class _UploadWorkload(_Workload):
    id = "upload_alpha"
    domain = "upload"
    commands_path = "bench/commands/upload_alpha.commands.json"
    plan_path = "bench/plans/upload_alpha.plan.json"
    extra_args: list[str] = []
    baseline_upload_buffer_usage = "copy-dst"
    baseline_upload_submit_every = 1


class _PlanOnlyWorkload(_Workload):
    id = "package_pipeline_creation_8kernels"
    domain = "pipeline"
    commands_path = ""
    plan_path = str(REPO_ROOT / "bench/plans/package-developer/package_pipeline_creation_8kernels.plan.json")
    extra_args: list[str] = []
    comparable = True
    strict_normalization_unit = "cycle"


class RunnerPlanSupportTests(unittest.TestCase):
    def test_materialize_repeated_plan_repeats_steps_and_summary(self) -> None:
        payload = {
            "schemaVersion": 1,
            "workloadId": "alpha",
            "steps": [{"kind": "write-buffer"}, {"kind": "dispatch"}],
            "summary": {
                "stepCount": 2,
                "operationCount": 2,
                "dispatchCount": 1,
                "bufferWriteCount": 1,
                "bufferLoadCount": 1,
            },
            "bufferLoadCount": 1,
        }
        with tempfile.TemporaryDirectory(prefix="doe-runner-plan-") as tmpdir:
            source = Path(tmpdir) / "alpha.plan.json"
            out_dir = Path(tmpdir) / "out"
            source.write_text(json.dumps(payload), encoding="utf-8")
            repeated_path = materialize_repeated_plan(
                str(source),
                repeat=3,
                out_dir=out_dir,
                side_name="comparison",
            )
            repeated = json.loads(Path(repeated_path).read_text(encoding="utf-8"))
            self.assertEqual(len(repeated["steps"]), 6)
            self.assertEqual(repeated["summary"]["stepCount"], 6)
            self.assertEqual(repeated["summary"]["dispatchCount"], 3)
            self.assertEqual(repeated["summary"]["bufferWriteCount"], 3)
            self.assertEqual(repeated["summary"]["bufferLoadCount"], 3)
            self.assertEqual(repeated["bufferLoadCount"], 3)

    def test_command_for_supports_plan_placeholder(self) -> None:
        command = command_for(
            "node bench/executors/run-node-webgpu-plan.js --plan {plan} --trace-meta {trace_meta} --trace-jsonl {trace_jsonl} --workload {workload} --command-repeat {command_repeat}",
            workload=_Workload(),
            workload_id="alpha",
            commands_path="",
            plan_path="bench/plans/alpha.plan.json",
            trace_jsonl=Path("tmp/trace.ndjson"),
            trace_meta=Path("tmp/trace.meta.json"),
            queue_sync_mode="per-command",
            upload_buffer_usage="copy-dst-copy-src",
            upload_submit_every=1,
            extra_args=[],
            command_repeat=5,
        )
        self.assertIn("bench/executors/run-node-webgpu-plan.js", command[1])
        self.assertIn("bench/plans/alpha.plan.json", command)
        self.assertIn("--command-repeat", command)
        self.assertIn("5", command)

    def test_run_workload_leaves_plan_files_unexpanded_when_executor_consumes_repeat(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-runner-repeat-") as tmpdir:
            result = run_workload(
                name="node-webgpu",
                template=(
                    "node bench/executors/run-node-webgpu-plan.js "
                    "--plan {plan} --trace-meta {trace_meta} --trace-jsonl {trace_jsonl} "
                    "--workload {workload} --command-repeat {command_repeat}"
                ),
                workload=_PlanOnlyWorkload(),
                iterations=1,
                warmup=0,
                out_dir=Path(tmpdir),
                gpu_memory_probe="none",
                resource_sample_ms=100,
                resource_sample_target_count=0,
                timing_divisor=5.0,
                command_repeat=5,
                ignore_first_ops=0,
                upload_buffer_usage="copy-dst-copy-src",
                upload_submit_every=1,
                inject_upload_runtime_flags=False,
                required_timing_class="operation",
                comparability_mode="strict",
                benchmark_policy=SimpleNamespace(),
                emit_shell=True,
            )
        command = result["commandSamples"][0]["command"]
        self.assertIn("--command-repeat", command)
        self.assertIn("5", command)
        self.assertIn(_PlanOnlyWorkload.plan_path, command)

    def test_verify_fawn_upload_runtime_contract_passes_plan_path_to_command_builder(self) -> None:
        captured: dict[str, object] = {}

        def fake_command_for(template: str, **kwargs: object) -> list[str]:
            captured["template"] = template
            captured.update(kwargs)
            return ["echo", "not-a-runtime"]

        verify_fawn_upload_runtime_contract(
            template="runtime/zig/zig-out/bin/doe-zig-runtime --plan {plan}",
            workload=_UploadWorkload(),
            command_for_fn=fake_command_for,
            runtime_source_paths=(),
        )

        self.assertEqual(captured["plan_path"], "bench/plans/upload_alpha.plan.json")

    def test_infer_workload_queue_sync_mode_defaults_uploads_to_deferred(self) -> None:
        upload = SimpleNamespace(domain="upload", extra_args=[])
        compute = SimpleNamespace(domain="compute", extra_args=[])
        explicit = SimpleNamespace(
            domain="upload",
            extra_args=["--queue-sync-mode", "per-command"],
        )

        self.assertEqual(infer_workload_queue_sync_mode(upload), "deferred")
        self.assertEqual(infer_workload_queue_sync_mode(compute), "per-command")
        self.assertEqual(infer_workload_queue_sync_mode(explicit), "per-command")

    def test_strict_plan_boundary_symmetry_rejects_mixed_plan_and_commands(self) -> None:
        workload = SimpleNamespace(
            id="alpha",
            comparable=True,
            runner_type="zig-runtime",
            plan_path="bench/plans/alpha.plan.json",
        )
        with self.assertRaisesRegex(ValueError, "plan-backed workload requires plan executors"):
            enforce_strict_plan_boundary_symmetry(
                workloads=[workload],
                baseline_command_template="runtime/zig/zig-out/bin/doe-zig-runtime --commands {commands}",
                comparison_command_template="runtime/zig/zig-out/bin/webgpu-plan-executor --plan {plan}",
                comparability_mode="strict",
            )

    def test_workload_unit_wall_from_trace_meta_uses_prepared_session_wall(self) -> None:
        self.assertEqual(
            workload_unit_wall_from_trace_meta(
                {
                    "workloadUnitWallSource": "trace-meta-process-wall",
                    "processWallMs": 12.5,
                }
            ),
            12.5,
        )
        self.assertIsNone(workload_unit_wall_from_trace_meta({}))

    def test_workload_unit_wall_from_trace_meta_rejects_unknown_source(self) -> None:
        self.assertIsNone(
            workload_unit_wall_from_trace_meta(
                {
                    "workloadUnitWallSource": "trace-meta-processwall",
                    "processWallMs": 12.5,
                }
            )
        )

    def test_extract_timing_metrics_ms_drops_cpu_when_only_inner_wall_boundary_moves(self) -> None:
        metrics = extract_timing_metrics_ms(
            {
                "workloadUnitWallSource": "trace-meta-process-wall",
                "processWallMs": 12.5,
            },
            wall_ms=12.5,
            cpu_ms=None,
        )
        self.assertEqual(metrics["wall_time"], 12.5)
        self.assertIsNone(metrics["cpu_time"])

    def test_trace_meta_records_terminal_execution_outcome_accepts_error_or_unsupported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-runner-trace-meta-") as tmpdir:
            trace_meta_path = Path(tmpdir) / "trace.meta.json"
            trace_meta_path.write_text(
                json.dumps(
                    {
                        "executionErrorCount": 1,
                        "executionUnsupportedCount": 0,
                        "executionSkippedCount": 0,
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(trace_meta_records_terminal_execution_outcome(trace_meta_path))

    @patch("bench.native_compare_modules.runner.run_once")
    def test_run_workload_executes_warmup_before_full_timed_iterations(
        self,
        mock_run_once,
    ) -> None:
        calls = []

        def fake_run_once(_command, **kwargs):
            calls.append(kwargs["trace_meta_path"])
            sample_index = len(calls)
            kwargs["trace_meta_path"].write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "kind": "trace_meta",
                        "executionErrorCount": 0,
                        "executionSkippedCount": 0,
                        "executionUnsupportedCount": 0,
                        "executionTotalNs": sample_index * 1_000_000,
                        "executionSetupTotalNs": 0,
                        "executionEncodeTotalNs": sample_index * 1_000_000,
                        "executionSubmitWaitTotalNs": 0,
                        "executionDispatchCount": 1,
                        "executionRowCount": 1,
                        "executionSuccessCount": 1,
                        "timingMs": float(sample_index),
                        "timingSource": "doe-execution-total-ns",
                    }
                ),
                encoding="utf-8",
            )
            return float(sample_index), 0.0, 0, {"processWallMs": float(sample_index)}

        mock_run_once.side_effect = fake_run_once
        workload = SimpleNamespace(
            id="alpha",
            domain="compute",
            commands_path="",
            plan_path="",
            quirks_path="",
            vendor="",
            api="",
            family="",
            driver="",
            dawn_filter="",
            extra_args=[],
            comparable=True,
            strict_normalization_unit="",
        )

        with tempfile.TemporaryDirectory(prefix="doe-runner-warmup-") as tmpdir:
            result = run_workload(
                name="sample",
                template=(
                    "node bench/executors/sample.js --trace-meta {trace_meta} "
                    "--trace-jsonl {trace_jsonl} --workload {workload}"
                ),
                workload=workload,
                iterations=3,
                warmup=2,
                out_dir=Path(tmpdir),
                gpu_memory_probe="none",
                resource_sample_ms=100,
                resource_sample_target_count=0,
                timing_divisor=1.0,
                command_repeat=1,
                ignore_first_ops=0,
                upload_buffer_usage="copy-dst-copy-src",
                upload_submit_every=1,
                inject_upload_runtime_flags=False,
                required_timing_class="operation",
                comparability_mode="strict",
                benchmark_policy=SimpleNamespace(),
                emit_shell=False,
            )

        self.assertEqual(mock_run_once.call_count, 5)
        self.assertEqual([sample["runIndex"] for sample in result["commandSamples"]], [2, 3, 4])
        self.assertEqual(result["timingsMs"], [3.0, 4.0, 5.0])
        self.assertEqual(result["stats"]["count"], 3)

    @patch(
        "bench.native_compare_modules.runner._parse_compilation_ndjson",
        return_value={"p50_ns": 2_000_000, "p95_ns": 2_500_000, "p99_ns": 3_000_000, "bytesOut": 128},
    )
    @patch(
        "bench.native_compare_modules.runner._tint_startup_baseline_samples",
        return_value=[3.0, 4.0, 5.0],
    )
    @patch(
        "bench.native_compare_modules.runner._tint_compile_samples",
        return_value=[10.0, 11.0, 12.0],
    )
    @patch("bench.native_compare_modules.runner.subprocess.run")
    def test_run_compilation_workload_reports_tint_raw_and_startup_corrected_stats(
        self,
        _mock_subprocess_run,
        _mock_tint_compile_samples,
        _mock_tint_startup_baseline_samples,
        _mock_parse_compilation_ndjson,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-compilation-runner-") as tmpdir:
            tmp = Path(tmpdir)
            shader_path = tmp / "alpha.wgsl"
            doe_bin = tmp / "doe-compilation-bench"
            tint_bin = tmp / "tint"
            shader_path.write_text("@compute @workgroup_size(1)\nfn main() {}\n", encoding="utf-8")
            doe_bin.write_text("", encoding="utf-8")
            tint_bin.write_text("", encoding="utf-8")
            workload = SimpleNamespace(
                id="alpha",
                shader_path=str(shader_path),
                compilation_target="msl",
            )

            result = run_compilation_workload(
                workload,
                iterations=3,
                warmup=1,
                out_dir=tmp / "out",
                doe_compilation_bin=str(doe_bin),
                tint_bin=str(tint_bin),
            )

        comparison = result["comparison"]
        self.assertEqual(comparison["stats"]["p50Ms"], 11.0)
        self.assertEqual(comparison["startupBaselineStatsMs"]["p50Ms"], 4.0)
        self.assertEqual(comparison["startupCorrectionMethod"], "subtract-trivial-shader-baseline-p50")
        self.assertEqual(comparison["startupCorrectedStatsMs"]["p50Ms"], 7.0)
        self.assertIn("startup-corrected", comparison["lastMeta"]["timingNote"])


if __name__ == "__main__":
    unittest.main()
