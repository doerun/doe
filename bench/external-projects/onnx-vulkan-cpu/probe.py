"""Build and execute a diagnostic copy of the qualified ONNX application."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct


def identity(path: Path) -> dict[str, str]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def build(source: Path, out: Path) -> None:
    """Keep original consumer sources and insert observation boundaries only."""
    out.mkdir(parents=True, exist_ok=False)
    preparation = json.loads((source / "preparation.json").read_text())
    owner = Path(__file__).resolve().parent
    snapshots = out / "sources"
    snapshots.mkdir()
    for path in [owner / "sampler.c", Path(__file__)]:
        shutil.copy2(path, snapshots / path.name)
    library = out / "libcpu_probe.so"
    subprocess.run(
        [
            "gcc",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fPIC",
            "-shared",
            str(owner / "sampler.c"),
            "-lrt",
            "-pthread",
            "-o",
            str(library),
        ],
        check=True,
    )
    header = Path(preparation["providerIntegration"]["path"]).read_text()
    if (
        hashlib.sha256(header.encode()).hexdigest()
        != preparation["providerIntegration"]["sha256"]
    ):
        raise ValueError("Qualified integration source changed")
    # Declarations precede the inline loop; boundaries exclude output verification.
    header = header.replace(
        "inline std::vector<Ort::Value> campaign_run",
        'extern "C" void doeCpuProbeBegin();\nextern "C" void doeCpuProbeEnd();\n'
        'extern "C" void doeCpuProbeMaps();\n'
        "inline std::vector<Ort::Value> campaign_run",
    )
    header = header.replace(
        "        result = session.Run(",
        "        if (iteration >= 0) doeCpuProbeBegin();\n        result = session.Run(",
    )
    header = header.replace(
        "        auto cpu_end = std::clock();",
        "        if (iteration >= 0) doeCpuProbeEnd();\n        auto cpu_end = std::clock();",
    )
    header = header.replace(
        "    struct rusage usage{};",
        "    doeCpuProbeMaps();\n    struct rusage usage{};",
    )
    (out / "application-provider.h").write_text(header)
    shutil.copy2(source / "main.cpp", out / "main.cpp")
    for name in ["squeezenet.onnx", "libonnxruntime.so.1"]:
        shutil.copy2(source / name, out / name)
    # Original command ends with rpath, -o, executable; retain rpath and add probe.
    command = preparation["command"][:]
    command = [
        (
            str(out / "main.cpp")
            if v == str(source.relative_to(Path.cwd()) / "main.cpp")
            else v
        )
        for v in command
    ]
    command = [
        (
            "-I" + str(out)
            if v.startswith("-I")
            and v.endswith("bench/external-projects/onnx-vulkan-campaign")
            else v
        )
        for v in command
    ]
    command[-1] = str(out / "application")
    command.insert(-2, str(library))
    subprocess.run(command, check=True)
    bridge_source = source.parent / "bridge-matched"
    diagnostic_bridge = out / "bridge"
    shutil.copytree(bridge_source, diagnostic_bridge)
    adapter = (diagnostic_bridge / "adapter.zig").read_text()
    adapter = adapter.replace(
        'const std = @import("std");',
        'const std = @import("std");\n'
        "extern fn doeCpuProbeEnter(index: c_uint) callconv(.c) void;\n"
        "extern fn doeCpuProbeLeave() callconv(.c) void;",
    )
    adapter = adapter.replace(
        "    _ = calls[index].fetchAdd",
        "    doeCpuProbeEnter(index);\n    defer doeCpuProbeLeave();\n"
        "    _ = calls[index].fetchAdd",
    )
    (diagnostic_bridge / "adapter.zig").write_text(adapter)
    shutil.copy2(diagnostic_bridge / "adapter.zig", snapshots / "adapter.zig")
    subprocess.run(
        [
            "zig",
            "build-lib",
            str(diagnostic_bridge / "adapter.zig"),
            "-dynamic",
            "-lc",
            "-ldl",
            "-O",
            "ReleaseSafe",
            "-I" + str(diagnostic_bridge / "generated/include"),
            "-L" + str(out),
            "-lcpu_probe",
            "-rpath",
            str(out),
            "-femit-bin=" + str(diagnostic_bridge / "libdoe_dawn_bridge.so"),
        ],
        check=True,
    )
    receipt = {
        "schemaVersion": 1,
        "classification": "diagnostic-cpu-build",
        "preparation": identity(source / "preparation.json"),
        "command": command,
        "application": identity(out / "application"),
        "sampler": identity(library),
        "bridge": identity(diagnostic_bridge / "libdoe_dawn_bridge.so"),
        "sources": [
            identity(out / "main.cpp"),
            identity(out / "application-provider.h"),
            identity(owner / "sampler.c"),
            identity(Path(__file__)),
        ],
    }
    (out / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")


def run(
    qualification: Path,
    application: Path,
    out: Path,
    period: int,
    runs: int,
    instrument_bridge: bool,
    spans: bool,
    negative: str | None,
) -> None:
    """Collect main-thread PCs with independent complete-process CPU controls."""
    out.mkdir(parents=True, exist_ok=False)
    q = json.loads(qualification.read_text())
    policy = json.loads(Path(q["policy"]["path"]).read_text())
    attribution_policy = (
        Path(__file__).resolve().parents[3]
        / "config/onnx-vulkan-cpu-investigation.json"
    )
    attribution = json.loads(attribution_policy.read_text())
    if not q["passed"] or q["negativeControl"]:
        raise ValueError("Application qualification failed")
    for item in q["inputs"].values():
        if identity(Path(item["path"])) != item:
            raise ValueError("Qualified input changed")
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CAMPAIGN_", "DOE_CPU_"))
        and k not in ["LD_PRELOAD", "LD_LIBRARY_PATH", "DOE_WEBGPU_LIB"]
    }
    cache = out / "cache"
    cache.mkdir()
    home = cache / "home"
    home.mkdir()
    environment.update(
        {
            "HOME": str(home),
            "XDG_CACHE_HOME": str(cache),
            "MESA_SHADER_CACHE_DIR": str(cache),
            "CAMPAIGN_ARM": q["arm"],
            "CAMPAIGN_MODE": "timing",
            "CAMPAIGN_WARMUP": str(attribution["diagnostic"]["warmupRuns"]),
            "CAMPAIGN_RUNS": str(runs),
            "CAMPAIGN_PROFILE": str(out / "profile"),
            "CAMPAIGN_OBSERVATIONS": str(out / "observations"),
            "CAMPAIGN_ATOL": str(policy["correctness"]["absoluteTolerance"]),
            "CAMPAIGN_RTOL": str(policy["correctness"]["relativeTolerance"]),
            "DOE_CPU_SAMPLES": str(out / "samples.bin"),
            "DOE_CPU_MAPS": str(out / "maps"),
            "DOE_CPU_PERIOD_US": str(period),
        }
    )
    for name in ["provider", "native", "bridge", "context", "reference"]:
        environment["CAMPAIGN_" + name.upper()] = q["inputs"][name]["path"]
    if instrument_bridge:
        environment["CAMPAIGN_BRIDGE"] = str(
            application.parent / "bridge/libdoe_dawn_bridge.so"
        )
    if spans:
        environment["DOE_CPU_SPANS"] = "1"
    if negative == "native":
        environment["CAMPAIGN_NATIVE"] = "/missing/selected-native-library.so"
    elif negative == "oracle":
        oracle = out / "corrupted-reference.f32"
        source = Path(environment["CAMPAIGN_REFERENCE"]).read_bytes()
        oracle.write_bytes(struct.pack("<f", 1.0) + source[4:])
        environment["CAMPAIGN_REFERENCE"] = str(oracle)
    with (out / "application.log").open("w") as stream:
        completed = subprocess.run(
            [str(application)],
            cwd=application.parent,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    receipt = {
        "schemaVersion": 1,
        "classification": "diagnostic-cpu-run",
        "qualification": identity(qualification),
        "application": identity(application),
        "policy": identity(attribution_policy),
        "bridge": identity(Path(environment["CAMPAIGN_BRIDGE"])),
        "environment": {
            k: v
            for k, v in environment.items()
            if k.startswith(("CAMPAIGN_", "DOE_CPU_"))
            or k in ["HOME", "XDG_CACHE_HOME", "MESA_SHADER_CACHE_DIR"]
        },
        "exitCode": completed.returncode,
        "periodUs": period,
        "runs": runs,
        "negativeControl": negative,
        "sampleRecordBytes": 128,
        "log": identity(out / "application.log"),
        "observations": (
            identity(out / "observations") if (out / "observations").exists() else None
        ),
        "samples": (
            identity(out / "samples.bin") if (out / "samples.bin").exists() else None
        ),
        "maps": identity(out / "maps") if (out / "maps").exists() else None,
    }
    (out / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    content = (out / "application.log").read_text()
    if negative:
        expected = (
            "Proc-table initialization failed"
            if negative == "native"
            else "Independent oracle mismatch"
        )
        if (
            not completed.returncode
            or expected not in content
            or "CampaignCleanupFailure" in content
        ):
            raise ValueError("Negative control failed at the wrong boundary")
    elif completed.returncode or "CampaignCleanupFailure" in content:
        raise ValueError("Diagnostic application failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("--source", type=Path, required=True)
    builder.add_argument("--out", type=Path, required=True)
    runner = commands.add_parser("run")
    runner.add_argument("--qualification", type=Path, required=True)
    runner.add_argument("--application", type=Path, required=True)
    runner.add_argument("--out", type=Path, required=True)
    runner.add_argument("--period-us", type=int, required=True)
    runner.add_argument("--runs", type=int, required=True)
    runner.add_argument("--instrument-bridge", action="store_true")
    runner.add_argument("--spans", action="store_true")
    runner.add_argument(
        "--negative",
        choices=["native", "oracle"],
        help="Expected failure at a named boundary",
    )
    args = parser.parse_args()
    if args.command == "build":
        build(args.source.resolve(), args.out.resolve())
    else:
        run(
            args.qualification.resolve(),
            args.application.resolve(),
            args.out.resolve(),
            args.period_us,
            args.runs,
            args.instrument_bridge,
            args.spans,
            args.negative,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
