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
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[3]
SIM_PLAN_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-simulator-plan.schema.json"
DRIVER_RESULT_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-simulator-driver-result.schema.json"
RUNTIME_CONFIG_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-runtime-config.schema.json"
OPERATION_GRAPH_SCHEMA = REPO_ROOT / "config" / "csl-operation-graph.schema.json"

# Matches `@export_name("<symbol>", <type>[, <bool>]);`.
# The type pattern uses non-greedy `.+?` anchored on the closing `);` so it
# accepts function types like `fn()void` whose `)` would be excluded by a
# simpler character-class approach. Assumes each `@export_name` declaration
# is on a single line (matches canonical SDK layout.csl style).
_EXPORT_NAME_RE = re.compile(
    r"""@export_name\s*\(\s*
        "(?P<name>[A-Za-z_][A-Za-z0-9_]*)"\s*,\s*
        (?P<type>.+?)
        (?:\s*,\s*(?P<mutable>true|false))?
        \s*\)\s*;""",
    re.VERBOSE,
)


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
    payload = load_json(path)
    if payload.get("artifactKind") == "csl_runtime_config":
        schema = load_json(RUNTIME_CONFIG_SCHEMA)
        jsonschema.Draft202012Validator(schema).validate(payload)
    return payload


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
    # SDK v1.4 requires n_channels > 0 (the deprecated CSELFRunner path with
    # n_channels=0 was removed; cslc now raises RuntimeError("n_channels=0
    # corresponds to the deprecated runtime CSELFRunner. Please use
    # n_channels>0 with SdkRuntime") when the legacy shape is invoked).
    # Default to 1 channel; plans may override via runtime.channels, and may
    # opt out of memcpy mode via runtime.memcpy=false when adopting SdkLayout
    # in the future.
    channels = int(runtime.get("channels", 1))
    use_memcpy = bool(runtime.get("memcpy", True))

    # SDK v1.4 memcpy-mode compiles require an explicit --fabric-offsets and a
    # --fabric-dims that accounts for memcpy's reserved margin around the PE
    # rectangle. cslc v1.4 raises:
    #     RuntimeError: The core must have --fabric-offsets=4+width_west_buf,1
    # when these are missing. The canonical offsets are (4 + west_buf, 1) and
    # the fabric is sized as
    #     (west_buf + 4 + kernel_w + east_buf + 3, 1 + kernel_h + 1)
    # per the SDK gemv-checkerboard benchmark's 4x4 kernel / 11x6 fabric
    # configuration. Plans may override any of these via
    # runtime.fabricOffsets / runtime.fabricDims / runtime.widthWestBuf /
    # runtime.widthEastBuf without requiring a driver change.
    width_west_buf = int(runtime.get("widthWestBuf", 0))
    width_east_buf = int(runtime.get("widthEastBuf", 0))
    fabric_offset_x = width_west_buf + 4
    fabric_offset_y = 1
    fabric_offsets = runtime.get("fabricOffsets") or [fabric_offset_x, fabric_offset_y]
    fabric_offset_x, fabric_offset_y = int(fabric_offsets[0]), int(fabric_offsets[1])
    fabric_dims = runtime.get("fabricDims") or [
        width_west_buf + 4 + width + width_east_buf + 3,
        1 + height + 1,
    ]
    fabric_width, fabric_height = int(fabric_dims[0]), int(fabric_dims[1])

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
            f"--fabric-dims={fabric_width},{fabric_height}",
            f"--fabric-offsets={fabric_offset_x},{fabric_offset_y}",
            f"--channels={channels}",
            # SDK v1.4 requires top-level `param width` / `param height` in
            # emitted layout.csl to be supplied via the explicit --params
            # flag; the deprecated semantics that let them sit uninitialized
            # now errors with "only 'var' and 'extern const' variables may
            # be uninitialized". The plan's peGrid is the source of truth.
            f"--params=width:{width},height:{height}",
            "-o",
            str(output_dir),
        ]
        if width_west_buf > 0:
            command.append(f"--width-west-buf={width_west_buf}")
        if width_east_buf > 0:
            command.append(f"--width-east-buf={width_east_buf}")
        if use_memcpy:
            command.append("--memcpy")
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


