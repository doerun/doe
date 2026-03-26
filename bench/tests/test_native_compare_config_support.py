#!/usr/bin/env python3
"""Tests for native compare workload selection behavior."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.native_compare_modules import config_support


def _write_workloads(path: Path) -> None:
    payload = {
        "schemaVersion": 1,
        "workloads": [
            {
                "id": "alpha",
                "name": "alpha",
                "domain": "compute",
                "commandsPath": "examples/alpha.json",
                "quirksPath": "examples/quirks/noop.json",
                "vendor": "apple",
                "api": "metal",
                "family": "m3",
                "driver": "1.0.0",
                "extraArgs": [],
                "dawnFilter": "alpha",
                "comparable": True,
                "benchmarkClass": "comparable",
                "claimEligible": True,
                "cohorts": ["governed"],
            },
            {
                "id": "beta",
                "name": "beta",
                "domain": "compute",
                "commandsPath": "examples/beta.json",
                "quirksPath": "examples/quirks/noop.json",
                "vendor": "apple",
                "api": "metal",
                "family": "m3",
                "driver": "1.0.0",
                "extraArgs": [],
                "dawnFilter": "beta",
                "comparable": True,
                "benchmarkClass": "comparable",
                "claimEligible": True,
                "cohorts": ["governed"],
            },
            {
                "id": "gamma",
                "name": "gamma",
                "domain": "compute",
                "commandsPath": "examples/gamma.json",
                "quirksPath": "examples/quirks/noop.json",
                "vendor": "apple",
                "api": "metal",
                "family": "m3",
                "driver": "1.0.0",
                "extraArgs": [],
                "dawnFilter": "gamma",
                "comparable": True,
                "benchmarkClass": "comparable",
                "claimEligible": True,
                "cohorts": ["exploration"],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class NativeCompareConfigSupportTests(unittest.TestCase):
    def test_load_workloads_preserves_ir_and_plan_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-native-compare-config-") as tmpdir:
            workloads_path = Path(tmpdir) / "workloads.json"
            payload = {
                "schemaVersion": 1,
                "workloads": [
                    {
                        "id": "alpha",
                        "name": "alpha",
                        "domain": "compute",
                        "commandsPath": "examples/alpha.json",
                        "irPath": "bench/ir/alpha.json",
                        "planPath": "bench/plans/alpha.json",
                        "quirksPath": "examples/quirks/noop.json",
                        "vendor": "apple",
                        "api": "metal",
                        "family": "m3",
                        "driver": "1.0.0",
                        "extraArgs": [],
                        "dawnFilter": "alpha",
                        "comparable": True,
                        "benchmarkClass": "comparable",
                        "claimEligible": True,
                        "cohorts": ["governed"],
                    }
                ],
            }
            workloads_path.write_text(json.dumps(payload), encoding="utf-8")
            workloads = config_support.load_workloads(
                workloads_path,
                "",
                include_noncomparable=False,
                include_extended=False,
                workload_cohort="all",
                selector=None,
            )
            self.assertEqual(len(workloads), 1)
            self.assertEqual(workloads[0].ir_path, "bench/ir/alpha.json")
            self.assertEqual(workloads[0].plan_path, "bench/plans/alpha.json")

    def test_workload_filter_intersects_selector_results(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-native-compare-config-") as tmpdir:
            workloads_path = Path(tmpdir) / "workloads.json"
            _write_workloads(workloads_path)
            workloads = config_support.load_workloads(
                workloads_path,
                "beta",
                include_noncomparable=False,
                include_extended=False,
                workload_cohort="all",
                selector={"cohorts": ["governed"], "benchmarkClass": ["comparable"]},
            )
            self.assertEqual([workload.id for workload in workloads], ["beta"])

    def test_selector_still_applies_without_workload_filter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-native-compare-config-") as tmpdir:
            workloads_path = Path(tmpdir) / "workloads.json"
            _write_workloads(workloads_path)
            workloads = config_support.load_workloads(
                workloads_path,
                "",
                include_noncomparable=False,
                include_extended=False,
                workload_cohort="all",
                selector={"cohorts": ["governed"], "benchmarkClass": ["comparable"]},
            )
            self.assertEqual([workload.id for workload in workloads], ["alpha", "beta"])


if __name__ == "__main__":
    unittest.main()
