#!/usr/bin/env python3
"""External CSL simulator driver that consumes DOE simulator-plan artifacts.

This driver is the concrete executable behind the DOE_CSL_SIM_EXECUTABLE
contract. It accepts the simulator-plan path as argv[1], validates the plan,
attempts CSL compilation when cslc is available, and optionally launches a
runtime command described by runtimeConfigPath.

It does not fabricate trace output. Blocked compile/run states are recorded
explicitly in a driver-result artifact next to the declared trace path.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[3]
SIM_PLAN_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-simulator-plan.schema.json"
DRIVER_RESULT_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-simulator-driver-result.schema.json"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def validate_schema(path: Path, schema_path: Path) -> dict[str, Any]:
    payload = load_json(path)
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator(schema).validate(payload)
    return payload


def resolve_relative(base: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def read_runtime_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing runtime config: {path}")
    return load_json(path)


def derive_driver_result_path(trace_path: Path) -> Path:
    return trace_path.with_name(f"{trace_path.name}.driver-result.json")


def env_or_which(explicit: str | None, env_var: str, default: str) -> str | None:
    if explicit:
        return explicit
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return env_value
    resolved = shutil.which(default)
    return resolved


def run_command(command: list[str], stdout_path: Path, stderr_path: Path) -> tuple[int, str, str]:
    ensure_parent(stdout_path)
    ensure_parent(stderr_path)
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    return proc.returncode, str(stdout_path), str(stderr_path)


def materialize_command(template: list[str], substitutions: dict[str, str]) -> list[str]:
    command: list[str] = []
    for item in template:
        rendered = item
        for key, value in substitutions.items():
            rendered = rendered.replace("{" + key + "}", value)
        command.append(rendered)
    return command


def compile_targets(
    *,
    plan_path: Path,
    plan: dict[str, Any],
    cslc_executable: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Path]]:
    plan_dir = plan_path.parent
    inputs = plan["inputs"]
    runtime = plan["runtime"]
    compile_root = resolve_relative(plan_dir, str(inputs["compileRootPath"]))
    compile_root.mkdir(parents=True, exist_ok=True)
    logs_dir = compile_root / "driver-logs"
    outputs_dir = compile_root / "compiled"
    logs_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    width = int(runtime["peGrid"]["width"])
    height = int(runtime["peGrid"]["height"])
    arch = str(plan.get("target", "wse3"))
    target_results: list[dict[str, Any]] = []

    if not cslc_executable:
        for target in inputs["compileTargets"]:
            target_results.append(
                {
                    "name": target["name"],
                    "layoutPath": str(resolve_relative(compile_root, target["layout"])),
                    "peProgramPath": str(resolve_relative(compile_root, target["peProgram"])),
                    "outputDir": str((outputs_dir / target["name"]).resolve()),
                    "status": "blocked",
                    "reason": "compiler_unavailable",
                }
            )
        return (
            {
                "attempted": False,
                "status": "blocked",
                "reason": "compiler_unavailable",
                "compilerExecutable": None,
            },
            target_results,
            {"compileRoot": compile_root, "logsDir": logs_dir, "outputsDir": outputs_dir},
        )

    overall_failed = False
    for target in inputs["compileTargets"]:
        name = str(target["name"])
        layout_path = resolve_relative(compile_root, str(target["layout"]))
        pe_program_path = resolve_relative(compile_root, str(target["peProgram"]))
        output_dir = (outputs_dir / name).resolve()
        stdout_path = logs_dir / f"{name}.cslc.stdout.log"
        stderr_path = logs_dir / f"{name}.cslc.stderr.log"
        if not layout_path.exists() or not pe_program_path.exists():
            overall_failed = True
            target_results.append(
                {
                    "name": name,
                    "layoutPath": str(layout_path),
                    "peProgramPath": str(pe_program_path),
                    "outputDir": str(output_dir),
                    "status": "failed",
                    "reason": "missing_compile_inputs",
                }
            )
            continue
        command = [
            cslc_executable,
            str(layout_path),
            f"--arch={arch}",
            f"--fabric-dims={width},{height}",
            "-o",
            str(output_dir),
        ]
        return_code, stdout_written, stderr_written = run_command(command, stdout_path, stderr_path)
        status = "succeeded" if return_code == 0 else "failed"
        if return_code != 0:
            overall_failed = True
        target_results.append(
            {
                "name": name,
                "layoutPath": str(layout_path),
                "peProgramPath": str(pe_program_path),
                "outputDir": str(output_dir),
                "status": status,
                "exitCode": return_code,
                "stdoutPath": stdout_written,
                "stderrPath": stderr_written,
                "command": command,
            }
        )

    summary = {
        "attempted": True,
        "status": "failed" if overall_failed else "succeeded",
        "reason": "compile_failed" if overall_failed else "compiled",
        "compilerExecutable": cslc_executable,
    }
    return summary, target_results, {"compileRoot": compile_root, "logsDir": logs_dir, "outputsDir": outputs_dir}


def run_simulation(
    *,
    plan_path: Path,
    plan: dict[str, Any],
    runtime_config_path: Path,
    compile_summary: dict[str, Any],
    compile_targets_payload: list[dict[str, Any]],
    working_paths: dict[str, Path],
    explicit_sim_runner: str | None,
) -> dict[str, Any]:
    plan_dir = plan_path.parent
    outputs = plan["outputs"]
    trace_path = resolve_relative(plan_dir, str(outputs["tracePath"]))
    stdout_path = resolve_relative(plan_dir, str(outputs["stdoutPath"]))
    stderr_path = resolve_relative(plan_dir, str(outputs["stderrPath"]))

    if compile_summary["status"] != "succeeded":
        return {
            "attempted": False,
            "status": "blocked",
            "reason": "compile_not_ready",
            "tracePath": str(trace_path),
            "traceProduced": False,
            "stdoutPath": str(stdout_path),
            "stderrPath": str(stderr_path),
        }

    runtime_config = read_runtime_config(runtime_config_path)
    mode = str(runtime_config.get("mode", ""))
    if mode == "compile-only":
        return {
            "attempted": False,
            "status": "blocked",
            "reason": "compile_only_fixture",
            "tracePath": str(trace_path),
            "traceProduced": trace_path.exists(),
            "stdoutPath": str(stdout_path),
            "stderrPath": str(stderr_path),
        }

    raw_command = runtime_config.get("command")
    if not isinstance(raw_command, list) or not all(isinstance(item, str) for item in raw_command):
        return {
            "attempted": False,
            "status": "blocked",
            "reason": "missing_runtime_command",
            "tracePath": str(trace_path),
            "traceProduced": trace_path.exists(),
            "stdoutPath": str(stdout_path),
            "stderrPath": str(stderr_path),
        }

    if explicit_sim_runner:
        raw_command = [explicit_sim_runner, *[str(item) for item in raw_command]]

    first_output_dir = ""
    for target in compile_targets_payload:
        if target.get("status") == "succeeded":
            first_output_dir = str(target.get("outputDir", ""))
            break
    substitutions = {
        "plan_path": str(plan_path.resolve()),
        "plan_dir": str(plan_dir.resolve()),
        "compile_root": str(working_paths["compileRoot"].resolve()),
        "compile_output_dir": first_output_dir,
        "trace_path": str(trace_path.resolve()),
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
    }
    command = materialize_command([str(item) for item in raw_command], substitutions)
    return_code, stdout_written, stderr_written = run_command(command, stdout_path, stderr_path)
    return {
        "attempted": True,
        "status": "succeeded" if return_code == 0 and trace_path.exists() else "failed",
        "reason": "ran" if return_code == 0 and trace_path.exists() else "runtime_failed",
        "command": command,
        "exitCode": return_code,
        "tracePath": str(trace_path),
        "traceProduced": trace_path.exists(),
        "stdoutPath": stdout_written,
        "stderrPath": stderr_written,
    }


def build_driver_result(
    *,
    plan_path: Path,
    cslc_executable: str | None,
    runtime_config_path: Path,
    compile_summary: dict[str, Any],
    compile_targets_payload: list[dict[str, Any]],
    run_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_driver_result",
        "target": "wse3",
        "contract": "explicit_driver_outcome",
        "simulatorPlanPath": str(plan_path.resolve()),
        "compilerExecutable": cslc_executable,
        "runtimeConfigPath": str(runtime_config_path.resolve()),
        "compile": {
            "attempted": compile_summary["attempted"],
            "status": compile_summary["status"],
            "reason": compile_summary["reason"],
            "targets": compile_targets_payload,
        },
        "run": run_summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--cslc-executable", default="")
    parser.add_argument("--sim-runner-executable", default="")
    parser.add_argument("--runtime-executable", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan_path = Path(args.plan).resolve()
    try:
        plan = validate_schema(plan_path, SIM_PLAN_SCHEMA)
    except (OSError, json.JSONDecodeError, jsonschema.ValidationError, ValueError) as exc:
        print(f"FAIL: invalid simulator plan: {exc}", file=sys.stderr)
        return 2

    plan_dir = plan_path.parent
    inputs = plan["inputs"]
    runtime_config_path = resolve_relative(plan_dir, str(inputs["runtimeConfigPath"]))
    trace_path = resolve_relative(plan_dir, str(plan["outputs"]["tracePath"]))
    driver_result_path = (
        Path(args.out_json).resolve()
        if args.out_json.strip()
        else derive_driver_result_path(trace_path)
    )

    cslc_executable = env_or_which(args.cslc_executable or None, "DOE_CSLC_EXECUTABLE", "cslc")
    sim_runner_executable = args.sim_runner_executable or os.environ.get("DOE_CSL_SIM_RUNNER_EXECUTABLE", "").strip() or None
    runtime_executable = args.runtime_executable or os.environ.get("DOE_CSL_RUNTIME_EXECUTABLE", "").strip() or None

    try:
        compile_summary, compile_targets_payload, working_paths = compile_targets(
            plan_path=plan_path,
            plan=plan,
            cslc_executable=cslc_executable,
        )
        run_summary = run_simulation(
            plan_path=plan_path,
            plan=plan,
            runtime_config_path=runtime_config_path,
            compile_summary=compile_summary,
            compile_targets_payload=compile_targets_payload,
            working_paths=working_paths,
            explicit_sim_runner=runtime_executable or sim_runner_executable,
        )
        driver_result = build_driver_result(
            plan_path=plan_path,
            cslc_executable=cslc_executable,
            runtime_config_path=runtime_config_path,
            compile_summary=compile_summary,
            compile_targets_payload=compile_targets_payload,
            run_summary=run_summary,
        )
        jsonschema.Draft202012Validator(load_json(DRIVER_RESULT_SCHEMA)).validate(driver_result)
        write_json(driver_result_path, driver_result)
    except Exception as exc:  # pragma: no cover - fail closed
        failure = {
            "schemaVersion": 1,
            "artifactKind": "csl_simulator_driver_result",
            "target": "wse3",
            "contract": "explicit_driver_outcome",
            "simulatorPlanPath": str(plan_path),
            "compilerExecutable": cslc_executable,
            "runtimeConfigPath": str(runtime_config_path),
            "compile": {
                "attempted": False,
                "status": "failed",
                "reason": f"driver_exception: {exc}",
                "targets": [],
            },
            "run": {
                "attempted": False,
                "status": "blocked",
                "reason": "driver_exception",
                "tracePath": str(trace_path),
                "traceProduced": trace_path.exists(),
                "stdoutPath": str(resolve_relative(plan_dir, str(plan["outputs"]["stdoutPath"]))),
                "stderrPath": str(resolve_relative(plan_dir, str(plan["outputs"]["stderrPath"]))),
            },
        }
        write_json(driver_result_path, failure)
        print(f"FAIL: driver exception: {exc}", file=sys.stderr)
        return 5

    compile_status = driver_result["compile"]["status"]
    run_status = driver_result["run"]["status"]
    if compile_status == "succeeded" and run_status == "succeeded":
        return 0
    if compile_status == "failed":
        return 3
    if run_status == "failed":
        return 4
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
