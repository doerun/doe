#!/usr/bin/env python3
"""Local host preflight for Dawn-vs-Fawn benchmark execution."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

ADAPTER_HEADER_RE = re.compile(r'^\s*-\s+"(?P<name>[^"]+)"\s+-\s+"(?P<driver>.+)"\s*$')
ADAPTER_FIELD_RE = re.compile(r'^\s*(?P<key>\w+):\s*(?P<value>.+?)\s*$')
INCOMPATIBLE_DRIVER_RE = re.compile(r"Could not open device (?P<device>/dev/dri/[^:]+): Permission denied")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-amd-vulkan", action="store_true")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def check_file(path: Path) -> tuple[bool, str]:
    if path.exists() and path.is_file():
        return True, "ok"
    return False, f"missing file: {path}"


def check_readwrite(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing device node: {path}"
    readable = os.access(path, os.R_OK)
    writable = os.access(path, os.W_OK)
    if readable and writable:
        return True, "ok"
    return False, f"insufficient permissions on {path} (read={readable}, write={writable})"


def parse_dawn_adapters(output: str) -> list[dict[str, str]]:
    adapters: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in output.splitlines():
        header = ADAPTER_HEADER_RE.match(raw_line)
        if header:
            if current is not None:
                adapters.append(current)
            current = {
                "name": header.group("name").strip(),
                "driver": header.group("driver").strip(),
            }
            continue

        field = ADAPTER_FIELD_RE.match(raw_line)
        if field is None or current is None:
            continue
        key = field.group("key").strip()
        value = field.group("value").strip()
        current[key] = value
        if "," in value:
            for segment in value.split(", "):
                nested_field = ADAPTER_FIELD_RE.match(segment)
                if nested_field is None:
                    continue
                current[nested_field.group("key").strip()] = nested_field.group("value").strip()

    if current is not None:
        adapters.append(current)
    return adapters


def find_matching_adapter(adapters: list[dict[str, str]], backend: str, vendor_id: str) -> bool:
    backend_norm = backend.lower()
    vendor_norm = vendor_id.lower()
    for adapter in adapters:
        adapter_backend = str(adapter.get("backend", "")).strip().lower()
        adapter_vendor = str(adapter.get("vendorId", "")).split(",")[0].strip().lower()
        if adapter_backend == backend_norm and adapter_vendor == vendor_norm:
            return True
    return False


def format_adapter_summary(adapters: list[dict[str, str]]) -> str:
    if not adapters:
        return "  (no adapters reported)"
    lines: list[str] = []
    for adapter in adapters:
        lines.append(
            "  - "
            f"{adapter.get('name', '')} "
            f"(backend={adapter.get('backend', '')}, "
            f"vendorId={adapter.get('vendorId', '')}, "
            f"type={adapter.get('type', '')}, "
            f"architecture={adapter.get('architecture', '')})"
        )
    return "\n".join(lines)


def probe_dawn_adapter(dawn_binary: Path, backend: str, vendor_id: str) -> tuple[bool, str]:
    if not dawn_binary.exists():
        return False, f"missing dawn binary: {dawn_binary}"
    command = [
        str(dawn_binary),
        "--gtest_list_tests",
        f"--backend={backend}",
        f"--adapter-vendor-id={vendor_id}",
    ]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as error:
        return False, f"failed to execute Dawn adapter probe: {error}"

    combined_output = f"{completed.stdout}\n{completed.stderr}"
    adapters = parse_dawn_adapters(combined_output)
    adapter_found = find_matching_adapter(adapters, backend, vendor_id)
    permission_denied = bool(INCOMPATIBLE_DRIVER_RE.search(combined_output))

    if completed.returncode != 0:
        return (
            False,
            "Dawn adapter probe failed "
            f"(rc={completed.returncode}): {shlex.join(command)}",
        )
    if adapter_found:
        return True, "ok"

    reason = (
        "requested Dawn adapter is unavailable "
        f"(backend={backend}, vendor-id={vendor_id})\n"
        f"Detected adapters:\n{format_adapter_summary(adapters)}"
    )
    if permission_denied:
        reason += "\nHint: Vulkan reported permission denied opening /dev/dri render nodes."
    return False, reason


def main() -> int:
    args = parse_args()

    checks: list[dict[str, object]] = []

    runtime_bin = Path("zig/zig-out/bin/fawn-zig-runtime")
    dawn_bin = Path("bench/vendor/dawn/out/Release/dawn_perf_tests")
    lib_webgpu = Path("bench/vendor/dawn/out/Release/libwebgpu.so")
    lib_wgpu_native = Path("bench/vendor/dawn/out/Release/libwgpu_native.so")

    for name, path in (
        ("fawnRuntime", runtime_bin),
        ("dawnPerfTests", dawn_bin),
        ("libwebgpu", lib_webgpu),
        ("libwgpuNative", lib_wgpu_native),
    ):
        ok, message = check_file(path)
        checks.append({"name": name, "ok": ok, "message": message})

    render_node = Path("/dev/dri/renderD128")
    ok_render, msg_render = check_readwrite(render_node)
    checks.append({"name": "renderNodeAccess", "ok": ok_render, "message": msg_render})

    groups = set(os.getgroups())
    groups.add(os.getgid())
    groups.add(os.getegid())
    render_gid = None
    try:
        import grp

        render_gid = grp.getgrnam("render").gr_gid
    except Exception:
        render_gid = None

    in_render_group = render_gid is not None and render_gid in groups
    checks.append(
        {
            "name": "renderGroupMembership",
            "ok": in_render_group,
            "message": "ok" if in_render_group else "user is not in render group",
        }
    )

    if args.strict_amd_vulkan:
        amd_vendor_id = "0x1002"
        amd_backend = "vulkan"
        ok_adapter_probe, msg_adapter_probe = probe_dawn_adapter(dawn_bin, amd_backend, amd_vendor_id)
        checks.append(
            {
                "name": "strictAmdDawnAdapterProbe",
                "ok": ok_adapter_probe,
                "message": msg_adapter_probe,
            }
        )
        checks.append(
            {
                "name": "strictAmdVendorRequirement",
                "ok": ok_render and in_render_group and ok_adapter_probe,
                "message": (
                    "ok"
                    if ok_render and in_render_group and ok_adapter_probe
                    else (
                        "strict AMD Vulkan runs require accessible render node, render group, and "
                        f"a Dawn-visible {amd_backend} adapter for vendor {amd_vendor_id}"
                    )
                ),
            }
        )

    failed = [entry for entry in checks if not bool(entry["ok"])]
    status = {
        "ok": len(failed) == 0,
        "checkCount": len(checks),
        "failedCount": len(failed),
        "checks": checks,
        "recommendations": [
            "Set LD_LIBRARY_PATH=bench/vendor/dawn/out/Release:$LD_LIBRARY_PATH for native Fawn runs.",
            "If /dev/dri/renderD128 is denied, add your user to group render and re-login.",
            "Use bench/compare_dawn_vs_fawn.config.local.vulkan.extended.comparable.json when AMD adapter constraints are unavailable.",
        ],
    }

    if args.emit_json:
        print(json.dumps(status, indent=2))
    else:
        print(f"preflight ok={status['ok']} failed={status['failedCount']}")
        for entry in checks:
            state = "ok" if bool(entry["ok"]) else "fail"
            print(f"[{state}] {entry['name']}: {entry['message']}")

    return 0 if status["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
