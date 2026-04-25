#!/usr/bin/env python3
"""Verify the csl_simulator_evidence_gate's classification rules.

The gate must distinguish:
  - artifacts_missing  (no driver-result on disk)
  - compile_failed     (driver says compile.status == "failed")
  - driver_exception   (driver crashed before producing structured output)
  - compile_only       (compile passed but no launch succeeded)
  - plumbing_partial   (some launches succeeded, but not all / run failed)
  - plumbing_pass      (every launch attempted completed cleanly)

Numeric parity must always report `unknown` until a reference transcript
source is wired in — never imply parity from plumbing metrics.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "bench" / "gates" / "csl_simulator_evidence_gate.py"


def _write_artifacts(
    bundle_dir: Path,
    *,
    driver_result: dict | None,
    progress_events: list[dict],
) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    if driver_result is not None:
        (bundle_dir / "trace.json.driver-result.json").write_text(
            json.dumps(driver_result), encoding="utf-8"
        )
    (bundle_dir / "trace.json.progress.jsonl").write_text(
        "\n".join(json.dumps(e) for e in progress_events) + ("\n" if progress_events else ""),
        encoding="utf-8",
    )


def _run_gate(bundle: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--hostplan-bundle", str(bundle), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


class SimulatorEvidenceGateTests(unittest.TestCase):
    def _classification(self, bundle: Path) -> dict:
        result = _run_gate(bundle)
        self.assertEqual(0, result.returncode, msg=result.stderr)
        receipt = json.loads((bundle / "simulator-evidence.json").read_text(encoding="utf-8"))
        return receipt

    def test_artifacts_missing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            # No artifacts written.
            receipt = self._classification(bundle)
            self.assertEqual("artifacts_missing", receipt["plumbingClassification"])
            self.assertEqual("unknown", receipt["numericParity"]["status"])

    def test_compile_failed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            _write_artifacts(
                bundle,
                driver_result={"compile": {"status": "failed"}, "run": {"status": "blocked"}},
                progress_events=[],
            )
            receipt = self._classification(bundle)
            self.assertEqual("compile_failed", receipt["plumbingClassification"])

    def test_driver_exception(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            _write_artifacts(
                bundle,
                driver_result={
                    "compile": {"status": "failed", "reason": "driver_exception: oops"},
                    "run": {"status": "blocked", "reason": "driver_exception: oops"},
                },
                progress_events=[],
            )
            receipt = self._classification(bundle)
            self.assertEqual("driver_exception", receipt["plumbingClassification"])

    def test_compile_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            _write_artifacts(
                bundle,
                driver_result={
                    "compile": {"status": "succeeded"},
                    "run": {"status": "failed", "reason": "runtime_timeout"},
                },
                progress_events=[
                    {"phase": "hostplan_launch_start", "launchIndex": 0, "target": "embed"},
                ],
            )
            receipt = self._classification(bundle)
            self.assertEqual("compile_only", receipt["plumbingClassification"])
            self.assertEqual([0], receipt["launchesStarted"])
            self.assertEqual([], receipt["launchesSucceeded"])

    def test_plumbing_partial(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            _write_artifacts(
                bundle,
                driver_result={
                    "compile": {"status": "succeeded"},
                    "run": {"status": "failed", "reason": "runtime_timeout"},
                },
                progress_events=[
                    {"phase": "hostplan_launch_start", "launchIndex": 0, "target": "embed"},
                    {"phase": "hostplan_launch_complete", "launchIndex": 0, "status": "succeeded"},
                    {"phase": "hostplan_launch_start", "launchIndex": 1, "target": "rmsnorm_prefill"},
                ],
            )
            receipt = self._classification(bundle)
            self.assertEqual("plumbing_partial", receipt["plumbingClassification"])
            self.assertEqual([0], receipt["launchesSucceeded"])
            self.assertEqual([0, 1], receipt["launchesStarted"])

    def test_plumbing_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            _write_artifacts(
                bundle,
                driver_result={
                    "compile": {"status": "succeeded"},
                    "run": {"status": "succeeded"},
                },
                progress_events=[
                    {"phase": "hostplan_launch_start", "launchIndex": 0, "target": "embed"},
                    {"phase": "hostplan_launch_complete", "launchIndex": 0, "status": "succeeded"},
                    {"phase": "hostplan_launch_start", "launchIndex": 1, "target": "rmsnorm_prefill"},
                    {"phase": "hostplan_launch_complete", "launchIndex": 1, "status": "succeeded"},
                ],
            )
            receipt = self._classification(bundle)
            self.assertEqual("plumbing_pass", receipt["plumbingClassification"])

    def test_last_observation_wins_across_regen_runs(self) -> None:
        # Progress log accumulates across regen runs. A launch that failed
        # in an earlier run and succeeded in the latest run must report as
        # succeeded — not as both succeeded and failed.
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            _write_artifacts(
                bundle,
                driver_result={
                    "compile": {"status": "succeeded"},
                    "run": {"status": "failed", "reason": "runtime_timeout"},
                },
                progress_events=[
                    {"phase": "hostplan_launch_blocked", "launchIndex": 1, "error": "some old error"},
                    {"phase": "hostplan_launch_start", "launchIndex": 1, "target": "rmsnorm_prefill"},
                    {"phase": "hostplan_launch_complete", "launchIndex": 1, "status": "succeeded"},
                ],
            )
            receipt = self._classification(bundle)
            self.assertEqual([1], receipt["launchesSucceeded"])
            self.assertEqual([], receipt["launchesFailed"])

    def test_numeric_parity_always_unknown_until_reference_wired(self) -> None:
        # Even when plumbing passes cleanly the gate must NOT imply parity.
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            _write_artifacts(
                bundle,
                driver_result={
                    "compile": {"status": "succeeded"},
                    "run": {"status": "succeeded"},
                },
                progress_events=[
                    {"phase": "hostplan_launch_start", "launchIndex": 0, "target": "embed"},
                    {"phase": "hostplan_launch_complete", "launchIndex": 0, "status": "succeeded"},
                ],
            )
            receipt = self._classification(bundle)
            self.assertEqual("plumbing_pass", receipt["plumbingClassification"])
            self.assertEqual("unknown", receipt["numericParity"]["status"])

    def test_require_threshold_passes_when_at_or_above(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            _write_artifacts(
                bundle,
                driver_result={
                    "compile": {"status": "succeeded"},
                    "run": {"status": "succeeded"},
                },
                progress_events=[
                    {"phase": "hostplan_launch_start", "launchIndex": 0, "target": "embed"},
                    {"phase": "hostplan_launch_complete", "launchIndex": 0, "status": "succeeded"},
                ],
            )
            self.assertEqual(0, _run_gate(bundle, "--require", "plumbing_partial").returncode)
            self.assertEqual(0, _run_gate(bundle, "--require", "plumbing_pass").returncode)

    def test_require_threshold_fails_when_below(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw)
            _write_artifacts(
                bundle,
                driver_result={
                    "compile": {"status": "succeeded"},
                    "run": {"status": "failed"},
                },
                progress_events=[
                    {"phase": "hostplan_launch_start", "launchIndex": 0, "target": "embed"},
                ],
            )
            self.assertEqual(1, _run_gate(bundle, "--require", "plumbing_partial").returncode)


if __name__ == "__main__":
    unittest.main()
