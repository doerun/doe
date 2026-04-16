"""Tests for the Metal pipeline cache manifest reader and workload detector."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.metal_pipeline_cache_manifest import (
    auto_path_asymmetry_note,
    commands_dispatched_kernel_names,
    is_apple_metal_workload,
    load_compute_kernel_set,
    workload_dispatches_cached_kernel,
)


class TestManifestParser(unittest.TestCase):
    def test_load_compute_kernel_set_from_real_manifest(self) -> None:
        kernels = load_compute_kernel_set()
        # Real manifest has 9 named compute kernels at the time of writing;
        # assert presence of the key cache-asymmetric ones rather than count
        # so the test survives manifest evolution.
        for expected in (
            "workgroup_atomic",
            "workgroup_non_atomic",
            "dispatch_noop",
            "shader_robustness_matmul_512_f32",
            "concurrent_execution_runsingle_u32",
            "zero_initialize_workgroup_memory_2048",
        ):
            self.assertIn(expected, kernels, f"manifest missing {expected!r}")

    def test_load_returns_empty_set_when_manifest_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(load_compute_kernel_set(Path(tmpdir) / "missing.manifest"), set())

    def test_load_parses_minimal_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "test.manifest"
            manifest.write_text("R:5\nC:foo\nC:bar\n# comment\nC:baz\n", encoding="utf-8")
            self.assertEqual(load_compute_kernel_set(manifest), {"foo", "bar", "baz"})

    def test_render_entries_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "render.manifest"
            manifest.write_text("R:99\n", encoding="utf-8")
            self.assertEqual(load_compute_kernel_set(manifest), set())


class TestCommandsDispatchedKernelNames(unittest.TestCase):
    def test_strips_wgsl_extension(self) -> None:
        commands = [
            {"kind": "kernel_dispatch", "kernel": "workgroup_atomic.wgsl", "x": 1},
        ]
        self.assertEqual(commands_dispatched_kernel_names(commands), {"workgroup_atomic"})

    def test_recognizes_kernel_name_alias(self) -> None:
        commands = [
            {"command": "kernel_dispatch", "kernel_name": "dispatch_noop.wgsl", "x": 1},
        ]
        self.assertEqual(commands_dispatched_kernel_names(commands), {"dispatch_noop"})

    def test_skips_non_dispatch_commands(self) -> None:
        commands = [
            {"kind": "buffer_write", "kernel": "irrelevant.wgsl"},
            {"kind": "kernel_dispatch", "kernel": "compute_a.wgsl"},
        ]
        self.assertEqual(commands_dispatched_kernel_names(commands), {"compute_a"})

    def test_handles_empty_or_invalid(self) -> None:
        self.assertEqual(commands_dispatched_kernel_names([]), set())
        self.assertEqual(commands_dispatched_kernel_names("not a list"), set())


class TestWorkloadDispatchesCachedKernel(unittest.TestCase):
    def test_non_metal_lane_returns_false(self) -> None:
        # Vulkan workload dispatching a cached kernel name still returns False
        # because the cache code path is gated by builtin.os.tag == .macos.
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = Path(tmpdir) / "cmd.json"
            cmd.write_text(
                json.dumps([{"kind": "kernel_dispatch", "kernel": "workgroup_atomic.wgsl"}]),
                encoding="utf-8",
            )
            self.assertFalse(
                workload_dispatches_cached_kernel(
                    workload_api="vulkan",
                    workload_vendor="amd",
                    commands_path=cmd,
                    cache_set={"workgroup_atomic"},
                    repo_root=Path(tmpdir),
                )
            )

    def test_apple_metal_with_cached_kernel_returns_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = Path(tmpdir) / "cmd.json"
            cmd.write_text(
                json.dumps([{"kind": "kernel_dispatch", "kernel": "workgroup_atomic.wgsl"}]),
                encoding="utf-8",
            )
            self.assertTrue(
                workload_dispatches_cached_kernel(
                    workload_api="metal",
                    workload_vendor="apple",
                    commands_path=cmd,
                    cache_set={"workgroup_atomic"},
                    repo_root=Path(tmpdir),
                )
            )

    def test_apple_metal_with_uncached_kernel_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = Path(tmpdir) / "cmd.json"
            cmd.write_text(
                json.dumps([{"kind": "kernel_dispatch", "kernel": "novel_kernel.wgsl"}]),
                encoding="utf-8",
            )
            self.assertFalse(
                workload_dispatches_cached_kernel(
                    workload_api="metal",
                    workload_vendor="apple",
                    commands_path=cmd,
                    cache_set={"workgroup_atomic"},
                    repo_root=Path(tmpdir),
                )
            )

    def test_missing_commands_path_returns_false(self) -> None:
        self.assertFalse(
            workload_dispatches_cached_kernel(
                workload_api="metal",
                workload_vendor="apple",
                commands_path="/nonexistent/path.json",
                cache_set={"workgroup_atomic"},
            )
        )


class TestIsAppleMetal(unittest.TestCase):
    def test_apple_metal_lane(self) -> None:
        self.assertTrue(is_apple_metal_workload("metal", "apple"))
        self.assertTrue(is_apple_metal_workload("Metal", "Apple"))

    def test_other_lanes(self) -> None:
        self.assertFalse(is_apple_metal_workload("vulkan", "amd"))
        self.assertFalse(is_apple_metal_workload("d3d12", "intel"))
        self.assertFalse(is_apple_metal_workload("metal", "intel"))


class TestCanonicalNote(unittest.TestCase):
    def test_note_mentions_archive_path_and_runtime_file(self) -> None:
        note = auto_path_asymmetry_note()
        self.assertIn("MTLBinaryArchive", note)
        self.assertIn("doe_pipeline_archive.metallib", note)
        self.assertIn("metal_native_runtime.zig", note)
        self.assertIn("Dawn delegate", note)


if __name__ == "__main__":
    unittest.main()
