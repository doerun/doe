#!/usr/bin/env python3
"""Tests for Chromium source checkout readiness checks."""

from __future__ import annotations

from pathlib import Path

from bench.tools import check_chromium_source_checkout as checkout


def _write_tool(bin_dir: Path, name: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def test_chromium_source_checkout_reports_missing_source_and_tools(tmp_path: Path) -> None:
    report = checkout.check_checkout(
        root=tmp_path,
        source_root_text="browser/chromium/src",
        require_ready=False,
        require_runtime_selector=False,
        path_env=str(tmp_path / "empty-bin"),
    )

    assert report["status"] == "blocked"
    assert "source_root" in report["missingRequired"]
    assert "tool:gclient" in report["missingRequired"]
    assert report["requireReady"] is False
    assert report["requireRuntimeSelector"] is False


def test_chromium_source_checkout_passes_with_markers_and_tools(tmp_path: Path) -> None:
    source_root = tmp_path / "browser" / "chromium" / "src"
    for marker in checkout.REQUIRED_MARKERS:
        marker_path = source_root / marker
        if "." in Path(marker).name:
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.write_text("", encoding="utf-8")
        else:
            marker_path.mkdir(parents=True, exist_ok=True)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for command in checkout.REQUIRED_TOOLS:
        _write_tool(bin_dir, command)

    report = checkout.check_checkout(
        root=tmp_path,
        source_root_text="browser/chromium/src",
        require_ready=True,
        require_runtime_selector=False,
        path_env=str(bin_dir),
    )

    assert report["status"] == "pass"
    assert report["missingRequired"] == []
    assert report["requireReady"] is True


def test_chromium_source_checkout_rejects_parent_traversal(tmp_path: Path) -> None:
    report = checkout.check_checkout(
        root=tmp_path,
        source_root_text="../src",
        require_ready=True,
        require_runtime_selector=False,
        path_env="",
    )

    assert report["status"] == "blocked"
    assert report["checks"][0]["checkId"] == "source_root"
    assert report["checks"][0]["message"] == "Chromium source root must be repo-relative or absolute without parent traversal"


def test_chromium_source_checkout_can_require_runtime_selector_markers(tmp_path: Path) -> None:
    source_root = tmp_path / "browser" / "chromium" / "src"
    for marker in checkout.REQUIRED_MARKERS:
        marker_path = source_root / marker
        if "." in Path(marker).name:
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.write_text("", encoding="utf-8")
        else:
            marker_path.mkdir(parents=True, exist_ok=True)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for command in checkout.REQUIRED_TOOLS:
        _write_tool(bin_dir, command)

    report = checkout.check_checkout(
        root=tmp_path,
        source_root_text="browser/chromium/src",
        require_ready=True,
        require_runtime_selector=True,
        path_env=str(bin_dir),
    )

    assert report["status"] == "blocked"
    assert report["requireRuntimeSelector"] is True
    assert "selector:runtime_switch" in report["missingRequired"]
    assert "selector:initialization_failure_reason" in report["missingRequired"]
    assert "selector:symbol_failure_reason" in report["missingRequired"]
    assert "selector:wire_proc_table_failure_reason" in report["missingRequired"]
    assert "selector:wire_proc_table_loader" in report["missingRequired"]
    assert "selector:doe_wire_runtime_instance" in report["missingRequired"]
    assert "selector:doe_wire_runtime_lifecycle_test" in report["missingRequired"]
    assert "selector:doe_shared_image_iosurface_bridge" in report["missingRequired"]
    assert "selector:doe_shared_image_iosurface_representation" in report["missingRequired"]
    assert "selector:doe_shared_image_native_import" in report["missingRequired"]
    assert "selector:doe_shared_image_native_begin_access" in report["missingRequired"]
    assert "selector:doe_shared_image_native_end_access" in report["missingRequired"]
    assert "selector:doe_shared_image_iosurface_handle" in report["missingRequired"]
    assert "selector:doe_shared_buffer_unsupported" in report["missingRequired"]
    assert "selector:doe_shared_buffer_fails_closed" in report["missingRequired"]
    assert "selector:doe_present_shared_texture_end_access" in report["missingRequired"]
    assert "selector:render_proc_surface" in report["missingRequired"]
    assert "selector:external_texture_proc_surface" in report["missingRequired"]
    assert "selector:adapter_denylist_detail" in report["missingRequired"]
    assert "selector:adapter_denylist_vendor_id" in report["missingRequired"]
    assert "selector:adapter_denylist_blocklist_reason" in report["missingRequired"]
    assert "selector:adapter_denylist_source_fields_test" in report["missingRequired"]


def test_chromium_source_checkout_passes_with_runtime_selector_markers(tmp_path: Path) -> None:
    source_root = tmp_path / "browser" / "chromium" / "src"
    for marker in checkout.REQUIRED_MARKERS:
        marker_path = source_root / marker
        if "." in Path(marker).name:
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.write_text("", encoding="utf-8")
        else:
            marker_path.mkdir(parents=True, exist_ok=True)
    decoder = source_root / "gpu" / "command_buffer" / "service" / "webgpu_decoder_impl.cc"
    decoder.parent.mkdir(parents=True, exist_ok=True)
    decoder.write_text(
        "\n".join(
            [
                "use-webgpu-runtime",
                "disable-webgpu-doe",
                "doe-webgpu-library-path",
                "runtime_artifact_load_failed",
                "runtime_initialization_failed",
                "symbol_surface_incomplete",
                "wire_proc_table_incomplete",
                "LoadDoeWireProcTable",
                "doe_wire_runtime_.instance",
                "doe_shared_image_iosurface_bridge",
                "DoeSharedImageRepresentationAndAccess",
                "deviceImportSharedTextureMemory",
                "sharedTextureMemoryBeginAccess",
                "sharedTextureMemoryEndAccess",
                "doe_shared_buffer_unsupported",
                "<< kDoeSharedBufferUnsupported;\n    return error::kInvalidArguments;",
                "doe_present_shared_texture_end_access",
                "wgpuCommandEncoderBeginRenderPass",
                "wgpuQueueCopyExternalTextureForBrowser",
                "profile_denylisted",
                "adapter_denylist_detail",
                "vendor_id",
                "blocklist_reason",
                "unknown_selection_error",
            ]
        ),
        encoding="utf-8",
    )
    shared_image_header = (
        source_root
        / "gpu"
        / "command_buffer"
        / "service"
        / "shared_image"
        / "shared_image_representation.h"
    )
    shared_image_header.parent.mkdir(parents=True, exist_ok=True)
    shared_image_header.write_text("GetIOSurfaceForNativeImport", encoding="utf-8")
    test_source = source_root / "gpu" / "command_buffer" / "service" / "webgpu_decoder_unittest.cc"
    test_source.write_text(
        "\n".join(
            [
                "DoeWireRuntimeOwnsAndReleasesInstanceLifecycle",
                "DoeAdapterDenylistDetailCarriesSourceFields",
            ]
        ),
        encoding="utf-8",
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for command in checkout.REQUIRED_TOOLS:
        _write_tool(bin_dir, command)

    report = checkout.check_checkout(
        root=tmp_path,
        source_root_text="browser/chromium/src",
        require_ready=True,
        require_runtime_selector=True,
        path_env=str(bin_dir),
    )

    assert report["status"] == "pass"
    assert report["missingRequired"] == []
