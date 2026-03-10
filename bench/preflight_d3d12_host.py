#!/usr/bin/env python3
"""Windows D3D12 preflight for governed Dawn-vs-Doe compare lanes."""

from __future__ import annotations

import argparse
import json
import platform
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def check_file(path: Path) -> tuple[bool, str]:
    if path.exists() and path.is_file():
        return True, "ok"
    return False, f"missing file: {path}"


def run_probe(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as error:
        return False, f"failed to execute probe: {error}"
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"returnCode={completed.returncode}"
        return False, f"probe failed: {detail}"
    return True, "ok"


def probe_doe(runtime_bin: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="fawn-d3d12-preflight-") as tmpdir:
        tmp_path = Path(tmpdir)
        commands_path = tmp_path / "commands.json"
        trace_meta_path = tmp_path / "trace-meta.json"
        commands_path.write_text(
            json.dumps([{"kind": "barrier", "dependency_count": 1}], ensure_ascii=True),
            encoding="utf-8",
        )
        command = [
            str(runtime_bin),
            "--commands",
            str(commands_path),
            "--vendor",
            "generic",
            "--api",
            "d3d12",
            "--family",
            "d3d12",
            "--driver",
            "1.0.0",
            "--backend",
            "native",
            "--backend-lane",
            "d3d12_doe_comparable",
            "--execute",
            "--trace-meta",
            str(trace_meta_path),
        ]
        ok, message = run_probe(command)
        if not ok:
            return False, f"{message}: {shlex.join(command)}"
        try:
            payload = json.loads(trace_meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return False, f"failed to read Doe D3D12 trace-meta probe: {error}"
        if not isinstance(payload, dict):
            return False, "Doe D3D12 trace-meta probe did not emit an object"
        if payload.get("backendId") != "doe_d3d12":
            return False, f"unexpected backendId={payload.get('backendId')!r}"
        if payload.get("backendLane") != "d3d12_doe_comparable":
            return False, f"unexpected backendLane={payload.get('backendLane')!r}"
        if payload.get("fallbackUsed") is True:
            return False, "fallbackUsed=true is not allowed on strict D3D12 lanes"
        return True, "ok"


def main() -> int:
    args = parse_args()

    system = platform.system().strip().lower()
    checks: list[dict[str, object]] = []

    runtime_bin = Path("zig/zig-out/bin/doe-zig-runtime.exe")
    dawn_bin = Path("bench/vendor/dawn/out/Release/dawn_perf_tests.exe")

    checks.append(
        {
            "name": "windowsHost",
            "code": "host_windows_required",
            "ok": system == "windows",
            "message": "ok" if system == "windows" else "D3D12 benchmark lanes require a Windows x64 host",
        }
    )

    for name, code, path in (
        ("doeRuntime", "missing_runtime", runtime_bin),
        ("dawnPerfTests", "missing_dawn_perf_tests", dawn_bin),
    ):
        ok, message = check_file(path)
        checks.append({"name": name, "code": code, "ok": ok, "message": message})

    dxc = shutil.which("dxc.exe") or shutil.which("dxc")
    checks.append(
        {
            "name": "dxcCompiler",
            "code": "missing_dxc",
            "ok": dxc is not None,
            "message": "ok" if dxc is not None else "missing dxc.exe on PATH for live WGSL->HLSL->DXC workloads",
        }
    )

    if system == "windows" and dawn_bin.exists():
        ok, message = run_probe([str(dawn_bin), "--gtest_list_tests", "--backend=d3d12"])
        checks.append(
            {
                "name": "dawnD3D12AdapterProbe",
                "code": "dawn_d3d12_adapter_unavailable",
                "ok": ok,
                "message": message,
            }
        )
    else:
        checks.append(
            {
                "name": "dawnD3D12AdapterProbe",
                "code": "dawn_d3d12_adapter_unavailable",
                "ok": False,
                "message": "skipped until running on Windows with dawn_perf_tests.exe present",
            }
        )

    if system == "windows" and runtime_bin.exists():
        ok, message = probe_doe(runtime_bin)
        checks.append(
            {
                "name": "doeD3D12Probe",
                "code": "doe_d3d12_probe_failed",
                "ok": ok,
                "message": message,
            }
        )
    else:
        checks.append(
            {
                "name": "doeD3D12Probe",
                "code": "doe_d3d12_probe_failed",
                "ok": False,
                "message": "skipped until running on Windows with doe-zig-runtime.exe present",
            }
        )

    failed = [entry for entry in checks if not bool(entry["ok"])]
    payload = {
        "schemaVersion": 1,
        "surface": "backend_native",
        "laneId": "d3d12_doe_comparable",
        "hostProfile": "windows_d3d12",
        "ok": len(failed) == 0,
        "checkCount": len(checks),
        "failedCount": len(failed),
        "checks": checks,
        "recommendations": [
            "Run this preflight on a Windows x64 host before compare_dawn_vs_doe local D3D12 lanes.",
            "Keep dxc.exe on PATH for live WGSL-backed compute and pipeline workloads.",
            "Treat render and texture contracts as out of scope for the first D3D12 governed comparable lane.",
        ],
    }

    if args.emit_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"preflight ok={payload['ok']} failed={payload['failedCount']}")
        for entry in checks:
            state = "ok" if bool(entry["ok"]) else "fail"
            print(f"[{state}] {entry['name']} ({entry['code']}): {entry['message']}")

    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
