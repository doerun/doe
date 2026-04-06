#!/usr/bin/env python3
"""Tests for deterministic synthetic benchmark asset warming."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from bench.lib import synthetic_assets


class SyntheticAssetsTests(unittest.TestCase):
    def test_ensure_buffer_load_asset_writes_reusable_nonzero_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-synth-assets-") as tmpdir:
            old = os.environ.get(synthetic_assets.CACHE_ENV_VAR)
            os.environ[synthetic_assets.CACHE_ENV_VAR] = tmpdir
            try:
                command = synthetic_assets.build_buffer_load_command(
                    handle=20,
                    buffer_size=64,
                    cache_namespace="unit_test",
                    generator="splitmix64_f32_nonzero_v1",
                    seed=11,
                    scale=0.125,
                    asset_key="alpha:handle-20",
                )
                path = synthetic_assets.ensure_buffer_load_asset(command)
                self.assertTrue(path.exists())
                payload = path.read_bytes()
                self.assertEqual(len(payload), 64)
                self.assertNotEqual(payload, bytes(64))
                second = synthetic_assets.ensure_buffer_load_asset(command)
                self.assertEqual(second, path)
                self.assertEqual(second.read_bytes(), payload)
            finally:
                if old is None:
                    os.environ.pop(synthetic_assets.CACHE_ENV_VAR, None)
                else:
                    os.environ[synthetic_assets.CACHE_ENV_VAR] = old

    def test_ensure_plan_assets_warms_all_buffer_load_entries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-synth-assets-plan-") as tmpdir:
            old = os.environ.get(synthetic_assets.CACHE_ENV_VAR)
            os.environ[synthetic_assets.CACHE_ENV_VAR] = tmpdir
            try:
                plan_path = Path(tmpdir) / "plan.json"
                command = synthetic_assets.build_buffer_load_command(
                    handle=30,
                    buffer_size=32,
                    cache_namespace="unit_test_plan",
                    generator="splitmix64_f16_nonzero_v1",
                    seed=29,
                    scale=0.125,
                    asset_key="alpha:handle-30",
                )
                plan_path.write_text(
                    json.dumps(
                        {
                            "schemaVersion": 1,
                            "planKind": "benchmark_ir",
                            "workloadId": "alpha",
                            "irPath": "bench/ir/test.json",
                            "irScenario": "alpha",
                            "commandCount": 1,
                            "bufferWriteCount": 0,
                            "bufferLoadCount": 1,
                            "dispatchCount": 0,
                            "sourceIrSha256": "abc",
                            "compatibilityCommandsSha256": "def",
                            "planSha256": "ghi",
                            "commands": [command],
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                warmed = synthetic_assets.ensure_plan_assets(plan_path)
                self.assertEqual(len(warmed), 1)
                self.assertTrue(warmed[0].exists())
            finally:
                if old is None:
                    os.environ.pop(synthetic_assets.CACHE_ENV_VAR, None)
                else:
                    os.environ[synthetic_assets.CACHE_ENV_VAR] = old


if __name__ == "__main__":
    unittest.main()
