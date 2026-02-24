#!/usr/bin/env python3
"""Build and run artifact-only drop-in WebGPU behavior checks."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact",
        required=True,
        help="Path to candidate drop-in shared library artifact (for linking/runtime).",
    )
    parser.add_argument(
        "--source",
        default="bench/dropin_behavior_suite.c",
        help="C source file for the black-box behavior harness.",
    )
    parser.add_argument(
        "--header-dir",
        default="bench/vendor/dawn/third_party/webgpu-headers/src",
        help="Include directory containing webgpu.h.",
    )
    parser.add_argument(
        "--cc",
        default="cc",
        help="C compiler executable.",
    )
    parser.add_argument(
        "--report",
        default="bench/out/dropin_behavior_report.json",
        help="JSON report output path.",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for output artifact path (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp the report path with a UTC timestamp suffix.",
    )
    return parser.parse_args()


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, env=env)


def parse_suite_json(stdout: str) -> dict[str, Any] | None:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    artifact_path = Path(args.artifact)
    source_path = Path(args.source)
    header_dir = Path(args.header_dir)
    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )
    report_path = output_paths.with_timestamp(
        args.report,
        output_timestamp,
        enabled=args.timestamp_output,
    )

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "outputTimestamp": output_timestamp,
        "artifact": str(artifact_path),
        "source": str(source_path),
        "headerDir": str(header_dir),
        "pass": False,
    }

    exit_code = 1
    try:
        if not artifact_path.exists():
            raise FileNotFoundError(f"missing artifact: {artifact_path}")
        if not source_path.exists():
            raise FileNotFoundError(f"missing harness source: {source_path}")
        if not header_dir.exists():
            raise FileNotFoundError(f"missing header directory: {header_dir}")

        artifact_dir = artifact_path.resolve().parent
        artifact_name = artifact_path.resolve().name

        with tempfile.TemporaryDirectory(prefix="fawn-dropin-behavior-") as tmp_dir:
            binary_path = Path(tmp_dir) / "dropin_behavior_suite"
            compile_command = [
                args.cc,
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(header_dir.resolve()),
                str(source_path.resolve()),
                "-L",
                str(artifact_dir),
                f"-Wl,-rpath,{artifact_dir}",
                f"-l:{artifact_name}",
                "-o",
                str(binary_path),
            ]
            compile_result = run_command(compile_command)
            report["compileCommand"] = compile_command
            report["compileReturnCode"] = compile_result.returncode
            report["compileStdout"] = compile_result.stdout
            report["compileStderr"] = compile_result.stderr
            if compile_result.returncode != 0:
                raise RuntimeError("behavior harness compile failed")

            run_command_list = [str(binary_path)]
            run_env = os.environ.copy()
            existing_ld = run_env.get("LD_LIBRARY_PATH", "")
            run_env["LD_LIBRARY_PATH"] = (
                f"{artifact_dir}:{existing_ld}" if existing_ld else str(artifact_dir)
            )

            run_result = run_command(run_command_list, env=run_env)
            suite_result = parse_suite_json(run_result.stdout)

            report["runCommand"] = run_command_list
            report["runReturnCode"] = run_result.returncode
            report["runStdout"] = run_result.stdout
            report["runStderr"] = run_result.stderr
            report["suiteResult"] = suite_result

            if suite_result is None:
                raise RuntimeError("behavior harness did not emit parsable suite JSON")
            suite_pass = bool(suite_result.get("pass"))
            if run_result.returncode != 0 or not suite_pass:
                raise RuntimeError("behavior suite reported compatibility failure")

            report["pass"] = True
            exit_code = 0
    except Exception as exc:  # noqa: BLE001
        report["error"] = str(exc)
        exit_code = 1
    finally:
        write_report(report_path, report)
        output_paths.write_run_manifest_for_outputs(
            [report_path],
            {
                "runType": "dropin_behavior_suite",
                "config": {
                    "artifact": str(artifact_path),
                    "source": str(source_path),
                    "headerDir": str(header_dir),
                },
                "fullRun": True,
                "claimGateRan": False,
                "dropinGateRan": False,
                "reportPath": str(report_path),
                "status": "passed" if report.get("pass") else "failed",
            },
        )

    if report.get("pass"):
        print("PASS: drop-in behavior suite")
    else:
        print(f"FAIL: drop-in behavior suite: {report.get('error', 'unknown failure')}")
    print(f"report: {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
