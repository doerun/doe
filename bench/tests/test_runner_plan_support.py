#!/usr/bin/env python3
"""Tests for plan-aware native compare runner helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.native_compare_modules.runner import (
    command_for,
    extract_timing_metrics_ms,
    materialize_repeated_plan,
    trace_meta_records_terminal_execution_outcome,
    workload_unit_wall_from_trace_meta,
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
            },
        }
        with tempfile.TemporaryDirectory(prefix="doe-runner-plan-") as tmpdir:
            source = Path(tmpdir) / "alpha.plan.json"
            out_dir = Path(tmpdir) / "out"
            source.write_text(json.dumps(payload), encoding="utf-8")
            repeated_path = materialize_repeated_plan(
                str(source),
                repeat=3,
                out_dir=out_dir,
                side_name="right",
            )
            repeated = json.loads(Path(repeated_path).read_text(encoding="utf-8"))
            self.assertEqual(len(repeated["steps"]), 6)
            self.assertEqual(repeated["summary"]["stepCount"], 6)
            self.assertEqual(repeated["summary"]["dispatchCount"], 3)
            self.assertEqual(repeated["summary"]["bufferWriteCount"], 3)

    def test_command_for_supports_plan_placeholder(self) -> None:
        command = command_for(
            "node bench/executors/run-node-webgpu-plan.js --plan {plan} --trace-meta {trace_meta} --trace-jsonl {trace_jsonl} --workload {workload}",
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
        )
        self.assertIn("bench/executors/run-node-webgpu-plan.js", command[1])
        self.assertIn("bench/plans/alpha.plan.json", command)

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
                left_command_template="runtime/zig/zig-out/bin/doe-zig-runtime --commands {commands}",
                right_command_template="runtime/zig/zig-out/bin/dawn-plan-executor --plan {plan}",
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


if __name__ == "__main__":
    unittest.main()
