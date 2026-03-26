#!/usr/bin/env python3
"""Tests for single-runtime plan-backed workload support."""

from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

MODULE_PATH = REPO_ROOT / "bench" / "single-runtime" / "run_bench.py"
SPEC = importlib.util.spec_from_file_location("doe_single_runtime_run_bench", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
run_bench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_bench
SPEC.loader.exec_module(run_bench)


class SingleRuntimePlanSupportTests(unittest.TestCase):
    def test_load_workload_preserves_ir_and_plan_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-single-runtime-plan-") as tmpdir:
            workloads_path = Path(tmpdir) / "workloads.json"
            payload = {
                "schemaVersion": 1,
                "workloads": [
                    {
                        "id": "alpha",
                        "name": "alpha",
                        "description": "alpha workload",
                        "runnerType": "zig-runtime",
                        "commandsPath": "examples/alpha.json",
                        "irPath": "bench/ir/alpha.json",
                        "planPath": "bench/plans/alpha.plan.json",
                        "quirksPath": "examples/quirks/noop.json",
                        "vendor": "apple",
                        "api": "metal",
                        "family": "m3",
                        "driver": "1.0.0",
                        "extraArgs": [],
                    }
                ],
            }
            workloads_path.write_text(json.dumps(payload), encoding="utf-8")

            workload = run_bench.load_workloads(str(workloads_path), "alpha")
            self.assertEqual(workload.runner_type, "zig-runtime")
            self.assertEqual(workload.ir_path, "bench/ir/alpha.json")
            self.assertEqual(workload.plan_path, "bench/plans/alpha.plan.json")

    def test_command_for_supports_plan_placeholder(self) -> None:
        workload = run_bench.Workload(
            workload_id="alpha",
            name="alpha",
            description="alpha workload",
            runner_type="zig-runtime",
            commands_path="examples/alpha.json",
            ir_path="bench/ir/alpha.json",
            plan_path="bench/plans/alpha.plan.json",
            quirks_path="examples/quirks/noop.json",
            vendor="apple",
            api="metal",
            family="m3",
            driver="1.0.0",
            extra_args=[],
        )
        command = run_bench.command_for(
            "node bench/executors/run-node-webgpu-plan.js --plan {plan} --trace-meta {trace_meta} --trace-jsonl {trace_jsonl} --workload {workload}",
            workload,
            trace_jsonl=Path("tmp/trace.ndjson"),
            trace_meta=Path("tmp/trace.meta.json"),
            command_template_args={"backend": "metal", "gpu": "test", "extra_args": []},
        )
        self.assertIn("bench/executors/run-node-webgpu-plan.js", command[1])
        self.assertIn("bench/plans/alpha.plan.json", command)

    def test_command_for_rejects_plan_template_without_plan_path(self) -> None:
        workload = run_bench.Workload(
            workload_id="alpha",
            name="alpha",
            description="alpha workload",
            runner_type="zig-runtime",
            commands_path="examples/alpha.json",
            ir_path="bench/ir/alpha.json",
            plan_path="",
            quirks_path="examples/quirks/noop.json",
            vendor="apple",
            api="metal",
            family="m3",
            driver="1.0.0",
            extra_args=[],
        )
        with self.assertRaisesRegex(ValueError, "requires planPath"):
            run_bench.command_for(
                "node bench/executors/run-node-webgpu-plan.js --plan {plan} --trace-meta {trace_meta} --trace-jsonl {trace_jsonl} --workload {workload}",
                workload,
                trace_jsonl=Path("tmp/trace.ndjson"),
                trace_meta=Path("tmp/trace.meta.json"),
                command_template_args={"backend": "metal", "gpu": "test", "extra_args": []},
            )


if __name__ == "__main__":
    unittest.main()
