#!/usr/bin/env python3
"""Tests for promoted compare wrapper resolution."""

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

from bench.native_compare_modules.promoted_compare import (  # noqa: E402
    DEFAULT_COMPARE_CLI,
    default_mode_for_surface,
    load_catalog,
    resolve_entry,
    build_compare_argv,
)


class PromotedCompareTests(unittest.TestCase):
    def test_default_mode_by_surface(self) -> None:
        self.assertEqual(default_mode_for_surface("backend"), "default")
        self.assertEqual(default_mode_for_surface("plan"), "default")
        self.assertEqual(default_mode_for_surface("package"), "cold")

    def test_resolve_backend_entry_by_preset(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(
            entries,
            backend="apple-metal",
            surface="backend",
            preset="compare",
        )
        self.assertEqual(entry.id, "apple-metal-backend-compare")
        self.assertEqual(entry.boundary, "backend_native")
        self.assertEqual(entry.runtime_host, "none")
        self.assertEqual(entry.temperature, "default")
        self.assertEqual(entry.comparison_view, "doe_vs_dawn_delegate")
        self.assertEqual(entry.provider_set, "backend_native_providers")
        self.assertEqual(entry.baseline_executor_id, "doe_direct_metal")
        self.assertEqual(entry.comparison_executor_id, "dawn_delegate_metal")

    def test_resolve_plan_entry_by_workload(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(
            entries,
            backend="apple-metal",
            surface="plan",
            workload="gemma270m-literal",
        )
        self.assertEqual(entry.id, "apple-metal-gemma270m-literal-plan")
        self.assertEqual(entry.baseline_executor_id, "doe_direct_plan_metal")
        self.assertEqual(entry.comparison_executor_id, "dawn_direct_metal")

    def test_resolve_package_warm_entry_by_workload(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(
            entries,
            backend="apple-metal",
            surface="package",
            workload="gemma64",
            mode="warm",
        )
        self.assertEqual(entry.id, "apple-metal-gemma64-package-warm")
        self.assertEqual(entry.package_runtime, "node")
        self.assertEqual(entry.runtime_host, "node")
        self.assertEqual(entry.temperature, "warm")
        self.assertEqual(entry.comparison_view, "doe_vs_node_webgpu_package")
        self.assertEqual(entry.baseline_executor_id, "doe_node_webgpu_prepared")
        self.assertEqual(entry.comparison_executor_id, "node_webgpu_package_prepared")

    def test_resolve_bun_package_warm_entry_by_workload(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(
            entries,
            backend="apple-metal",
            surface="package",
            workload="gemma64",
            mode="warm",
            package_runtime="bun",
        )
        self.assertEqual(entry.id, "apple-metal-gemma64-bun-package-warm")
        self.assertEqual(entry.package_runtime, "bun")
        self.assertEqual(entry.runtime_host, "bun")
        self.assertEqual(entry.comparison_view, "doe_vs_bun_webgpu_package")
        self.assertEqual(entry.baseline_executor_id, "doe_bun_package_prepared")
        self.assertEqual(entry.comparison_executor_id, "bun_webgpu_package_prepared")

    def test_resolve_entry_by_profile_id(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(entries, profile_id="apple-metal-gemma1b-plan")
        self.assertEqual(entry.workload, "gemma1b")
        self.assertEqual(entry.surface, "plan")

    def test_resolve_backend_entry_by_profile_id(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(entries, profile_id="amd-vulkan-backend-release")
        self.assertEqual(entry.surface, "backend")
        self.assertEqual(entry.preset, "release")

    def test_build_compare_argv_uses_canonical_cli(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(entries, profile_id="apple-metal-gemma64-package-cold")
        argv = build_compare_argv(entry, passthrough=["--iterations", "20"])
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(argv[1], str(DEFAULT_COMPARE_CLI))
        self.assertEqual(argv[2], "compare")
        self.assertIn("--config", argv)
        self.assertIn("--boundary", argv)
        self.assertIn("package_surface", argv)
        self.assertIn("--runtime-host", argv)
        self.assertIn("node", argv)
        self.assertIn("--temperature", argv)
        self.assertIn("cold", argv)
        self.assertIn("--comparison-view", argv)
        self.assertIn("doe_vs_node_webgpu_package", argv)
        self.assertIn("--iterations", argv)
        self.assertIn("20", argv)
        self.assertIn(
            str(REPO_ROOT / "bench/native-compare/compare.config.apple.metal.gemma64.node-package.ir.json"),
            argv,
        )

    def test_build_compare_argv_resolves_config_relative_to_custom_catalog(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-promoted-compare-") as tmpdir:
            tmp = Path(tmpdir)
            catalog_path = tmp / "catalog.json"
            config_path = tmp / "custom.compare.json"
            config_path.write_text("{}", encoding="utf-8")
            catalog_path.write_text(
                json.dumps({
                    "schemaVersion": 4,
                    "entries": [
                        {
                            "id": "custom-backend-compare",
                            "backend": "custom",
                            "surface": "backend",
                            "preset": "compare",
                            "mode": "default",
                            "benchmarkClass": "backend-runtime-preset",
                            "baselineExecutorId": "doe_direct_metal",
                            "comparisonExecutorId": "dawn_delegate_metal",
                            "configPath": "custom.compare.json",
                            "description": "custom entry",
                        }
                    ],
                }),
                encoding="utf-8",
            )
            entries = load_catalog(catalog_path)
            entry = resolve_entry(entries, profile_id="custom-backend-compare")
            argv = build_compare_argv(entry, catalog_path=catalog_path)
            self.assertEqual(Path(argv[4]).resolve(), config_path.resolve())

    def test_missing_workload_raises_clear_error(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        with self.assertRaises(ValueError):
            resolve_entry(
                entries,
                backend="apple-metal",
                boundary="package_surface",
                workload="gemma270m-literal",
            )

    def test_package_runtime_is_rejected_for_non_package_surface(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        with self.assertRaises(ValueError):
            resolve_entry(
                entries,
                backend="apple-metal",
                surface="plan",
                workload="gemma64",
                package_runtime="bun",
            )

    def test_preset_and_workload_cannot_both_be_set(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        with self.assertRaises(ValueError):
            resolve_entry(
                entries,
                backend="apple-metal",
                surface="plan",
                preset="compare",
                workload="gemma64",
            )


if __name__ == "__main__":
    unittest.main()
