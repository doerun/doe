"""Wait for observed GPU inactivity, then run one unchanged calibration."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from bench.lib.compute_program_gpu_activity import (
    detect_target, read_boot_id, read_snapshot, reject_activity,
)
from bench.lib.compute_program_retention import write_json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREVIOUS = HERE.parent / "20260920-command-storage-calibration-window"
OUTPUT = HERE.parent / "20260920-command-storage-calibration-window-03"
POLICY = HERE.parent / "20260912-warmup-calibration-v1/procedure/calibration.json"
POLL_SECONDS = 30
QUIET_SECONDS = 180


def verify_inputs() -> None:
    report = json.loads((PREVIOUS / "report.json").read_text(encoding="utf-8"))
    references = [report["policy"], report["frozenInputs"], *report["packages"]]
    references.extend(json.loads(
        Path(report["frozenInputs"]["path"]).read_text(encoding="utf-8")))
    for reference in references:
        with Path(reference["path"]).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != reference["hash"]:
            raise ValueError(f"Frozen input changed: {reference['path']}")
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if shutil.disk_usage(ROOT).free < policy["minimumFreeBytes"]:
        raise ValueError("Insufficient free disk space for frozen procedure")
    for name in ("LD_PRELOAD", "NODE_OPTIONS", "NODE_PATH"):
        if os.environ.get(name):
            raise ValueError(f"Unexpected execution override: {name}")


def main() -> int:
    """Launch once; observed quiet is not an exclusive GPU reservation."""
    verify_inputs()
    target = detect_target()
    boot_id = read_boot_id()
    write_json(HERE / "launch-guard.json", {
        "pollSeconds": POLL_SECONDS, "quietSeconds": QUIET_SECONDS,
        "purpose": "launch scheduling only; frozen evaluator unchanged",
        "exclusiveGpuAccessEstablished": False,
        "bootId": boot_id, "target": target,
    })
    before = read_snapshot(target)
    quiet_start = before["monotonicNs"]
    index = 0
    while True:
        time.sleep(POLL_SECONDS)
        after = read_snapshot(target)
        if read_boot_id() != boot_id:
            raise ValueError("Host boot changed while waiting")
        rejection = None
        try:
            reject_activity([before, after], target["pciDevice"])
        except ValueError as exc:
            rejection = str(exc)
            quiet_start = after["monotonicNs"]
        quiet = (after["monotonicNs"] - quiet_start) / 1e9
        write_json(HERE / f"watch-{index:04d}.json", {
            "snapshots": [before, after], "rejection": rejection,
            "quietSeconds": quiet, "bootId": boot_id, "target": target,
        })
        print(json.dumps({"observation": index, "quietSeconds": quiet,
                          "rejection": rejection}), flush=True)
        index += 1
        if quiet >= QUIET_SECONDS:
            break
        before = after
    verify_inputs()
    command = [sys.executable, "-m", "bench.runners.run_compute_program_calibration",
               "--policy", str(POLICY), "--output", str(OUTPUT)]
    write_json(HERE / "command.json", command)
    (HERE / "execution-commit.txt").write_text(subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True), encoding="utf-8")
    (HERE / "launch-working-tree.txt").write_text(subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True), encoding="utf-8")
    started = time.monotonic_ns()
    print("Quiet launch guard passed; starting complete calibration", flush=True)
    with (HERE / "execution.log").open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    write_json(HERE / "execution-result.json", {
        "command": command, "exitCode": result.returncode,
        "startedMonotonicNs": started,
        "completedMonotonicNs": time.monotonic_ns(),
    })
    print(f"Calibration finished: exit {result.returncode}", flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
