#!/usr/bin/env python3
"""Local host preflight for Dawn-vs-Fawn benchmark execution."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


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
        checks.append(
            {
                "name": "strictAmdVendorRequirement",
                "ok": ok_render and in_render_group,
                "message": (
                    "ok"
                    if ok_render and in_render_group
                    else (
                        "strict AMD Vulkan runs require accessible render node and render group; "
                        f"requested vendor id is {amd_vendor_id}"
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
