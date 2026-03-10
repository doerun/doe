#!/usr/bin/env python3
"""Local host preflight for Dawn-vs-Doe benchmark execution."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

ADAPTER_HEADER_RE = re.compile(r'^\s*-\s+"(?P<name>[^"]+)"\s+-\s+"(?P<driver>.+)"\s*$')
ADAPTER_FIELD_RE = re.compile(r'^\s*(?P<key>\w+):\s*(?P<value>.+?)\s*$')
INCOMPATIBLE_DRIVER_RE = re.compile(r"Could not open device (?P<device>/dev/dri/[^:]+): Permission denied")
VULKANINFO_GPU_RE = re.compile(r"^GPU(?P<ordinal>\d+):\s*$")


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


def parse_vulkaninfo_summary(output: str) -> list[dict[str, str]]:
    gpus: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in output.splitlines():
        header = VULKANINFO_GPU_RE.match(raw_line.strip())
        if header:
            if current is not None:
                gpus.append(current)
            current = {"ordinal": header.group("ordinal")}
            continue
        if current is None:
            continue
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        current[key.strip()] = value.strip()
    if current is not None:
        gpus.append(current)
    return gpus


def probe_vulkaninfo_gpus() -> tuple[list[dict[str, str]], str]:
    command = ["vulkaninfo", "--summary"]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as error:
        return [], f"failed to execute vulkaninfo: {error}"
    if completed.returncode != 0:
        return [], f"vulkaninfo failed (rc={completed.returncode})"
    return parse_vulkaninfo_summary(completed.stdout), "ok"


def probe_doe_adapter(runtime_bin: Path) -> tuple[dict[str, object] | None, str]:
    if not runtime_bin.exists():
        return None, f"missing Doe runtime: {runtime_bin}"

    with tempfile.TemporaryDirectory(prefix="fawn-doe-preflight-") as tmpdir:
        tmp_path = Path(tmpdir)
        commands_path = tmp_path / "commands.json"
        trace_meta_path = tmp_path / "trace-meta.json"
        commands_path.write_text(
            json.dumps([{"kind": "barrier", "dependency_count": 1}], ensure_ascii=True),
            encoding="utf-8",
        )
        command = [
            "env",
            "LD_LIBRARY_PATH=bench/vendor/dawn/out/Release:" + os.environ.get("LD_LIBRARY_PATH", ""),
            str(runtime_bin),
            "--commands",
            str(commands_path),
            "--vendor",
            "amd",
            "--api",
            "vulkan",
            "--family",
            "gfx11",
            "--driver",
            "24.0.0",
            "--backend",
            "native",
            "--backend-lane",
            "vulkan_doe_comparable",
            "--execute",
            "--trace-meta",
            str(trace_meta_path),
        ]
        try:
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
        except OSError as error:
            return None, f"failed to execute Doe adapter probe: {error}"
        if completed.returncode != 0:
            return None, f"Doe adapter probe failed (rc={completed.returncode}): {shlex.join(command)}"
        try:
            payload = json.loads(trace_meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return None, f"failed to read Doe trace-meta probe: {error}"
        if not isinstance(payload, dict):
            return None, "Doe trace-meta probe did not produce an object"
        return payload, "ok"


def resolve_doe_vulkan_identity(
    runtime_bin: Path,
) -> tuple[dict[str, str] | None, dict[str, object] | None, str]:
    trace_meta, probe_message = probe_doe_adapter(runtime_bin)
    if trace_meta is None:
        return None, None, probe_message

    adapter_ordinal = trace_meta.get("adapterOrdinal")
    if not isinstance(adapter_ordinal, int) or adapter_ordinal < 0:
        return None, trace_meta, "Doe adapter probe did not emit adapterOrdinal"

    gpus, vulkaninfo_message = probe_vulkaninfo_gpus()
    if not gpus:
        return None, trace_meta, vulkaninfo_message

    ordinal_text = str(adapter_ordinal)
    for gpu in gpus:
        if gpu.get("ordinal") == ordinal_text:
            return gpu, trace_meta, "ok"
    return None, trace_meta, f"vulkaninfo did not report GPU ordinal {adapter_ordinal}"


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


def probe_dawn_adapters(dawn_binary: Path, backend: str, vendor_id: str) -> tuple[list[dict[str, str]], str]:
    if not dawn_binary.exists():
        return [], f"missing dawn binary: {dawn_binary}"
    command = [
        str(dawn_binary),
        "--gtest_list_tests",
        f"--backend={backend}",
        f"--adapter-vendor-id={vendor_id}",
    ]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as error:
        return [], f"failed to execute Dawn adapter probe: {error}"
    if completed.returncode != 0:
        return [], f"Dawn adapter probe failed (rc={completed.returncode}): {shlex.join(command)}"
    return parse_dawn_adapters(f"{completed.stdout}\n{completed.stderr}"), "ok"


def main() -> int:
    args = parse_args()

    checks: list[dict[str, object]] = []

    runtime_bin = Path("zig/zig-out/bin/doe-zig-runtime")
    dawn_bin = Path("bench/vendor/dawn/out/Release/dawn_perf_tests")
    lib_webgpu = Path("bench/vendor/dawn/out/Release/libwebgpu.so")
    lib_wgpu_native = Path("bench/vendor/dawn/out/Release/libwgpu_native.so")

    for name, path in (
        ("doeRuntime", runtime_bin),
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
        dawn_adapters, dawn_adapters_message = probe_dawn_adapters(dawn_bin, amd_backend, amd_vendor_id)
        doe_identity, doe_trace_meta, doe_probe_message = resolve_doe_vulkan_identity(runtime_bin)
        doe_matches_amd = (
            doe_identity is not None
            and str(doe_identity.get("vendorID", "")).strip().lower() == amd_vendor_id
        )
        dawn_identity_match = False
        dawn_identity_message = dawn_adapters_message
        checks.append(
            {
                "name": "strictAmdDawnAdapterProbe",
                "ok": ok_adapter_probe,
                "message": msg_adapter_probe,
            }
        )
        checks.append(
            {
                "name": "strictAmdDoeAdapterProbe",
                "ok": doe_identity is not None,
                "message": (
                    "ok"
                    if doe_identity is not None
                    else doe_probe_message
                ),
            }
        )
        checks.append(
            {
                "name": "strictAmdDoeAdapterIdentity",
                "ok": doe_matches_amd,
                "message": (
                    "ok"
                    if doe_matches_amd
                    else (
                        "Doe selected a non-AMD Vulkan adapter"
                        if doe_identity is not None
                        else "Doe adapter identity unavailable"
                    )
                ),
            }
        )
        if doe_identity is not None and dawn_adapters:
            doe_vendor = str(doe_identity.get("vendorID", "")).strip().lower()
            doe_device = str(doe_identity.get("deviceID", "")).strip().lower()
            doe_name = str(doe_identity.get("deviceName", "")).strip()
            dawn_identity_match = any(
                str(adapter.get("backend", "")).strip().lower() == amd_backend
                and str(adapter.get("vendorId", "")).split(",")[0].strip().lower() == doe_vendor
                and str(adapter.get("deviceId", "")).split(",")[0].strip().lower() == doe_device
                for adapter in dawn_adapters
            )
            dawn_identity_message = (
                "ok"
                if dawn_identity_match
                else (
                    "strict AMD Vulkan comparability requires Doe and Dawn to resolve to the same "
                    f"vendor/device identity; Doe selected {doe_name} "
                    f"(vendorId={doe_vendor}, deviceId={doe_device})"
                )
            )
            checks.append(
                {
                    "name": "strictAmdDoeDawnIdentityMatch",
                    "ok": dawn_identity_match,
                    "message": dawn_identity_message,
                }
            )
        checks.append(
            {
                "name": "strictAmdIdentityRequirement",
                "ok": ok_render and in_render_group and ok_adapter_probe and doe_matches_amd and dawn_identity_match,
                "message": (
                    "ok"
                    if ok_render and in_render_group and ok_adapter_probe and doe_matches_amd and dawn_identity_match
                    else (
                        "strict AMD Vulkan runs require accessible render node, render group, and "
                        f"matching Doe/Dawn {amd_backend} vendor/device identity for vendor {amd_vendor_id}"
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
            "Use bench/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json when AMD adapter constraints are unavailable.",
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
