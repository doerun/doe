"""Tests for Apple Metal pipeline cache state in trace_meta -> runtimeIdentity.

Covers:
- _pipeline_cache_telemetry reader (nested object, legacy fallback, absent)
- _resolve_metal_cache_asymmetry skips auto-flag when cache state=disabled
- default Apple Metal executor templates disable the pipeline cache
- explicit cache opt-in and no-cache executor templates
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from native_compare_modules.executor_registry import (
    resolve_executor_boundary,
    resolve_executor_command_template,
)
from native_compare_modules.run_artifact import (
    _pipeline_cache_telemetry,
    _resolve_metal_cache_asymmetry,
)


class _FakeWorkloadSpec:
    def __init__(self, *, in_manifest: bool) -> None:
        self.api = "metal"
        self.vendor = "apple"
        self.commands_path = (
            "examples/cached_kernel.json" if in_manifest else "examples/uncached_kernel.json"
        )
        self.path_asymmetry = False
        self.path_asymmetry_note = ""


class PipelineCacheTelemetryReaderTests(unittest.TestCase):
    def test_reads_nested_object(self) -> None:
        result = _pipeline_cache_telemetry(
            {
                "pipelineCache": {
                    "state": "enabled",
                    "reason": "default",
                    "warmupCount": 22,
                    "warmupNs": 12_345_000,
                }
            }
        )
        self.assertEqual(
            result,
            {
                "state": "enabled",
                "reason": "default",
                "warmupCount": 22,
                "warmupNs": 12_345_000,
            },
        )

    def test_falls_back_to_legacy_top_level(self) -> None:
        result = _pipeline_cache_telemetry(
            {"pipelineCacheWarmupCount": 5, "pipelineCacheWarmupNs": 1_000_000}
        )
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["reason"], "unknown")
        self.assertEqual(result["warmupCount"], 5)
        self.assertEqual(result["warmupNs"], 1_000_000)

    def test_returns_none_when_absent(self) -> None:
        self.assertIsNone(_pipeline_cache_telemetry({}))
        self.assertIsNone(_pipeline_cache_telemetry({"unrelated": 7}))

    def test_partial_nested_fills_defaults(self) -> None:
        result = _pipeline_cache_telemetry({"pipelineCache": {"state": "disabled"}})
        self.assertEqual(result["state"], "disabled")
        self.assertEqual(result["reason"], "unknown")
        self.assertEqual(result["warmupCount"], 0)
        self.assertEqual(result["warmupNs"], 0)


class CacheAsymmetryResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch(
            "native_compare_modules.run_artifact.metal_cache_manifest"
        )
        self.mock_manifest = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_manifest.auto_path_asymmetry_note.return_value = "<auto note>"

    def test_non_manifest_workload_not_flagged(self) -> None:
        self.mock_manifest.workload_dispatches_cached_kernel.return_value = False
        flag, note = _resolve_metal_cache_asymmetry(
            workload_spec=_FakeWorkloadSpec(in_manifest=False),
            declared=False,
            declared_note="",
            pipeline_cache_state="enabled",
            pipeline_cache_reason="default",
        )
        self.assertFalse(flag)
        self.assertEqual(note, "")

    def test_manifest_workload_with_cache_active_is_flagged(self) -> None:
        self.mock_manifest.workload_dispatches_cached_kernel.return_value = True
        flag, note = _resolve_metal_cache_asymmetry(
            workload_spec=_FakeWorkloadSpec(in_manifest=True),
            declared=False,
            declared_note="",
            pipeline_cache_state="enabled",
            pipeline_cache_reason="default",
        )
        self.assertTrue(flag)
        self.assertEqual(note, "<auto note>")

    def test_manifest_workload_with_cli_flag_not_flagged(self) -> None:
        self.mock_manifest.workload_dispatches_cached_kernel.return_value = True
        flag, note = _resolve_metal_cache_asymmetry(
            workload_spec=_FakeWorkloadSpec(in_manifest=True),
            declared=False,
            declared_note="",
            pipeline_cache_state="disabled",
            pipeline_cache_reason="cli-flag",
        )
        self.assertFalse(flag)
        self.assertEqual(note, "")

    def test_manifest_workload_dawn_delegate_not_flagged(self) -> None:
        self.mock_manifest.workload_dispatches_cached_kernel.return_value = True
        flag, note = _resolve_metal_cache_asymmetry(
            workload_spec=_FakeWorkloadSpec(in_manifest=True),
            declared=False,
            declared_note="",
            pipeline_cache_state="disabled",
            pipeline_cache_reason="non-doe-backend",
        )
        self.assertFalse(flag)

    def test_manifest_workload_non_mac_not_flagged(self) -> None:
        self.mock_manifest.workload_dispatches_cached_kernel.return_value = True
        flag, _ = _resolve_metal_cache_asymmetry(
            workload_spec=_FakeWorkloadSpec(in_manifest=True),
            declared=False,
            declared_note="",
            pipeline_cache_state="disabled",
            pipeline_cache_reason="platform-unsupported",
        )
        self.assertFalse(flag)

    def test_declared_asymmetry_preserved_even_with_disabled_cache(self) -> None:
        self.mock_manifest.workload_dispatches_cached_kernel.return_value = True
        flag, note = _resolve_metal_cache_asymmetry(
            workload_spec=_FakeWorkloadSpec(in_manifest=True),
            declared=True,
            declared_note="UMA upload skips staging",
            pipeline_cache_state="disabled",
            pipeline_cache_reason="cli-flag",
        )
        self.assertTrue(flag)
        self.assertEqual(note, "UMA upload skips staging")

    def test_declared_asymmetry_preserved_when_not_in_manifest(self) -> None:
        self.mock_manifest.workload_dispatches_cached_kernel.return_value = False
        flag, note = _resolve_metal_cache_asymmetry(
            workload_spec=_FakeWorkloadSpec(in_manifest=False),
            declared=True,
            declared_note="UMA upload",
            pipeline_cache_state="enabled",
            pipeline_cache_reason="default",
        )
        self.assertTrue(flag)
        self.assertEqual(note, "UMA upload")


class NoCacheExecutorTemplateTests(unittest.TestCase):
    def test_doe_direct_metal_no_cache_template(self) -> None:
        template = resolve_executor_command_template("doe_direct_metal_no_cache")
        self.assertIn("doe-zig-runtime", template)
        self.assertIn("--backend-lane metal_doe_comparable", template)
        self.assertIn("--no-pipeline-cache", template)
        self.assertEqual(
            resolve_executor_boundary("doe_direct_metal_no_cache"), "commands"
        )

    def test_dawn_delegate_metal_no_cache_template(self) -> None:
        template = resolve_executor_command_template("dawn_delegate_metal_no_cache")
        self.assertIn("doe-zig-runtime", template)
        self.assertIn("--backend-lane metal_dawn_release", template)
        self.assertIn("--no-pipeline-cache", template)
        self.assertEqual(
            resolve_executor_boundary("dawn_delegate_metal_no_cache"), "commands"
        )

    def test_default_metal_executors_disable_pipeline_cache(self) -> None:
        for executor_id in ("doe_direct_metal", "dawn_delegate_metal"):
            template = resolve_executor_command_template(executor_id)
            self.assertIn(
                "--no-pipeline-cache",
                template,
                msg=f"{executor_id} must disable pipeline cache by default",
            )

    def test_cache_opt_in_executors_omit_no_cache_flag(self) -> None:
        for executor_id in ("doe_direct_metal_cache", "dawn_delegate_metal_cache"):
            template = resolve_executor_command_template(executor_id)
            self.assertNotIn(
                "--no-pipeline-cache",
                template,
                msg=f"{executor_id} unexpectedly carries --no-pipeline-cache",
            )

    def test_vulkan_package_cache_executors_set_explicit_cache_dir(self) -> None:
        for executor_id in (
            "doe_node_webgpu_prepared_resident_buffer_loads_vulkan_cache",
            "doe_bun_package_prepared_resident_buffer_loads_vulkan_cache",
        ):
            template = resolve_executor_command_template(executor_id)
            self.assertIn("DOE_PIPELINE_CACHE_DIR={pipeline_cache_dir}", template)
            self.assertIn("--resident-buffer-loads", template)
            self.assertEqual(resolve_executor_boundary(executor_id), "plan")


if __name__ == "__main__":
    unittest.main()
