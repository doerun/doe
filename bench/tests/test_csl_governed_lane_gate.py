#!/usr/bin/env python3
"""Verify the csl_governed_lane_gate's heterogeneous-HostPlan check.

The gate must fail when:
  - the referenced HostPlan declares more than one distinct kernel
    (a heterogeneous lane — 270M, Gemma 4 E2B, any future multi-kernel fixture)
  - AND the report's receipts.operationGraph.kernelPatternCount is 0 or absent

It must NOT fail when:
  - the HostPlan is single-kernel (gelu smoke) — kernelPatternCount=1 or 0
    both look fine because only one pattern was ever expected
  - the HostPlan artifact is missing/unreadable — that's upstream territory
  - kernelPatternCount is correctly surfaced for the heterogeneous plan
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "bench" / "gates" / "csl_governed_lane_gate.py"


def _minimal_report(
    *,
    host_plan_path: Path | str,
    kernel_pattern_count: int | None,
    lane_status: str = "ready",
) -> dict:
    """Synthesize the smallest lane report that satisfies the schema plus
    the fields our gate inspects."""
    op_graph: dict = {
        "status": "bound",
        "graphId": "test-graph",
        "executionPattern": "rpc_launch",
        "orchestrationMode": "memcpy",
        "operationCount": 3,
        "exportedSymbolCount": 2,
        "sdkVersionFloor": "1.4.0",
    }
    if kernel_pattern_count is not None:
        op_graph["kernelPatternCount"] = kernel_pattern_count

    return {
        "schemaVersion": 1,
        "generatedAt": "2026-04-18T00:00:00Z",
        "fixture": {"id": "unit-test", "inputJsonPath": "/dev/null"},
        "laneStatus": lane_status,
        "compile": {"status": "succeeded", "reason": "unit_test", "runnerExitCode": 0},
        "run": {"status": "succeeded", "reason": "unit_test", "traceProduced": True},
        "parity": {
            "status": "matched",
            "reason": "unit_test",
            "expectedHostPlanSha256": "",
            "actualHostPlanSha256": "",
        },
        "artifacts": {
            "actualHostPlanPath": str(host_plan_path),
            "expectedHostPlanPath": str(host_plan_path),
            "simulatorPlanPath": "/dev/null",
            "simulatorResultPath": "",
            "driverResultPath": "",
        },
        "comparisonStatus": "diagnostic",
        "claimStatus": "not-evaluated",
        "receipts": {"operationGraph": op_graph},
    }


def _write_host_plan(path: Path, kernel_names: list[str]) -> None:
    payload = {
        "schemaVersion": 2,
        "artifactKind": "csl_host_plan",
        "hostPlan": {
            "kernels": [
                {"name": name, "pattern": "element_wise", "count": 1}
                for name in kernel_names
            ]
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_gate(report_path: Path, *extra_args: str) -> tuple[int, str, str]:
    """Run the gate as a subprocess — this exercises the real argparse
    entrypoint, matching how run_blocking_gates.py will invoke it."""
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(REPO_ROOT))
    proc = subprocess.run(
        [
            sys.executable,
            str(GATE),
            "--report",
            str(report_path),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


class HeterogeneousHostPlanGateTests(unittest.TestCase):
    def test_heterogeneous_hostplan_without_kernel_patterns_fails(self) -> None:
        """270M/E2B-shaped HostPlan + kernelPatternCount=0 is the regression
        we're gating. It must fail the lane even though every other status
        field looks green."""
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "host-plan.json"
            _write_host_plan(hp, ["embed", "rmsnorm", "tiled", "gemv"])
            report = _minimal_report(host_plan_path=hp, kernel_pattern_count=0)
            report_path = Path(td) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            rc, stdout, stderr = _run_gate(report_path)
            self.assertNotEqual(rc, 0, f"gate should fail; stdout={stdout} stderr={stderr}")
            self.assertIn("kernelPatternCount", stdout + stderr)

    def test_heterogeneous_hostplan_missing_field_fails(self) -> None:
        """Absence of kernelPatternCount on a heterogeneous HostPlan is
        just as bad as kernelPatternCount=0 — the field carrying the
        per-kernel binding got dropped somewhere upstream."""
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "host-plan.json"
            _write_host_plan(hp, ["embed", "rmsnorm"])
            report = _minimal_report(host_plan_path=hp, kernel_pattern_count=None)
            report_path = Path(td) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            rc, stdout, stderr = _run_gate(report_path)
            self.assertNotEqual(rc, 0, f"gate should fail; stdout={stdout} stderr={stderr}")

    def test_heterogeneous_hostplan_with_kernel_patterns_passes(self) -> None:
        """Happy path: heterogeneous HostPlan + kernelPatternCount > 0
        means the op-graph receipt actually surfaced the Doppler pattern
        bindings. The gate must not false-positive here."""
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "host-plan.json"
            _write_host_plan(hp, ["embed", "rmsnorm", "tiled"])
            report = _minimal_report(host_plan_path=hp, kernel_pattern_count=3)
            report_path = Path(td) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            rc, stdout, _ = _run_gate(report_path)
            self.assertEqual(rc, 0, f"gate should pass; stdout={stdout}")

    def test_single_kernel_hostplan_does_not_require_pattern_count(self) -> None:
        """Single-kernel fixtures (like gelu-wgsl-backed) have only one
        kernel; the gate must NOT demand kernelPatternCount > 0 because
        the op-graph receipt is already fully informative with the
        single-target rpc_launch section."""
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "host-plan.json"
            _write_host_plan(hp, ["gelu"])
            report = _minimal_report(host_plan_path=hp, kernel_pattern_count=0)
            report_path = Path(td) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            rc, stdout, _ = _run_gate(report_path)
            self.assertEqual(rc, 0, f"gate should pass; stdout={stdout}")

    def test_missing_host_plan_does_not_fail_gate(self) -> None:
        """If the HostPlan artifact is unreachable (path broken, upstream
        step crashed), that's not the governed-lane gate's concern — the
        compile/run/parity fields would already be degraded and caught
        by the existing checks."""
        with tempfile.TemporaryDirectory() as td:
            report = _minimal_report(
                host_plan_path=Path(td) / "nonexistent.json",
                kernel_pattern_count=0,
            )
            report_path = Path(td) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            rc, stdout, _ = _run_gate(report_path)
            self.assertEqual(rc, 0, f"gate should pass when HostPlan missing; stdout={stdout}")

    def test_check_can_be_disabled(self) -> None:
        """--no-require-host-plan-kernel-patterns lets legacy reports
        that predate kernelPatternCount through — temporary escape hatch
        while the field rolls out."""
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "host-plan.json"
            _write_host_plan(hp, ["embed", "rmsnorm"])
            report = _minimal_report(host_plan_path=hp, kernel_pattern_count=0)
            report_path = Path(td) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            rc, stdout, _ = _run_gate(report_path, "--no-require-host-plan-kernel-patterns")
            self.assertEqual(rc, 0, f"gate should pass when check disabled; stdout={stdout}")


if __name__ == "__main__":
    unittest.main()
