"""Collect sequential diagnostic controls with a frozen attribution policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qualified", type=Path, required=True, help="Retained campaign run directory"
    )
    parser.add_argument(
        "--diagnostic",
        type=Path,
        required=True,
        help="Diagnostic application directory",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="New collection directory"
    )
    parser.add_argument(
        "--callers",
        action="store_true",
        help="Use call-site sampling and omit intrusive CPU spans",
    )
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    owner = Path(__file__).resolve().parent
    policy_path = owner.parents[2] / "config/onnx-vulkan-cpu-investigation.json"
    policy = json.loads(policy_path.read_text())
    shutil.copy2(policy_path, args.out / "policy.json")
    settings = policy["diagnostic"]
    for index in range(settings["processPairs"]):
        arms = ["dawn", "doe"] if index % 2 == 0 else ["doe", "dawn"]
        treatments = [
            "original",
            "off",
            *[f"sample-{period}" for period in settings["periodsUs"]],
            "spans",
        ]
        if args.callers:
            treatments.remove("spans")
        for treatment in treatments:
            for arm in arms:
                qualification = (args.qualified / f"{arm}-matched.json").resolve()
                q = json.loads(qualification.read_text())
                application = (
                    Path(q["inputs"]["application"]["path"])
                    if treatment == "original"
                    else args.diagnostic.resolve() / "application"
                )
                period = (
                    int(treatment.split("-")[1])
                    if treatment.startswith("sample-")
                    else 0
                )
                label = f"{index}-{treatment}-{arm}"
                print("CPU diagnostic:", label, flush=True)
                command = [
                    sys.executable,
                    str(owner / "probe.py"),
                    "run",
                    "--qualification",
                    str(qualification),
                    "--application",
                    str(application),
                    "--out",
                    str(args.out / label),
                    "--period-us",
                    str(period),
                    "--runs",
                    str(settings["runsPerProcess"]),
                ]
                if treatment == "spans":
                    command.extend(["--instrument-bridge", "--spans"])
                elif args.callers and treatment.startswith("sample-"):
                    command.append("--instrument-bridge")
                subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