def parse_layout_exports(layout_path: Path) -> list[dict[str, Any]]:
    """Parse `@export_name(...)` entries from a layout.csl source.

    Returns a list of `exportedSymbol` dicts in csl-operation-graph.schema.json
    shape. The shape discriminates `device_function` (type matches `fn(...)`)
    from `device_variable`. Functions always carry `mutable=false`; variables
    inherit the mutability bool declared in the CSL `@export_name` call (the
    third positional arg).
    """
    try:
        source = layout_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    exports: list[dict[str, Any]] = []
    for match in _EXPORT_NAME_RE.finditer(source):
        raw_type = match.group("type").strip()
        mutable_raw = match.group("mutable")
        is_function = raw_type.startswith("fn") or raw_type.startswith("fn ") or "fn(" in raw_type
        kind = "device_function" if is_function else "device_variable"
        mutable = (mutable_raw == "true") if mutable_raw is not None else False
        exports.append(
            {
                "name": match.group("name"),
                "type": raw_type,
                "mutable": mutable,
                "kind": kind,
            }
        )
    return exports


def synthesize_operation_graph(
    *,
    plan: dict[str, Any],
    compile_targets_payload: list[dict[str, Any]],
    compile_root: Path,
) -> dict[str, Any] | None:
    """Build a csl-operation-graph.schema.json-shaped artifact for the compile.

    Emits the canonical `rpc_launch` host-side graph the compile inputs expect:
    h2d per mutable device variable, launch of the single `fn()void` export,
    d2h per mutable device variable. This is a contract receipt describing
    what a valid host invocation would look like given the compile inputs —
    not a log of operations that were actually executed.

    The graph is synthesized from the compile INPUTS (layout.csl @export_name
    declarations) and is independent of whether cslc successfully compiled
    those inputs. A blocked compile (compiler_unavailable, missing_compile_inputs,
    actual compile failure) still produces a graph as long as layout.csl exists
    and declares at least one `fn()void` export. This lets gates that require
    an operationGraph block on its ABSENCE (no receipt surface at all) rather
    than on the compile outcome, which is orthogonal.

    Returns None only when no target has parseable exports with at least one
    function export — the genuine "no receipt surface" case.
    """
    # Prefer a successful target when one exists — its declared ABI is known
    # to be v1.4-valid. Fall back to any target with a parseable layout so
    # blocked / failed compiles still emit a receipt.
    ordered = sorted(
        compile_targets_payload,
        key=lambda t: 0 if t.get("status") == "succeeded" else 1,
    )
    target: dict[str, Any] | None = None
    exports: list[dict[str, Any]] = []
    function_exports: list[dict[str, Any]] = []
    for candidate in ordered:
        layout_rel = candidate.get("layoutPath")
        if not layout_rel:
            continue
        layout_path = Path(layout_rel)
        if not layout_path.is_absolute():
            layout_path = (compile_root / layout_rel).resolve()
        candidate_exports = parse_layout_exports(layout_path)
        candidate_function_exports = [
            e for e in candidate_exports if e["kind"] == "device_function"
        ]
        if candidate_exports and candidate_function_exports:
            target = candidate
            exports = candidate_exports
            function_exports = candidate_function_exports
            break
    if target is None:
        return None

    runtime = plan.get("runtime", {})
    pe_grid = runtime.get("peGrid", {"width": 1, "height": 1})
    width = int(pe_grid.get("width", 1))
    height = int(pe_grid.get("height", 1))

    width_west_buf = int(runtime.get("widthWestBuf", 0))
    width_east_buf = int(runtime.get("widthEastBuf", 0))
    fabric_offsets_raw = runtime.get("fabricOffsets") or [width_west_buf + 4, 1]
    fabric_dims_raw = runtime.get("fabricDims") or [
        width_west_buf + 4 + width + width_east_buf + 3,
        1 + height + 1,
    ]
    channels = int(runtime.get("channels", 1))
    memcpy_enabled = bool(runtime.get("memcpy", True))

    inputs = plan.get("inputs", {})
    compile_targets = []
    for compile_target in inputs.get("compileTargets", []):
        compile_targets.append(
            {
                "name": str(compile_target["name"]),
                "layout": str(compile_target["layout"]),
                "peProgram": str(compile_target["peProgram"]),
            }
        )
    output_dir = str(target.get("outputDir") or inputs.get("compileRootPath", "compile"))

    compile_section: dict[str, Any] = {
        "arch": str(plan.get("target", "wse3")),
        "fabricDims": [int(fabric_dims_raw[0]), int(fabric_dims_raw[1])],
        "fabricOffsets": [int(fabric_offsets_raw[0]), int(fabric_offsets_raw[1])],
        "peGrid": {"width": width, "height": height},
        "channels": channels,
        "memcpy": memcpy_enabled,
        "params": [
            {"name": "width", "type": "i16", "value": width},
            {"name": "height", "type": "i16", "value": height},
        ],
        "importPaths": [],
        "outputDir": output_dir,
        "compileTargets": compile_targets,
    }
    if width_west_buf > 0:
        compile_section["widthWestBuf"] = width_west_buf
    if width_east_buf > 0:
        compile_section["widthEastBuf"] = width_east_buf

    roi = {"x": 0, "y": 0, "width": width, "height": height}
    operations: list[dict[str, Any]] = []
    mutable_variables = [
        e for e in exports if e["kind"] == "device_variable" and e["mutable"]
    ]
    for var in mutable_variables:
        operations.append(
            {
                "operationId": f"h2d-{var['name'].lower().replace('_', '-')}",
                "kind": "memcpy_h2d",
                "targetKind": "device_symbol",
                "deviceSymbol": var["name"],
                "roi": roi,
                # Placeholder: the actual per-PE element count is set by the
                # host at runtime from the model's tensor shape. The synthesized
                # graph documents the call shape, not the execution trace.
                "elementsPerPE": 1,
                "dataType": "MEMCPY_32BIT",
                "order": "ROW_MAJOR",
                "streaming": False,
                "nonblock": True,
            }
        )
    launch_fn = function_exports[0]["name"]
    operations.append(
        {
            "operationId": f"launch-{launch_fn.lower().replace('_', '-')}",
            "kind": "launch",
            "functionName": launch_fn,
            "args": [],
            "nonblock": False,
            "unblockCheckpointRequired": True,
        }
    )
    for var in mutable_variables:
        operations.append(
            {
                "operationId": f"d2h-{var['name'].lower().replace('_', '-')}",
                "kind": "memcpy_d2h",
                "targetKind": "device_symbol",
                "deviceSymbol": var["name"],
                "roi": roi,
                "elementsPerPE": 1,
                "dataType": "MEMCPY_32BIT",
                "order": "ROW_MAJOR",
                "streaming": False,
                "nonblock": False,
            }
        )

    graph_id = f"{compile_targets[0]['name']}-rpc-launch" if compile_targets else "csl-operation-graph"
    # Graph IDs must start with [a-z0-9] and use only [a-z0-9_.-]; normalize
    # the kernel name to match.
    graph_id = re.sub(r"[^a-z0-9_.-]", "-", graph_id.lower()).strip("-.")
    if not graph_id or not graph_id[0].isalnum():
        graph_id = "csl-operation-graph"

    return {
        "schemaVersion": 1,
        "artifactKind": "csl_operation_graph",
        "graphId": graph_id,
        "orchestrationMode": "memcpy",
        "executionPattern": "rpc_launch",
        "sdkVersionFloor": "1.4.0",
        "compile": compile_section,
        "exportedSymbols": exports,
        "operations": operations,
        "sdkReferences": [
            "https://sdk.cerebras.net/csl/code-examples/tutorial-gemv-01-complete-program",
            "https://sdk.cerebras.net/sdk-release-notes/sdk-rel-notes-cumulative",
        ],
    }


