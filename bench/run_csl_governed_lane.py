#!/usr/bin/env python3
"""Governed non-hardware CSL compile/run/parity lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

import output_paths

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ZIG_ROOT = REPO_ROOT / "runtime" / "zig"
LANE_SCHEMA = REPO_ROOT / "config" / "csl-governed-lane-report.schema.json"
HOST_PLAN_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-host-plan.schema.json"
SIM_PLAN_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-simulator-plan.schema.json"
SIM_RESULT_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-simulator-result.schema.json"
DRIVER_RESULT_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-simulator-driver-result.schema.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-id",
        default="gemma-3-270m-manifest-smoke",
    )
    parser.add_argument(
        "--input-json",
        default="runtime/zig/examples/execution-v1/gemma-3-270m-manifest-smoke.json",
    )
    parser.add_argument(
        "--expected-host-plan",
        default="runtime/zig/examples/doe-wgsl-host-plan.gemma-3-270m-manifest-smoke.json",
    )
    parser.add_argument(
        "--host-plan-tool",
        default="runtime/zig/zig-out/bin/doe-csl-host-plan-tool",
    )
    parser.add_argument(
        "--sim-runner",
        default="runtime/zig/zig-out/bin/doe-csl-sim-runner",
    )
    parser.add_argument(
        "--simulator-plan-template",
        default="runtime/zig/examples/simulator/gemma-3-270m-manifest-smoke/simulator-plan.template.json",
    )
    parser.add_argument(
        "--driver-executable",
        default="",
    )
    parser.add_argument(
        "--cslc-executable",
        default="",
    )
    parser.add_argument(
        "--runtime-executable",
        default="",
    )
    parser.add_argument(
        "--out-json",
        default="bench/out/csl-governed-lane.report.json",
    )
    parser.add_argument(
        "--out-md",
        default="bench/out/csl-governed-lane.report.md",
    )
    parser.add_argument("--timestamp", default="")
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def validate_against(path: Path, schema_path: Path) -> dict[str, Any]:
    payload = load_json(path)
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator(schema).validate(payload)
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# CSL governed lane",
        "",
        f"- Fixture: `{report['fixture']['id']}`",
        f"- Lane status: `{report['laneStatus']}`",
        f"- Compile status: `{report['compile']['status']}`",
        f"- Run status: `{report['run']['status']}`",
        f"- Parity status: `{report['parity']['status']}`",
        f"- Generated at: `{report['generatedAt']}`",
        "",
        "## Artifacts",
        f"- Host plan: `{report['artifacts']['actualHostPlanPath']}`",
        f"- Expected host plan: `{report['artifacts']['expectedHostPlanPath']}`",
        f"- Simulator plan: `{report['artifacts']['simulatorPlanPath']}`",
        f"- Simulator result: `{report['artifacts']['simulatorResultPath']}`",
        f"- Driver result: `{report['artifacts']['driverResultPath']}`",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_command(
    label: str,
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    print(f"[csl-lane] {label}: {' '.join(command)}", flush=True)
    proc = subprocess.run(command, check=False, cwd=str(cwd) if cwd else None, env=env)
    return {
        "label": label,
        "command": command,
        "exitCode": proc.returncode,
    }


def materialize_plan(
    *,
    template_path: Path,
    host_plan_path: Path,
    run_dir: Path,
) -> Path:
    template = validate_against(template_path, SIM_PLAN_SCHEMA)
    template_dir = template_path.parent

    compile_src = (template_dir / "compile").resolve()
    compile_dst = (run_dir / "compile").resolve()
    if compile_dst.exists():
        shutil.rmtree(compile_dst)
    shutil.copytree(compile_src, compile_dst)

    runtime_cfg_src = (template_dir / "runtime-config.json").resolve()
    runtime_cfg_dst = (run_dir / "runtime-config.json").resolve()
    shutil.copy2(runtime_cfg_src, runtime_cfg_dst)

    template["inputs"]["hostPlanArtifactPath"] = str(host_plan_path.resolve())
    template["inputs"]["runtimeConfigPath"] = str(runtime_cfg_dst.resolve())
    template["inputs"]["compileRootPath"] = str(compile_dst.resolve())
    template["outputs"]["stdoutPath"] = str((run_dir / "sim.stdout.log").resolve())
    template["outputs"]["stderrPath"] = str((run_dir / "sim.stderr.log").resolve())
    template["outputs"]["tracePath"] = str((run_dir / "sim.trace.json").resolve())

    materialized = (run_dir / "simulator-plan.json").resolve()
    write_json(materialized, template)
    validate_against(materialized, SIM_PLAN_SCHEMA)
    return materialized


def main() -> int:
    args = parse_args()
    output_timestamp = output_paths.resolve_timestamp(args.timestamp) if args.timestamp_output else ""
    out_json = output_paths.with_timestamp(
        resolve_repo_path(args.out_json),
        output_timestamp,
        enabled=args.timestamp_output,
        layout="folder",
        group="csl-governed",
    ).resolve()
    out_md = output_paths.with_timestamp(
        resolve_repo_path(args.out_md),
        output_timestamp,
        enabled=args.timestamp_output,
        layout="folder",
        group="csl-governed",
    ).resolve()
    run_dir = out_json.parent
    run_dir.mkdir(parents=True, exist_ok=True)

    fixture_input = resolve_repo_path(args.input_json)
    expected_host_plan = resolve_repo_path(args.expected_host_plan)
    host_plan_tool = resolve_repo_path(args.host_plan_tool)
    sim_runner = resolve_repo_path(args.sim_runner)
    simulator_plan_template = resolve_repo_path(args.simulator_plan_template)
    actual_host_plan = (run_dir / "host-plan.actual.json").resolve()

    lowering_step = run_command(
        "host-plan",
        [
            str(host_plan_tool),
            "--input",
            str(fixture_input),
            "--output",
            str(actual_host_plan),
            "--mode",
            "manifest",
        ],
        cwd=RUNTIME_ZIG_ROOT,
    )

    parity_status = "not-run"
    parity_reason = "lowering_failed"
    actual_hash = ""
    expected_hash = ""
    if lowering_step["exitCode"] == 0 and actual_host_plan.exists():
        validate_against(actual_host_plan, HOST_PLAN_SCHEMA)
        validate_against(expected_host_plan, HOST_PLAN_SCHEMA)
        actual_hash = sha256_file(actual_host_plan)
        expected_hash = sha256_file(expected_host_plan)
        if actual_hash == expected_hash:
            parity_status = "matched"
            parity_reason = "host_plan_hash_match"
        else:
            parity_status = "mismatched"
            parity_reason = "host_plan_hash_mismatch"

    sim_plan_path = materialize_plan(
        template_path=simulator_plan_template,
        host_plan_path=actual_host_plan if actual_host_plan.exists() else expected_host_plan,
        run_dir=run_dir,
    )

    env = dict(os.environ)
    if args.driver_executable.strip():
        env["DOE_CSL_SIM_EXECUTABLE"] = str(resolve_repo_path(args.driver_executable))
    if args.cslc_executable.strip():
        env["DOE_CSLC_EXECUTABLE"] = str(resolve_repo_path(args.cslc_executable))
    if args.runtime_executable.strip():
        env["DOE_CSL_RUNTIME_EXECUTABLE"] = str(resolve_repo_path(args.runtime_executable))

    sim_step = run_command(
        "sim-runner",
        [
            str(sim_runner),
            "--plan",
            str(sim_plan_path),
        ],
        cwd=REPO_ROOT,
        env=env,
    )

    trace_path = Path(load_json(sim_plan_path)["outputs"]["tracePath"])
    sim_result_path = Path(f"{trace_path}.result.json")
    driver_result_path = Path(f"{trace_path}.driver-result.json")

    sim_result: dict[str, Any] = {}
    driver_result: dict[str, Any] = {}
    if sim_result_path.exists():
        sim_result = validate_against(sim_result_path, SIM_RESULT_SCHEMA)
    if driver_result_path.exists():
        driver_result = validate_against(driver_result_path, DRIVER_RESULT_SCHEMA)

    compile_status = "not-produced"
    compile_reason = "driver_result_missing"
    if driver_result:
        compile_status = str(driver_result["compile"]["status"])
        compile_reason = str(driver_result["compile"]["reason"])

    run_status = "not-produced"
    run_reason = "driver_result_missing"
    trace_produced = False
    if driver_result:
        run_status = str(driver_result["run"]["status"])
        run_reason = str(driver_result["run"]["reason"])
        trace_produced = bool(driver_result["run"]["traceProduced"])

    lane_status = "blocked"
    if parity_status == "mismatched" or compile_status == "failed" or run_status == "failed":
        lane_status = "failed"
    elif parity_status == "matched" and compile_status == "succeeded" and run_status == "succeeded":
        lane_status = "ready"

    report = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "outputTimestamp": output_timestamp,
        "fixture": {
            "id": args.fixture_id,
            "inputJsonPath": str(fixture_input),
        },
        "laneStatus": lane_status,
        "compile": {
            "status": compile_status,
            "reason": compile_reason,
            "runnerExitCode": sim_step["exitCode"],
        },
        "run": {
            "status": run_status,
            "reason": run_reason,
            "traceProduced": trace_produced,
        },
        "parity": {
            "status": parity_status,
            "reason": parity_reason,
            "expectedHostPlanSha256": expected_hash,
            "actualHostPlanSha256": actual_hash,
        },
        "artifacts": {
            "actualHostPlanPath": str(actual_host_plan),
            "expectedHostPlanPath": str(expected_host_plan),
            "simulatorPlanPath": str(sim_plan_path),
            "simulatorResultPath": str(sim_result_path) if sim_result_path.exists() else "",
            "driverResultPath": str(driver_result_path) if driver_result_path.exists() else "",
        },
        "steps": {
            "hostPlanLowering": lowering_step,
            "simRunner": sim_step,
        },
        "simulationResult": sim_result,
        "driverResult": driver_result,
        "comparisonStatus": "diagnostic",
        "claimStatus": "not-evaluated",
    }

    jsonschema.Draft202012Validator(load_json(LANE_SCHEMA)).validate(report)
    write_json(out_json, report)
    write_markdown(out_md, report)
    output_paths.write_run_manifest_for_outputs(
        [out_json, out_md],
        {
            "runType": "csl-governed-lane",
            "status": "ready" if lane_status == "ready" else "diagnostic",
            "reportPath": str(out_json),
            "comparisonStatus": report["comparisonStatus"],
            "claimStatus": report["claimStatus"],
            "fixtureId": args.fixture_id,
        },
    )

    if lane_status == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
