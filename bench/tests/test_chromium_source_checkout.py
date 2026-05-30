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
    assert "selector:symbol_failure_reason" in report["missingRequired"]


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
                "symbol_surface_incomplete",
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