def build_driver_result(
    *,
    plan_path: Path,
    cslc_executable: str | None,
    runtime_config_path: Path,
    compile_summary: dict[str, Any],
    compile_targets_payload: list[dict[str, Any]],
    run_summary: dict[str, Any],
    operation_graph: dict[str, Any] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
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
    if operation_graph is not None:
        result["operationGraph"] = operation_graph
    return result


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
        operation_graph = synthesize_operation_graph(
            plan=plan,
            compile_targets_payload=compile_targets_payload,
            compile_root=working_paths["compileRoot"],
        )
        if operation_graph is not None:
            try:
                jsonschema.Draft202012Validator(load_json(OPERATION_GRAPH_SCHEMA)).validate(
                    operation_graph
                )
            except jsonschema.ValidationError as exc:
                # Fail closed on a malformed synthesized graph rather than
                # writing an invalid artifact. The compile section still lands
                # in driver-result.compile; the operationGraph is skipped so
                # downstream gates see "no graph bound" instead of a bogus one.
                print(
                    f"WARN: synthesized operation graph failed schema validation: {exc.message}",
                    file=sys.stderr,
                )
                operation_graph = None
        driver_result = build_driver_result(
            plan_path=plan_path,
            cslc_executable=cslc_executable,
            runtime_config_path=runtime_config_path,
            compile_summary=compile_summary,
            compile_targets_payload=compile_targets_payload,
            run_summary=run_summary,
            operation_graph=operation_graph,
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
