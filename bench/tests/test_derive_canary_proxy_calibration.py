"""Tests for bench/tools/derive_canary_proxy_calibration.py."""

from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

derive = importlib.import_module(
    "bench.tools.derive_canary_proxy_calibration"
)


def _write_sim_stats(
    root: Path,
    kernel: str,
    cycle_count: int,
    total_time: float,
) -> Path:
    sim_stats_dir = root / kernel / "scratch"
    sim_stats_dir.mkdir(parents=True, exist_ok=True)
    sim_stats_path = sim_stats_dir / "sim_stats.json"
    sim_stats_path.write_text(
        json.dumps(
            {
                "cycle_count": cycle_count,
                "total_time": total_time,
                "fabric_x": 8,
                "fabric_y": 3,
                "simulated_tile_count": 14,
            }
        ),
        encoding="utf-8",
    )
    return sim_stats_path


class CollectSamplesTests(unittest.TestCase):
    def test_walks_inventory_and_records_per_kernel_metadata(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kernel in derive.CANARY_INVENTORY:
                _write_sim_stats(
                    root,
                    kernel=kernel,
                    cycle_count=1000,
                    total_time=0.1,
                )
            samples, missing = derive.collect_samples(root)
            self.assertEqual(len(samples), len(derive.CANARY_INVENTORY))
            self.assertEqual(missing, [])
            embed = next(s for s in samples if s["kernel"] == "embed")
            self.assertEqual(embed["pattern"], "gather")
            self.assertEqual(embed["cycleCount"], 1000)
            self.assertEqual(embed["outputBytes"], 256 * 4)
            self.assertAlmostEqual(embed["bytesPerCycle"], 1024 / 1000)

    def test_missing_kernels_are_reported_not_silently_dropped(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_sim_stats(
                root, kernel="embed", cycle_count=1000, total_time=0.1
            )
            samples, missing = derive.collect_samples(root)
            self.assertEqual({s["kernel"] for s in samples}, {"embed"})
            self.assertIn("rms_norm", missing)
            self.assertIn("attention_head256_f16kv", missing)

    def test_zero_cycle_count_is_treated_as_missing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_sim_stats(
                root, kernel="embed", cycle_count=0, total_time=0.1
            )
            samples, missing = derive.collect_samples(root)
            self.assertEqual(samples, [])
            self.assertTrue(any("embed" in m for m in missing))


class DeriveConstantsTests(unittest.TestCase):
    def test_per_pattern_picks_largest_cycle_count(self):
        samples = [
            {
                "kernel": "attention_head256_f16kv",
                "pattern": "attention_decode",
                "cycleCount": 30000,
                "bytesPerCycle": 1024 / 30000,
            },
            {
                "kernel": "attention_head512_f16kv",
                "pattern": "attention_decode",
                "cycleCount": 60000,
                "bytesPerCycle": 2048 / 60000,
            },
        ]
        constants = derive.derive_constants(samples)
        self.assertEqual(
            constants["perPatternCyclesPerCall"]["attention_decode"],
            60000,
        )

    def test_bytes_per_cycle_is_median(self):
        samples = [
            {"pattern": "p", "cycleCount": 10, "bytesPerCycle": 1.0},
            {"pattern": "p", "cycleCount": 10, "bytesPerCycle": 2.0},
            {"pattern": "p", "cycleCount": 10, "bytesPerCycle": 3.0},
        ]
        constants = derive.derive_constants(samples)
        self.assertEqual(constants["bytesPerCycle"], 2.0)

    def test_empty_samples_raises(self):
        with self.assertRaises(ValueError):
            derive.derive_constants([])


class BuildReceiptTests(unittest.TestCase):
    def test_receipt_carries_calibration_source_and_not_what(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_sim_stats(
                root, kernel="embed", cycle_count=1000, total_time=0.1
            )
            samples, missing = derive.collect_samples(root)
            constants = derive.derive_constants(samples)
            receipt = derive.build_receipt(root, samples, missing, constants)
            self.assertEqual(
                receipt["artifactKind"],
                "doe_simfabric_throughput_calibration",
            )
            self.assertEqual(receipt["calibrationSource"], "canary_proxy")
            self.assertIn("NOT a manifest-shape", receipt["claim"]["notWhat"])
            self.assertEqual(receipt["comparisonMode"], "no_oracle")


if __name__ == "__main__":
    unittest.main()
