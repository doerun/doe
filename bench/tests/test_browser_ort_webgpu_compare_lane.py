#!/usr/bin/env python3
"""Regression tests for the browser ORT WebGPU compare surface."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.native_compare_modules import config_support
from bench.native_compare_modules.executor_registry import (
    resolve_executor_boundary,
    resolve_executor_command_template,
)


WORKLOADS_PATH = REPO_ROOT / "bench" / "workloads" / "workloads.browser.ort-webgpu-compare.json"
COMPARE_CONFIG_PATH = REPO_ROOT / "bench" / "native-compare" / "compare.config.browser.ort-webgpu.json"

EXPECTED_IDS = [
    "browser_ort_webgpu_compare_sentiment",
    "browser_ort_webgpu_compare_sentiment_longform",
]


class BrowserOrtWebGpuCompareLaneTests(unittest.TestCase):
    def test_workload_manifest_loads_browser_compare_ids(self) -> None:
        workloads = config_support.load_workloads(
            WORKLOADS_PATH,
            "",
            include_noncomparable=True,
            include_extended=False,
            workload_cohort="all",
            selector={"ids": EXPECTED_IDS},
        )
        self.assertEqual([workload.id for workload in workloads], EXPECTED_IDS)
        for workload in workloads:
            self.assertTrue(workload.comparable)
            self.assertFalse(workload.claim_eligible)
            self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_compare_config_tracks_expected_browser_ids(self) -> None:
        payload = json.loads(COMPARE_CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["baseline"]["executorId"], "browser_ort_webgpu_dawn")
        self.assertEqual(payload["comparison"]["executorId"], "browser_ort_webgpu_doe")
        self.assertEqual(payload["comparability"]["mode"], "strict")
        self.assertEqual(payload["comparability"]["requireTimingClass"], "process-wall")
        self.assertEqual(payload["claimability"]["mode"], "off")
        self.assertEqual(payload["selector"]["ids"], EXPECTED_IDS)

    def test_executor_registry_resolves_browser_compare_executors(self) -> None:
        dawn_template = resolve_executor_command_template("browser_ort_webgpu_dawn")
        doe_template = resolve_executor_command_template("browser_ort_webgpu_doe")
        self.assertIn("run-browser-ort-bench.py", dawn_template)
        self.assertIn("--mode dawn", dawn_template)
        self.assertIn("--mode doe", doe_template)
        self.assertEqual(resolve_executor_boundary("browser_ort_webgpu_dawn"), "commands")
        self.assertEqual(resolve_executor_boundary("browser_ort_webgpu_doe"), "commands")


if __name__ == "__main__":
    unittest.main()
