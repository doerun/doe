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

from bench.run_compare import (  # noqa: E402
    DEFAULT_COMPARE_SCRIPT,
    default_mode_for_surface,
    load_catalog,
    resolve_entry,
    build_compare_argv,
)


class PromotedCompareTests(unittest.TestCase):
    def test_default_mode_by_surface(self) -> None:
        self.assertEqual(default_mode_for_surface("native"), "default")
        self.assertEqual(default_mode_for_surface("direct"), "default")
        self.assertEqual(default_mode_for_surface("package"), "cold")

    def test_resolve_native_entry_by_preset(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(
            entries,
            backend="apple-metal",
            surface="native",
            preset="compare",
        )
        self.assertEqual(entry.id, "apple-metal-native-compare")
        self.assertEqual(entry.left_executor_id, "doe_direct_metal")
        self.assertEqual(entry.right_executor_id, "dawn_delegate_metal")

    def test_resolve_direct_entry_by_workload(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(
            entries,
            backend="apple-metal",
            surface="direct",
            workload="gemma270m-literal",
        )
        self.assertEqual(entry.id, "apple-metal-gemma270m-literal-direct")
        self.assertEqual(entry.left_executor_id, "doe_direct_plan_metal")
        self.assertEqual(entry.right_executor_id, "dawn_direct_metal")

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
        self.assertEqual(entry.left_executor_id, "doe_node_webgpu_prepared")
        self.assertEqual(entry.right_executor_id, "dawn_node_webgpu_prepared")

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
        self.assertEqual(entry.left_executor_id, "doe_bun_package_prepared")
        self.assertEqual(entry.right_executor_id, "bun_webgpu_package_prepared")

    def test_resolve_entry_by_profile_id(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(entries, profile_id="apple-metal-gemma1b-direct")
        self.assertEqual(entry.workload, "gemma1b")
        self.assertEqual(entry.surface, "direct")

    def test_resolve_native_entry_by_profile_id(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(entries, profile_id="amd-vulkan-native-release")
        self.assertEqual(entry.surface, "native")
        self.assertEqual(entry.preset, "release")

    def test_build_compare_argv_uses_existing_runner(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        entry = resolve_entry(entries, profile_id="apple-metal-gemma64-package-cold")
        argv = build_compare_argv(entry, passthrough=["--iterations", "20"])
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(argv[1], str(DEFAULT_COMPARE_SCRIPT))
        self.assertIn("--config", argv)
        self.assertIn("--iterations", argv)
        self.assertIn("20", argv)
        self.assertIn(
            str(REPO_ROOT / "bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.node-package.ir.json"),
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
                    "schemaVersion": 2,
                    "entries": [
                        {
                            "id": "custom-native-compare",
                            "backend": "custom",
                            "surface": "native",
                            "preset": "compare",
                            "mode": "default",
                            "benchmarkClass": "native-runtime-preset",
                            "leftExecutorId": "doe_direct_metal",
                            "rightExecutorId": "dawn_delegate_metal",
                            "configPath": "custom.compare.json",
                            "description": "custom entry",
                        }
                    ],
                }),
                encoding="utf-8",
            )
            entries = load_catalog(catalog_path)
            entry = resolve_entry(entries, profile_id="custom-native-compare")
            argv = build_compare_argv(entry, catalog_path=catalog_path)
            self.assertEqual(Path(argv[3]).resolve(), config_path.resolve())

    def test_missing_workload_raises_clear_error(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        with self.assertRaises(ValueError):
            resolve_entry(
                entries,
                backend="apple-metal",
                surface="package",
                workload="gemma270m-literal",
            )

    def test_package_runtime_is_rejected_for_non_package_surface(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        with self.assertRaises(ValueError):
            resolve_entry(
                entries,
                backend="apple-metal",
                surface="direct",
                workload="gemma64",
                package_runtime="bun",
            )

    def test_preset_and_workload_cannot_both_be_set(self) -> None:
        entries = load_catalog(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        with self.assertRaises(ValueError):
            resolve_entry(
                entries,
                backend="apple-metal",
                surface="direct",
                preset="compare",
                workload="gemma64",
            )


if __name__ == "__main__":
    unittest.main()
