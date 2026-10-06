"""Add the pinned Dawn native table to the existing Release ONNX source build."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.consumer_root = args.consumer_root.resolve()
    args.out = args.out.resolve()
    if args.out.exists():
        parser.error("Output must be new")
    args.out.mkdir(parents=True)
    policy_path = (
        Path(__file__).resolve().parents[3] / "config/onnx-vulkan-campaign.json"
    )
    policy = json.loads(policy_path.read_text())
    source = (
        args.consumer_root
        / ("onnxruntime-" + policy["consumer"]["onnxCommit"])
        / "cmake"
    )
    build = args.consumer_root / "build"
    cache = (build / "CMakeCache.txt").read_text()
    for setting in [
        "CMAKE_BUILD_TYPE:STRING=Release",
        "DAWN_ENABLE_VULKAN:BOOL=ON",
        "onnxruntime_USE_EXTERNAL_DAWN:BOOL=ON",
    ]:
        if setting not in cache:
            raise ValueError("Unmatched consumer setting: " + setting)
    control = args.out / "dawn-control.cc"
    control.write_text(
        '#include "dawn/native/DawnNative.h"\n'
        'extern "C" __attribute__((visibility("default"))) const DawnProcTable* doeDawnControlGetProcs() {\n'
        " return &dawn::native::GetProcs();\n}\n"
    )
    hook = args.out / "control-target.cmake"
    hook.write_text(
        "function(add_doe_source_matched_control)\n"
        f' add_library(doe_dawn_control SHARED "{control}")\n'
        " target_link_libraries(doe_dawn_control PRIVATE dawn::dawn_native)\n"
        f' set_target_properties(doe_dawn_control PROPERTIES LIBRARY_OUTPUT_DIRECTORY "{args.out}")\n'
        "endfunction()\ncmake_language(DEFER CALL add_doe_source_matched_control)\n"
    )
    commands = [
        [
            "cmake",
            "-S",
            str(source),
            "-B",
            str(build),
            "-DCMAKE_PROJECT_onnxruntime_INCLUDE=" + str(hook),
        ],
        ["cmake", "--build", str(build), "--target", "doe_dawn_control", "-j4"],
    ]
    for index, command in enumerate(commands):
        with (args.out / f"build-{index}.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    identity = lambda p: {
        "path": str(p.resolve()),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    receipt = {
        "schemaVersion": 1,
        "policy": identity(policy_path),
        "builder": identity(Path(__file__)),
        "commands": commands,
        "controlSource": identity(control),
        "cmakeHook": identity(hook),
        "cmakeCache": identity(build / "CMakeCache.txt"),
        "library": identity(args.out / "libdoe_dawn_control.so"),
    }
    (args.out / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
