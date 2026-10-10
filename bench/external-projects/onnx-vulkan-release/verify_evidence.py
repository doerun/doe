"""Recompute installed acceptance from retained raw logs and exact package bytes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.dont_write_bytecode = True

from distribution import digest, inventory, verify
from qualification import application_evidence, loaded_libraries


def verify_results(root: Path, out: Path) -> dict[str, Any]:
    """Reject omitted controls, missing native work, and changed result artifacts."""
    root = root.resolve()
    manifest = verify(root)
    result = json.loads((out / "qualification.json").read_text("utf-8"))
    if result["manifestSha256"] != digest(root / "manifest.json"):
        raise ValueError("Qualification belongs to a different installation")
    if result["version"] != manifest["version"] or result["mode"] != "qualify":
        raise ValueError("Complete qualification of the installed version required")
    expected = ["initialization", "callbacks", "lifecycle"]
    expected += [
        f"application-{i}"
        for i in range(manifest["qualification"]["applicationProcesses"])
    ]
    expected += ["native-disabled", "oracle-corrupted"]
    if [row["name"] for row in result["jobs"]] != expected:
        raise ValueError("Missing, reordered, or additional acceptance jobs")
    if not result["passed"] or result["performanceClaim"] or result["externalAdoption"]:
        raise ValueError("Invalid evaluation verdict or strengthened claim")
    for row in result["jobs"]:
        if not row["passed"] or row["failure"]:
            raise ValueError("Failed acceptance job: " + row["name"])
        job = out / row["name"]
        if row["artifacts"] != inventory(job):
            raise ValueError("Changed raw job artifacts: " + row["name"])
        output = (job / "stdout.log").read_text("utf-8")
        content = output + (job / "stderr.log").read_text("utf-8")
        if "CampaignCleanupFailure " in content:
            raise ValueError("Cleanup failure cannot pass")
        if row["name"].startswith("application-"):
            if row["exitCode"] != 0 or row["execution"] != application_evidence(
                root, job, content, manifest
            ):
                raise ValueError("Application execution evidence mismatch")
        elif row["name"] in ("native-disabled", "oracle-corrupted"):
            reason = (
                "Proc-table initialization failed"
                if row["name"] == "native-disabled"
                else "Independent oracle mismatch"
            )
            if row["exitCode"] == 0 or reason not in content:
                raise ValueError(
                    "Negative control did not fail at the intended boundary"
                )
        else:
            checks = [
                json.loads(line) for line in output.splitlines() if line.startswith("{")
            ]
            if (
                row["exitCode"] != 0
                or not checks
                or any(item.get("passed") is False for item in checks)
            ):
                raise ValueError("Failed initialization or lifecycle observation")
            if row["name"] == "initialization":
                required = {
                    "missing-library-rejected",
                    "incomplete-library-rejected",
                    "retry-succeeds",
                    "live-rebind-rejected",
                    "rebind-diagnostic",
                }
                if set(checks[0]["checks"]) != required or not all(
                    checks[0]["checks"].values()
                ):
                    raise ValueError("Incomplete initialization/retry coverage")
            elif checks[-1].get("failures") != 0:
                raise ValueError("Lifecycle fixture failed")
            execution = {
                "checks": checks,
                "loadedLibraries": loaded_libraries(content, root),
            }
            if row["execution"] != execution:
                raise ValueError("Fixture execution evidence mismatch")
    return {
        "passed": True,
        "version": manifest["version"],
        "manifestSha256": result["manifestSha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--installation", required=True, type=Path, help="Retained installed package"
    )
    parser.add_argument(
        "--results", required=True, type=Path, help="Retained complete qualification"
    )
    args = parser.parse_args()
    print(json.dumps(verify_results(args.installation, args.results), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
