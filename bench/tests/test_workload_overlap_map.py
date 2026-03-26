#!/usr/bin/env python3
"""Regression tests for generated workload overlap maps."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OVERLAP_GENERATOR_PATH = REPO_ROOT / "bench" / "tools" / "generate_workload_overlap_map.py"
OVERLAP_MAP_PATH = REPO_ROOT / "bench" / "workloads" / "metadata" / "workload-overlap-map.json"


def load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "generate_workload_overlap_map", OVERLAP_GENERATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load generator module from {OVERLAP_GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


class WorkloadOverlapMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generator = load_generator_module()
        cls.catalog_root = REPO_ROOT

    def _full_frontier_sources(self) -> dict[str, str]:
        return {
            "metal": str(self.catalog_root / self.generator.DEFAULT_FULL_FRONTIER["metal"]),
            "vulkan": str(self.catalog_root / self.generator.DEFAULT_FULL_FRONTIER["vulkan"]),
            "d3d12": str(self.catalog_root / self.generator.DEFAULT_FULL_FRONTIER["d3d12"]),
        }

    def _release_lens_sources(self) -> dict[str, str]:
        return {
            "metal": str(self.catalog_root / self.generator.DEFAULT_METAL_RELEASE_LENS["metal"]),
            "vulkan": str(self.catalog_root / self.generator.DEFAULT_METAL_RELEASE_LENS["vulkan"]),
            "d3d12": str(self.catalog_root / self.generator.DEFAULT_METAL_RELEASE_LENS["d3d12"]),
        }

    def _assert_partition_is_disjoint(self, coverage: dict[str, list[str]]) -> None:
        buckets = [set(v) for v in coverage.values()]
        all_ids = set().union(*buckets)
        seen: set[str] = set()
        for bucket in buckets:
            overlap = seen & bucket
            self.assertFalse(
                overlap,
                msg=f"workload-overlap categories must be disjoint, found overlap={sorted(overlap)}",
            )
            seen |= bucket
        self.assertEqual(sum(len(bucket) for bucket in buckets), len(all_ids))

    def test_overlap_artifact_matches_generator_output(self) -> None:
        expected = self.generator.build_overlap_map(
            self._full_frontier_sources(),
            self._release_lens_sources(),
        )
        artifact = load_json(OVERLAP_MAP_PATH)
        self.assertEqual(artifact, expected)

    def test_overlap_sections_are_partitioned_and_counted(self) -> None:
        overlap = self.generator.build_overlap_map(
            self._full_frontier_sources(),
            self._release_lens_sources(),
        )

        for key in ("fullComparableFrontier", "metalReleaseLens"):
            section = overlap[key]["coverage"]
            self._assert_partition_is_disjoint(section)
            self.assertEqual(
                overlap[key]["counts"]["across_all_three_backends"],
                len(section["across_all_three_backends"]),
            )
            self.assertEqual(
                overlap[key]["counts"]["only_vulkan"],
                len(section["only_vulkan"]),
            )
            self.assertEqual(
                overlap[key]["counts"]["only_metal"],
                len(section["only_metal"]),
            )
            self.assertEqual(
                overlap[key]["counts"]["only_d3d12"],
                len(section["only_d3d12"]),
            )
            self.assertEqual(
                overlap[key]["counts"]["vulkan_and_metal_only"],
                len(section["vulkan_and_metal_only"]),
            )
            self.assertEqual(
                overlap[key]["counts"]["metal_and_d3d12_only"],
                len(section["metal_and_d3d12_only"]),
            )
            self.assertEqual(
                overlap[key]["counts"]["vulkan_and_d3d12_only"],
                len(section["vulkan_and_d3d12_only"]),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
