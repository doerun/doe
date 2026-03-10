#!/usr/bin/env python3
"""Regression tests for the canonical backend workload catalog."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR_PATH = REPO_ROOT / "bench" / "generate_backend_workloads.py"


def load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_backend_workloads", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load generator module from {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


class BackendWorkloadCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generator = load_generator_module()
        cls.catalog = load_json(REPO_ROOT / "bench" / "backend-workload-catalog.json")

    def test_write_json_skips_unchanged_content(self) -> None:
        payload = {"schemaVersion": 1, "workloads": [{"id": "alpha"}]}
        with tempfile.TemporaryDirectory(prefix="fawn-backend-workload-catalog-") as tmpdir:
            path = Path(tmpdir) / "out.json"
            first = self.generator.write_json(path, payload)
            second = self.generator.write_json(path, payload)
            self.assertTrue(first)
            self.assertFalse(second)
            self.assertEqual(path.read_text(encoding="utf-8"), self.generator.json_text(payload))

    def test_d3d12_generated_views_match_catalog(self) -> None:
        smoke = self.generator.materialize_lane(self.catalog, "local_d3d12_smoke")
        extended = self.generator.materialize_lane(self.catalog, "local_d3d12_extended")
        self.assertEqual(
            smoke,
            load_json(REPO_ROOT / "bench" / "workloads.local.d3d12.smoke.json"),
        )
        self.assertEqual(
            extended,
            load_json(REPO_ROOT / "bench" / "workloads.local.d3d12.extended.json"),
        )

    def test_expected_d3d12_workload_id_sets(self) -> None:
        smoke = self.generator.materialize_lane(self.catalog, "local_d3d12_smoke")
        extended = self.generator.materialize_lane(self.catalog, "local_d3d12_extended")
        self.assertEqual(
            [row["id"] for row in smoke["workloads"]],
            [
                "compute_workgroup_atomic_1024",
                "pipeline_compile_stress",
                "upload_write_buffer_64kb",
            ],
        )
        self.assertEqual(
            [row["id"] for row in extended["workloads"]],
            [
                "compute_workgroup_atomic_1024",
                "compute_workgroup_non_atomic_1024",
                "pipeline_compile_stress",
                "upload_write_buffer_16mb",
                "upload_write_buffer_1kb",
                "upload_write_buffer_1mb",
                "upload_write_buffer_4mb",
                "upload_write_buffer_64kb",
                "compute_concurrent_execution_single",
                "compute_zero_initialize_workgroup_memory_256",
                "resource_lifecycle",
            ],
        )

    def test_expected_local_metal_additional_directional_ids(self) -> None:
        metal = self.generator.materialize_lane(self.catalog, "local_metal_extended")
        workload_ids = [row["id"] for row in metal["workloads"]]
        self.assertIn("compute_dispatch_fallback", workload_ids)
        self.assertIn("compute_dispatch_grid", workload_ids)
        self.assertIn("copy_buffer_to_texture", workload_ids)
        self.assertIn("copy_protocol", workload_ids)
        self.assertIn("copy_texture_to_buffer", workload_ids)
        self.assertIn("copy_texture_to_texture", workload_ids)
        self.assertIn("surface_full_presentation", workload_ids)
        self.assertEqual(len(workload_ids), 50)

    def test_d3d12_config_and_policy_invariants(self) -> None:
        smoke_config = load_json(REPO_ROOT / "bench" / "compare_dawn_vs_doe.config.local.d3d12.smoke.json")
        comparable_config = load_json(
            REPO_ROOT / "bench" / "compare_dawn_vs_doe.config.local.d3d12.extended.comparable.json"
        )
        release_config = load_json(
            REPO_ROOT / "bench" / "compare_dawn_vs_doe.config.local.d3d12.release.json"
        )
        runtime_policy = load_json(REPO_ROOT / "config" / "backend-runtime-policy.json")
        governed_lanes = load_json(REPO_ROOT / "config" / "governed-lanes.json")
        cube_policy = load_json(REPO_ROOT / "config" / "benchmark-cube-policy.json")

        self.assertEqual(smoke_config["workloads"], "bench/workloads.local.d3d12.smoke.json")
        self.assertEqual(
            comparable_config["workloads"], "bench/workloads.local.d3d12.extended.json"
        )
        self.assertEqual(release_config["workloads"], "bench/workloads.local.d3d12.extended.json")

        self.assertEqual(smoke_config["left"]["name"], "doe")
        self.assertIn("--backend-lane d3d12_doe_comparable", smoke_config["left"]["commandTemplate"])
        self.assertIn("--backend-lane d3d12_dawn_release", smoke_config["right"]["commandTemplate"])
        self.assertIn("--backend-lane d3d12_doe_comparable", comparable_config["left"]["commandTemplate"])
        self.assertIn("--backend-lane d3d12_dawn_release", comparable_config["right"]["commandTemplate"])
        self.assertIn("--backend-lane d3d12_doe_release", release_config["left"]["commandTemplate"])
        self.assertIn("--backend-lane d3d12_dawn_release", release_config["right"]["commandTemplate"])
        self.assertEqual(release_config["claimability"]["mode"], "release")
        self.assertEqual(release_config["claimability"]["minTimedSamples"], 15)

        for lane_id in ("d3d12_doe_comparable", "d3d12_doe_release"):
            lane = runtime_policy["lanes"][lane_id]
            self.assertEqual(lane["defaultBackend"], "doe_d3d12")
            self.assertEqual(lane["uploadPathPolicy"], "staged_copy_only")
            self.assertTrue(lane["strictNoFallback"])

        lane_map = {lane["id"]: lane for lane in governed_lanes["lanes"]}
        for lane_id in ("d3d12_doe_comparable", "d3d12_doe_release", "d3d12_dawn_release"):
            lane = lane_map[lane_id]
            self.assertIn("windows_d3d12", lane["hostProfiles"])
            self.assertTrue(lane["cubeEligible"])
            self.assertEqual(lane["surface"], "backend_native")

        backend_surface = next(
            item for item in cube_policy["surfaces"] if item["id"] == "backend_native"
        )
        self.assertIn("windows_d3d12", backend_surface["expectedHostProfiles"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
