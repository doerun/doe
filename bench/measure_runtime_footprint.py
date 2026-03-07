#!/usr/bin/env python3
"""Measure runtime binary/library footprint and optional build-wall timings."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--doe-bin",
        default="zig/zig-out/bin/doe-zig-runtime",
        help="Doe runtime binary path.",
    )
    parser.add_argument(
        "--doe-lib",
        default="",
        help="Doe shared library path (auto-detected when omitted).",
    )
    parser.add_argument(
        "--dawn-bin",
        default="bench/vendor/dawn/out/Release/dawn_perf_tests",
        help="Dawn benchmark binary path.",
    )
    parser.add_argument(
        "--doe-build-cmd",
        default="",
        help="Optional shell command to build Doe before measurement.",
    )
    parser.add_argument(
        "--dawn-build-cmd",
        default="",
        help="Optional shell command to build Dawn before measurement.",
    )
    parser.add_argument(
        "--build-cwd",
        default=".",
        help="Working directory for optional build commands.",
    )
    parser.add_argument(
        "--out-json",
        default="bench/out/runtime_footprint_report.json",
        help="JSON output path.",
    )
    parser.add_argument(
        "--out-md",
        default="bench/out/runtime_footprint_report.md",
        help="Markdown output path.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_shell(command: str, cwd: Path) -> dict[str, Any]:
    start = time.perf_counter()
    proc = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    wall_ms = (time.perf_counter() - start) * 1000.0
    return {
        "command": command,
        "cwd": str(cwd),
        "exitCode": proc.returncode,
        "wallMs": wall_ms,
        "stdoutTail": (proc.stdout or "").splitlines()[-20:],
        "stderrTail": (proc.stderr or "").splitlines()[-20:],
    }


def dependency_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    if os.name == "posix" and sys_platform() == "darwin":
        proc = subprocess.run(
            ["otool", "-L", str(path)],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            return []
        lines = proc.stdout.splitlines()[1:]
        deps: list[str] = []
        for line in lines:
            text = line.strip()
            if not text:
                continue
            deps.append(text.split(" (", 1)[0].strip())
        return deps
    if os.name == "posix":
        proc = subprocess.run(
            ["ldd", str(path)],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            return []
        deps: list[str] = []
        for line in proc.stdout.splitlines():
            text = line.strip()
            if not text:
                continue
            if "=>" in text:
                deps.append(text.split("=>", 1)[1].split("(", 1)[0].strip())
            else:
                deps.append(text.split("(", 1)[0].strip())
        return deps
    return []


def sys_platform() -> str:
    return os.uname().sysname.lower() if hasattr(os, "uname") else ""


def stripped_size_bytes(path: Path) -> int | None:
    if not path.exists():
        return None
    strip_bin = shutil.which("strip")
    if not strip_bin:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / path.name
        shutil.copy2(path, target)
        commands: list[list[str]] = []
        if sys_platform() == "darwin":
            commands.extend(
                [
                    [strip_bin, "-x", str(target)],
                    [strip_bin, "-S", str(target)],
                ]
            )
        else:
            commands.extend(
                [
                    [strip_bin, "--strip-unneeded", str(target)],
                    [strip_bin, str(target)],
                ]
            )
        for command in commands:
            proc = subprocess.run(command, capture_output=True, check=False)
            if proc.returncode == 0 and target.exists():
                return target.stat().st_size
    return None


def resolve_default_doe_lib() -> Path | None:
    candidates = [
        Path("zig/zig-out/lib/libwebgpu_doe.dylib"),
        Path("zig/zig-out/lib/libwebgpu_doe.so"),
        Path("zig/zig-out/lib/libwebgpu_doe.dll"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def measure_artifact(label: str, path: Path) -> dict[str, Any]:
    exists = path.exists()
    raw_size = path.stat().st_size if exists else None
    stripped = stripped_size_bytes(path) if exists else None
    deps = dependency_list(path) if exists else []
    return {
        "label": label,
        "path": str(path),
        "exists": exists,
        "rawSizeBytes": raw_size,
        "strippedSizeBytes": stripped,
        "dependencyCount": len(deps),
        "dependencies": deps,
    }


def markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Runtime Footprint Report")
    lines.append("")
    lines.append(f"- Generated: `{payload.get('generatedAtUtc', '')}`")
    lines.append("")
    lines.append("| Artifact | Exists | Raw Size (KiB) | Stripped Size (KiB) | Dependency Count |")
    lines.append("|---|---:|---:|---:|---:|")
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        raw = artifact.get("rawSizeBytes")
        stripped = artifact.get("strippedSizeBytes")
        raw_kib = f"{(raw / 1024.0):.2f}" if isinstance(raw, int) else ""
        stripped_kib = f"{(stripped / 1024.0):.2f}" if isinstance(stripped, int) else ""
        lines.append(
            "| "
            f"{artifact.get('label', '')} (`{artifact.get('path', '')}`) | "
            f"{artifact.get('exists', False)} | {raw_kib} | {stripped_kib} | "
            f"{artifact.get('dependencyCount', 0)} |"
        )
    lines.append("")
    builds = payload.get("buildRuns", {})
    if isinstance(builds, dict):
        lines.append("## Build wall-time runs")
        lines.append("")
        for key in ("doeBuild", "dawnBuild"):
            run = builds.get(key)
            if not isinstance(run, dict):
                continue
            lines.append(
                f"- `{key}`: exit={run.get('exitCode')}, wallMs={run.get('wallMs')}, "
                f"cmd=`{run.get('command', '')}`"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    build_cwd = Path(args.build_cwd)
    if not build_cwd.exists():
        print(f"FAIL: missing --build-cwd: {build_cwd}")
        return 1

    build_runs: dict[str, Any] = {}
    if args.doe_build_cmd.strip():
        build_runs["doeBuild"] = run_shell(args.doe_build_cmd, build_cwd)
        if build_runs["doeBuild"]["exitCode"] != 0:
            print("FAIL: doe build command failed")
            return 1
    if args.dawn_build_cmd.strip():
        build_runs["dawnBuild"] = run_shell(args.dawn_build_cmd, build_cwd)
        if build_runs["dawnBuild"]["exitCode"] != 0:
            print("FAIL: dawn build command failed")
            return 1

    doe_lib_path = Path(args.doe_lib) if args.doe_lib.strip() else resolve_default_doe_lib()
    artifacts = [
        measure_artifact("doe-bin", Path(args.doe_bin)),
        measure_artifact("dawn-bin", Path(args.dawn_bin)),
    ]
    if doe_lib_path is not None:
        artifacts.append(measure_artifact("doe-lib", doe_lib_path))

    payload = {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "buildRuns": build_runs,
        "artifacts": artifacts,
    }

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text(markdown(payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "outJson": str(out_json),
                "outMd": str(out_md),
                "artifactCount": len(artifacts),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

