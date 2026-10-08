"""Run unchanged consumer recovery and application controls against immutable libraries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def identity(path: Path) -> dict[str, str]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "native",
        "dawn",
        "bridge",
        "context",
        "provider",
        "recovery",
        "application",
        "reference",
        "python",
        "out",
    ):
        parser.add_argument(
            "--" + name, type=Path, required=True, help="Selected " + name
        )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    receipt = args.out / "consumer-qualification.json"
    if receipt.exists():
        parser.error("Retain the prior receipt; choose a new output")
    inputs = {
        name: identity(getattr(args, name))
        for name in (
            "native",
            "dawn",
            "bridge",
            "context",
            "provider",
            "recovery",
            "application",
            "reference",
        )
    }
    jobs = []

    def execute(command: list[str], name: str, expected: int = 0) -> None:
        path = args.out / (name + ".runner.log")
        if path.exists():
            raise ValueError("Refusing to overwrite " + str(path))
        before = {key: identity(Path(value["path"])) for key, value in inputs.items()}
        with path.open("w", encoding="utf-8") as log:
            child = subprocess.Popen(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT
            )
            code = child.wait()
        after = {key: identity(Path(value["path"])) for key, value in inputs.items()}
        jobs.append(
            {
                "name": name,
                "command": command,
                "pid": child.pid,
                "exitCode": code,
                "expectedExitCode": expected,
                "inputsBefore": before,
                "inputsAfter": after,
                "log": identity(path),
            }
        )
        receipt.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "performanceClaim": False,
                    "inputs": inputs,
                    "producer": identity(Path(__file__)),
                    "jobs": jobs,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if code != expected or before != after or before != inputs:
            raise ValueError("Consumer qualification failed: " + name)

    common = ROOT / "bench/external-projects/onnx-vulkan-campaign"
    for arm in ("doe", "dawn"):
        selected = args.native if arm == "doe" else args.dawn
        safety = args.out / ("safety-" + arm + ".json")
        command = [
            str(args.python),
            str(common / "safety.py"),
            "--arm",
            arm,
            "--out",
            str(safety),
        ]
        for key in ("bridge", "context", "provider", "recovery"):
            command += ["--" + key, str(getattr(args, key))]
        command += ["--native", str(selected)]
        execute(command, "safety-" + arm)
        command = [
            sys.executable,
            str(common / "run_application.py"),
            "--arm",
            arm,
            "--safety",
            str(safety),
            "--native",
            str(selected),
        ]
        for key in ("bridge", "context", "provider", "application", "reference"):
            command += ["--" + key, str(getattr(args, key))]
        execute(
            command
            + ["--out", str(args.out / ("application-" + arm + "-qualified.json"))],
            "application-" + arm,
        )
        execute(
            command
            + [
                "--disable-native",
                "--out",
                str(args.out / ("application-" + arm + "-disabled.json")),
            ],
            "disabled-" + arm,
        )
        if arm == "doe":
            altered = args.out / "altered-reference.f32"
            data = bytearray(args.reference.read_bytes())
            struct.pack_into("<f", data, 0, struct.unpack_from("<f", data)[0] + 100)
            altered.write_bytes(data)
            negative = command.copy()
            negative[negative.index("--reference") + 1] = str(altered)
            execute(
                negative
                + ["--out", str(args.out / "application-doe-oracle-negative.json")],
                "oracle-negative",
                1,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
