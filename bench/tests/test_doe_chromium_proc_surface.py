#!/usr/bin/env python3
"""Tests for Doe Chromium proc-surface checks."""

from __future__ import annotations

import json
from pathlib import Path

from bench.tools import check_doe_chromium_proc_surface as proc_surface


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "doe-chromium-proc-surface.json"


def _load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _write_proc_table_header(root: Path, payload: dict) -> set[str]:
    header_path = root / payload["wireProcTable"]["tableHeaderPath"]
    header_path.parent.mkdir(parents=True, exist_ok=True)
    header_path.write_text(
        "\n".join(
            [
                "typedef struct DawnProcTable {",
                "    WGPUProcCreateInstance createInstance;",
                "    WGPUProcDeviceCreateTexture deviceCreateTexture;",
                "    WGPUProcQueueCopyExternalTextureForBrowser queueCopyExternalTextureForBrowser;",
                "} DawnProcTable;",
            ]
        ),
        encoding="utf-8",
    )
    behavior_source_path = root / payload["browserSharedMemoryBehavior"]["implementationSourcePath"]
    behavior_source_path.parent.mkdir(parents=True, exist_ok=True)
    behavior_source_path.write_text(
        "\n".join(
            [
                "pub fn wgpuDeviceCreateErrorBuffer() void {",
                "    _ = native.make(native.DoeBuffer);",
                "    _ = .{ .error_object = true };",
                "    labelOwnedObject(raw, d.label);",
                "    return raw;",
                "}",
                "pub fn wgpuDeviceCreateErrorTexture() void {",
                "    _ = native.make(native.DoeTexture);",
                "    _ = .{ .error_object = true };",
                "    labelOwnedObject(raw, d.label);",
                "    return raw;",
                "}",
                "const STYPE_SHARED_TEXTURE_MEMORY_IOSURFACE_DESCRIPTOR = 0x0005_0023;",
                "const WGPUSharedTextureMemoryIOSurfaceDescriptor = extern struct {};",
                "const DoeSharedTextureMemory = struct {};",
                "extern fn CFRetain() void;",
                "extern fn CFRelease() void;",
                "pub fn wgpuDeviceImportSharedTextureMemory() void {",
                "    _ = findIOSurfaceDescriptor(desc);",
                "    _ = external_texture_ops.importIOSurface(dev.mtl_device, iosurface);",
                "    _ = native.make(DoeSharedTextureMemory);",
                "    labelOwnedObject(raw, desc.label);",
                "    return raw;",
                "}",
                "pub fn wgpuSharedTextureMemoryCreateTexture() void {",
                "    _ = external_texture_ops.importIOSurface(",
                "    _ = native.make(native.DoeTexture);",
                "    _ = .{ .error_object = false, .mtl = imported.plane0 };",
                "    labelOwnedObject(raw, desc.label);",
                "    return raw;",
                "}",
                "pub fn wgpuSharedTextureMemoryBeginAccess() void {",
                "    shared_memory.in_access = true;",
                "    return abi_core.WGPUStatus_Success;",
                "}",
                "pub fn wgpuSharedTextureMemoryEndAccess() void {",
                "    state.initialized = abi_core.WGPU_TRUE;",
                "    shared_memory.in_access = false;",
                "    return abi_core.WGPUStatus_Success;",
                "}",
                "pub fn wgpuSharedTextureMemoryGetProperties() void {",
                "    out.usage = shared_memory.usage;",
                "    out.format = shared_memory.format;",
                "    return abi_core.WGPUStatus_Success;",
                "}",
                "pub fn wgpuDeviceImportSharedBufferMemory() void {",
                "    logUnsupported(\"wgpuDeviceImportSharedBufferMemory\");",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "wgpuCreateInstance",
        "wgpuDeviceCreateTexture",
        "wgpuQueueCopyExternalTextureForBrowser",
    }


def _local_proc_symbols(payload: dict) -> set[str]:
    return {
        row["symbol"]
        for row in payload["localWireProcSurface"]["requiredSymbols"]
    }


def test_doe_chromium_proc_surface_config_is_valid() -> None:
    assert proc_surface.validate_config(_load_config()) == []


def test_doe_chromium_proc_surface_passes_with_required_symbols(tmp_path: Path) -> None:
    payload = _load_config()
    library_path = tmp_path / "libwebgpu_doe_full.dylib"
    library_path.write_bytes(b"fake")
    symbols = {row["symbol"] for row in payload["requiredSymbols"]}
    wire_symbols = _write_proc_table_header(tmp_path, payload)

    report = proc_surface.check_proc_surface(
        payload,
        root=tmp_path,
        library_override=str(library_path),
        symbol_checker=lambda symbol: symbol in symbols,
        wire_proc_checker=lambda symbol: symbol in wire_symbols,
        local_proc_checker=lambda symbol: symbol in _local_proc_symbols(payload),
        instance_bootstrap_checker=lambda: (
            True,
            "Doe WGPU instance created and released",
        ),
    )

    assert report["status"] == "pass"
    assert report["missingRequired"] == []


def test_doe_chromium_proc_surface_reports_missing_symbol(tmp_path: Path) -> None:
    payload = _load_config()
    library_path = tmp_path / "libwebgpu_doe_full.dylib"
    library_path.write_bytes(b"fake")
    symbols = {row["symbol"] for row in payload["requiredSymbols"]}
    symbols.remove("wgpuQueueSubmit")
    wire_symbols = _write_proc_table_header(tmp_path, payload)

    report = proc_surface.check_proc_surface(
        payload,
        root=tmp_path,
        library_override=str(library_path),
        symbol_checker=lambda symbol: symbol in symbols,
        wire_proc_checker=lambda symbol: symbol in wire_symbols,
        local_proc_checker=lambda symbol: symbol in _local_proc_symbols(payload),
        instance_bootstrap_checker=lambda: (
            True,
            "Doe WGPU instance created and released",
        ),
    )

    assert report["status"] == "blocked"
    assert "symbol:wgpuQueueSubmit" in report["missingRequired"]


def test_doe_chromium_proc_surface_reports_instance_bootstrap_failure(
    tmp_path: Path,
) -> None:
    payload = _load_config()
    library_path = tmp_path / "libwebgpu_doe_full.dylib"
    library_path.write_bytes(b"fake")
    wire_symbols = _write_proc_table_header(tmp_path, payload)

    report = proc_surface.check_proc_surface(
        payload,
        root=tmp_path,
        library_override=str(library_path),
        symbol_checker=lambda _: True,
        wire_proc_checker=lambda symbol: symbol in wire_symbols,
        local_proc_checker=lambda symbol: symbol in _local_proc_symbols(payload),
        instance_bootstrap_checker=lambda: (
            False,
            "wgpuCreateInstance returned null",
        ),
    )

    assert report["status"] == "blocked"
    assert "instance_bootstrap" in report["missingRequired"]


def test_doe_chromium_proc_surface_reports_missing_library(tmp_path: Path) -> None:
    payload = _load_config()
    wire_symbols = _write_proc_table_header(tmp_path, payload)

    report = proc_surface.check_proc_surface(
        payload,
        root=tmp_path,
        library_override="missing/libwebgpu_doe_full.dylib",
        symbol_checker=lambda _: True,
        wire_proc_checker=lambda symbol: symbol in wire_symbols,
        local_proc_checker=lambda symbol: symbol in _local_proc_symbols(payload),
        instance_bootstrap_checker=lambda: (
            True,
            "Doe WGPU instance created and released",
        ),
    )

    assert report["status"] == "blocked"
    assert "library_path" in report["missingRequired"]


def test_doe_chromium_proc_surface_rejects_parent_traversal(tmp_path: Path) -> None:
    payload = _load_config()
    wire_symbols = _write_proc_table_header(tmp_path, payload)

    report = proc_surface.check_proc_surface(
        payload,
        root=tmp_path,
        library_override="../libwebgpu_doe_full.dylib",
        symbol_checker=lambda _: True,
        wire_proc_checker=lambda symbol: symbol in wire_symbols,
        local_proc_checker=lambda symbol: symbol in _local_proc_symbols(payload),
        instance_bootstrap_checker=lambda: (
            True,
            "Doe WGPU instance created and released",
        ),
    )

    assert report["status"] == "blocked"
    assert report["checks"][0]["checkId"] == "library_path"
    assert report["checks"][0]["message"] == "libraryPath must be repo-relative or absolute without parent traversal"


def test_doe_chromium_proc_surface_rejects_duplicate_symbol(tmp_path: Path) -> None:
    payload = _load_config()
    payload["requiredSymbols"].append(dict(payload["requiredSymbols"][0]))
    library_path = tmp_path / "libwebgpu_doe_full.dylib"
    library_path.write_bytes(b"fake")
    wire_symbols = _write_proc_table_header(tmp_path, payload)

    report = proc_surface.check_proc_surface(
        payload,
        root=tmp_path,
        library_override=str(library_path),
        symbol_checker=lambda _: True,
        wire_proc_checker=lambda symbol: symbol in wire_symbols,
        local_proc_checker=lambda symbol: symbol in _local_proc_symbols(payload),
        instance_bootstrap_checker=lambda: (
            True,
            "Doe WGPU instance created and released",
        ),
    )

    assert report["status"] == "blocked"
    assert "config:0" in report["missingRequired"]


def test_doe_chromium_proc_surface_reports_missing_wire_proc(tmp_path: Path) -> None:
    payload = _load_config()
    library_path = tmp_path / "libwebgpu_doe_full.dylib"
    library_path.write_bytes(b"fake")
    wire_symbols = _write_proc_table_header(tmp_path, payload)
    wire_symbols.remove("wgpuDeviceCreateTexture")

    report = proc_surface.check_proc_surface(
        payload,
        root=tmp_path,
        library_override=str(library_path),
        symbol_checker=lambda _: True,
        wire_proc_checker=lambda symbol: symbol in wire_symbols,
        local_proc_checker=lambda symbol: symbol in _local_proc_symbols(payload),
        instance_bootstrap_checker=lambda: (
            True,
            "Doe WGPU instance created and released",
        ),
    )

    assert report["status"] == "blocked"
    assert "wire_proc:wgpuDeviceCreateTexture" in report["missingRequired"]


def test_doe_chromium_proc_surface_reports_missing_local_wire_proc(tmp_path: Path) -> None:
    payload = _load_config()
    library_path = tmp_path / "libwebgpu_doe_full.dylib"
    library_path.write_bytes(b"fake")
    wire_symbols = _write_proc_table_header(tmp_path, payload)
    local_symbols = _local_proc_symbols(payload)
    local_symbols.remove("wgpuDeviceImportSharedTextureMemory")

    report = proc_surface.check_proc_surface(
        payload,
        root=tmp_path,
        library_override=str(library_path),
        symbol_checker=lambda _: True,
        wire_proc_checker=lambda symbol: symbol in wire_symbols,
        local_proc_checker=lambda symbol: symbol in local_symbols,
        instance_bootstrap_checker=lambda: (
            True,
            "Doe WGPU instance created and released",
        ),
    )

    assert report["status"] == "blocked"
    assert "local_wire_proc:wgpuDeviceImportSharedTextureMemory" in report["missingRequired"]


def test_doe_chromium_proc_surface_reports_missing_browser_shared_memory_behavior(
    tmp_path: Path,
) -> None:
    payload = _load_config()
    library_path = tmp_path / "libwebgpu_doe_full.dylib"
    library_path.write_bytes(b"fake")
    wire_symbols = _write_proc_table_header(tmp_path, payload)
    behavior_source_path = tmp_path / payload["browserSharedMemoryBehavior"]["implementationSourcePath"]
    behavior_source_path.write_text(
        "pub fn wgpuDeviceCreateErrorBuffer() void { return null; }",
        encoding="utf-8",
    )

    report = proc_surface.check_proc_surface(
        payload,
        root=tmp_path,
        library_override=str(library_path),
        symbol_checker=lambda _: True,
        wire_proc_checker=lambda symbol: symbol in wire_symbols,
        local_proc_checker=lambda symbol: symbol in _local_proc_symbols(payload),
        instance_bootstrap_checker=lambda: (
            True,
            "Doe WGPU instance created and released",
        ),
    )

    assert report["status"] == "blocked"
    assert "browser_shared_memory_behavior" in report["missingRequired"]


def test_doe_chromium_proc_surface_parses_local_proc_source(tmp_path: Path) -> None:
    payload = _load_config()
    source_path = tmp_path / payload["localWireProcSurface"]["resolverSourcePath"]
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        '\n'.join(
            f'if (symbolViewEq(name, "{symbol}")) return fnPtr(&stub);'
            for symbol in _local_proc_symbols(payload)
        ),
        encoding="utf-8",
    )

    symbols, parse_error = proc_surface.parse_local_proc_symbols(source_path)

    assert parse_error is None
    assert symbols == _local_proc_symbols(payload)
