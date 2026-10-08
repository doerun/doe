"""Retain independent callback controls with exact source, binary, and log custody."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def identity(path: Path) -> dict:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["native", "before", "dawn", "bridge", "headers", "out"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output must be new")
    args.out.mkdir(parents=True)
    policy_path = ROOT / "config/native-callback-contract.json"
    policy = json.loads(policy_path.read_text())
    source = Path(__file__).with_name("callbacks.cpp")
    executable = args.out / "callbacks"
    command = [
        "c++",
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pthread",
        "-I" + str(args.headers.resolve()),
        str(source.resolve()),
        "-ldl",
        "-o",
        str(executable.resolve()),
    ]
    with (args.out / "build.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    result = {
        "schemaVersion": 1,
        "classification": "bounded-native-vulkan-callback-qualification",
        "performanceClaim": False,
        "policy": identity(policy_path),
        "fixture": identity(source),
        "producer": identity(Path(__file__)),
        "buildCommand": command,
        "executable": identity(executable),
        "inputs": {
            n: identity(getattr(args, n))
            for n in ["native", "before", "dawn", "bridge"]
        },
        "headers": {
            n: identity(args.headers / "dawn" / n)
            for n in ["webgpu.h", "dawn_proc_table.h"]
        },
        "runs": [],
    }
    # Sequential independent processes preserve each implementation's normal synchronization.
    for arm in ["before", "dawn", "native"]:
        for index in range(policy["independentProcesses"]):
            stem = args.out / f"{arm}-{index:02d}"
            stdout = stem.with_suffix(".jsonl")
            stderr = stem.with_suffix(".stderr")
            command = [
                str(executable.resolve()),
                str(args.bridge.resolve()),
                str(getattr(args, arm).resolve()),
                "dawn" if arm == "dawn" else "doe",
                str(policy["qualificationDeadlineNs"]),
            ]
            input_before = identity(getattr(args, arm))
            with stdout.open("w") as output, stderr.open("w") as error:
                run = subprocess.run(
                    command,
                    stdout=output,
                    stderr=error,
                    timeout=policy["qualificationDeadlineNs"] / 1e9 * 10,
                )
            rows = [json.loads(line) for line in stdout.read_text().splitlines()]
            expected = 1 if arm == "before" else 0
            result["runs"].append(
                {
                    "arm": arm,
                    "nativeBefore": input_before,
                    "nativeAfter": identity(getattr(args, arm)),
                    "index": index,
                    "command": command,
                    "exitCode": run.returncode,
                    "expectedExitCode": expected,
                    "stdout": identity(stdout),
                    "stderr": identity(stderr),
                    "failedObservations": sum(
                        row.get("passed") is False
                        for row in rows
                        if row["kind"] in ["callback", "check"]
                    ),
                    "summary": rows[-1],
                }
            )
            # Write progress even if a positive arm fails; never discard unfavorable output.
            (args.out / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return int(
        any(
            r["exitCode"] != r["expectedExitCode"]
            or r["nativeBefore"] != r["nativeAfter"]
            or r["nativeBefore"] != result["inputs"][r["arm"]]
            for r in result["runs"]
        )
    )


if __name__ == "__main__":
    sys.exit(main())
