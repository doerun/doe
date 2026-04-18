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

# Matches `var <name>: [<size_expr>]<elem_type>` in pe_program.csl.
# <size_expr> allows identifier references and `*` products (`chunk_size * 4`)
# so the parser reads the per-PE element count even when the size is derived
# from a compile-time param expression. We capture the raw expression string
# — the driver resolves it against compile.params[] bindings later.
_PE_PROGRAM_VAR_RE = re.compile(
    r"""var\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*
        \[\s*(?P<size_expr>[^\]]+?)\s*\]
        \s*(?P<elem_type>[A-Za-z_][A-Za-z0-9_]*)""",
    re.VERBOSE,
)

# Matches `@group(G) @binding(B) var<storage[, ACCESS]> NAME: TYPE;` in WGSL.
# Captures the binding name and access mode. The optional access mode defaults
# to `read` per WGSL spec (when `var<storage>` appears without a second
# argument). Uniforms (`var<uniform>`) and workgroup vars are NOT captured
# here — this parser is only for the storage-buffer role inference the driver
# uses to pick h2d vs d2h per exported symbol.
_WGSL_STORAGE_BINDING_RE = re.compile(
    r"""@group\(\s*\d+\s*\)\s*
        @binding\(\s*\d+\s*\)\s*
        var\s*<\s*storage
        (?:\s*,\s*(?P<access>read_write|read|write))?
        \s*>\s*
        (?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:""",
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


# Ordered list of (pattern, failure_code) pairs used to classify cslc stderr
# into v1.4-specific failure taxonomy codes. First match wins. The order is
# load-bearing — broader regex (e.g. `error: expected`) is listed AFTER the
# more specific patterns so a v1.4 type-mismatch lands on
# `csl_compile_type_mismatch` instead of the generic parse-error bucket.
#
# This taxonomy is intentionally narrow: only codes we have first-party
# evidence for (either from running our own CSL through v1.4 cslc or from
# SDK 1.4 release notes) are included. Anything else falls through to
# `csl_compile_unclassified` and the raw stderr path is the evidence —
# never silently relabeled as `compile_failed` without a known pattern.
_CSLC_FAILURE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"n_channels=0 corresponds to the deprecated runtime CSELFRunner"),
        "csl_compile_deprecated_cselfrunner",
    ),
    (
        re.compile(r"The core must have --fabric-offsets="),
        "csl_compile_fabric_offsets_required",
    ),
    (
        re.compile(r"only 'var' and 'extern const' variables may be uninitialized"),
        "csl_compile_uninitialized_param",
    ),
    (
        re.compile(r"exported symbol type mismatch"),
        "csl_compile_export_type_mismatch",
    ),
    (
        re.compile(r"use of undeclared identifier"),
        "csl_compile_undeclared_identifier",
    ),
    (
        re.compile(r"ran out of PE memory"),
        "csl_compile_pe_memory_exhausted",
    ),
    (
        re.compile(r"expected type '[^']+', got: '[^']+'"),
        "csl_compile_type_mismatch",
    ),
    (
        re.compile(r"function expects \d+ arguments?, \d+ provided"),
        "csl_compile_arity_mismatch",
    ),
    (
        re.compile(r"Unexpected character at this location"),
        "csl_compile_parser_reject",
    ),
    (
        re.compile(r"singularity not in \$PATH|apptainer not in \$PATH"),
        "csl_compile_sandbox_runtime_missing",
    ),
]


def classify_cslc_failure(stderr_path: Path | str) -> str:
    """Scan cslc stderr for a known v1.4 failure signature.

    Returns a specific `csl_compile_*` code when one of the patterns in
    `_CSLC_FAILURE_PATTERNS` matches, otherwise `csl_compile_unclassified`.
    The full stderr log is always preserved — this only categorizes, it
    doesn't replace the evidence.
    """
    try:
        text = Path(stderr_path).read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return "csl_compile_unclassified"
    for pattern, code in _CSLC_FAILURE_PATTERNS:
        if pattern.search(text):
            return code
    return "csl_compile_unclassified"


def check_unblock_cmd_stream(pe_program_path: Path, launch_function: str) -> str:
    """Static check: for an rpc_launch execution pattern, every launched
    device function must call `sys_mod.unblock_cmd_stream()` before returning,
    or the host-side memcpy command stream blocks indefinitely. Returns a
    classification code: `unblock_present`, `unblock_missing`, or
    `unblock_unknown` (source unreadable).

    This is a conservative lexical check — we don't parse the function body.
    If the file contains `sys_mod.unblock_cmd_stream()` anywhere after the
    function declaration, we treat it as present. Good enough for the
    emitter patterns we control today; a richer check would walk the CSL
    AST.
    """
    try:
        source = pe_program_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return "unblock_unknown"
    fn_marker = f"fn {launch_function}("
    fn_idx = source.find(fn_marker)
    if fn_idx < 0:
        return "unblock_unknown"
    tail = source[fn_idx:]
    if "sys_mod.unblock_cmd_stream()" in tail:
        return "unblock_present"
    return "unblock_missing"


def materialize_command(template: list[str], substitutions: dict[str, str]) -> list[str]:
    command: list[str] = []
    for item in template:
        rendered = item
        for key, value in substitutions.items():
            rendered = rendered.replace("{" + key + "}", value)
        if rendered == "":
            continue
        command.append(rendered)
    return command


def redact_command_for_receipt(command: list[str], cmaddr: str) -> list[str]:
    """Remove CM endpoint details from persisted command receipts.

    The process still receives the real endpoint. The JSON receipt records
    that hardware targeting was requested without leaking an internal
    IP:port into commit-eligible artifacts.
    """
    if not cmaddr:
        return command
    redacted: list[str] = []
    for item in command:
        redacted.append(item.replace(cmaddr, "$DOE_CSL_CMADDR"))
    return redacted


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
        target_failure_code: str | None = None
        if return_code != 0:
            overall_failed = True
            target_failure_code = classify_cslc_failure(stderr_written)
        unblock_status = check_unblock_cmd_stream(pe_program_path, "compute")
        target_entry: dict[str, Any] = {
            "name": name,
            "layoutPath": str(layout_path),
            "peProgramPath": str(pe_program_path),
            "outputDir": str(output_dir),
            "status": status,
            "exitCode": return_code,
            "stdoutPath": stdout_written,
            "stderrPath": stderr_written,
            "command": command,
            "unblockCmdStreamCheck": unblock_status,
        }
        if target_failure_code is not None:
            target_entry["failureCode"] = target_failure_code
        target_results.append(target_entry)

    summary: dict[str, Any] = {
        "attempted": True,
        "status": "failed" if overall_failed else "succeeded",
        "reason": "compile_failed" if overall_failed else "compiled",
        "compilerExecutable": cslc_executable,
    }
    # Escalate the summary reason from the generic `compile_failed` to the
    # first specific failure code when every failed target shares the same
    # classification. This keeps the top-level receipt specific ("the 270M
    # compile failed because n_channels=0 was rejected") instead of generic.
    failure_codes = [t.get("failureCode") for t in target_results if t.get("failureCode")]
    if failure_codes:
        unique = set(failure_codes)
        if len(unique) == 1:
            summary["reason"] = next(iter(unique))
        else:
            summary["reason"] = "csl_compile_failed_multi"
            summary["failureCodes"] = sorted(unique)
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
    csl_cmaddr: str,
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
            "executionTarget": "system" if csl_cmaddr else "simfabric",
            "cmaddrProvided": bool(csl_cmaddr),
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
            "executionTarget": "system" if csl_cmaddr else "simfabric",
            "cmaddrProvided": bool(csl_cmaddr),
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
            "executionTarget": "system" if csl_cmaddr else "simfabric",
            "cmaddrProvided": bool(csl_cmaddr),
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
        "cmaddr": csl_cmaddr,
        "cmaddr_arg": f"--cmaddr={csl_cmaddr}" if csl_cmaddr else "",
        "execution_target": "system" if csl_cmaddr else "simfabric",
    }
    command = materialize_command([str(item) for item in raw_command], substitutions)
    return_code, stdout_written, stderr_written = run_command(command, stdout_path, stderr_path)
    return {
        "attempted": True,
        "status": "succeeded" if return_code == 0 and trace_path.exists() else "failed",
        "reason": "ran" if return_code == 0 and trace_path.exists() else "runtime_failed",
        "executionTarget": "system" if csl_cmaddr else "simfabric",
        "cmaddrProvided": bool(csl_cmaddr),
        "command": redact_command_for_receipt(command, csl_cmaddr),
        "exitCode": return_code,
        "tracePath": str(trace_path),
        "traceProduced": trace_path.exists(),
        "stdoutPath": stdout_written,
        "stderrPath": stderr_written,
    }


def parse_wgsl_storage_bindings(wgsl_path: Path) -> dict[str, str]:
    """Parse WGSL `@group(G) @binding(B) var<storage, ACCESS> NAME: TYPE;`
    declarations and return a `{name: access_mode}` map.

    Access modes follow the WGSL spec: `read`, `read_write`, `write`.
    A bare `var<storage>` without an access-mode argument defaults to `read`.
    The returned names are WGSL binding names — they match exported symbol
    names produced by the Doe CSL bundle emitter (the emitter forwards the
    WGSL binding name verbatim to `@export_name`).

    The driver uses this map in synthesize_operation_graph to pick the
    correct host-side memcpy direction for each symbol:
      - `read`       → memcpy_h2d only (host writes the input)
      - `write`      → memcpy_d2h only (host reads the output)
      - `read_write` → both h2d and d2h
    When no sourceWgslPath is available the synthesizer falls back to the
    layout.csl mutable-bit heuristic (emits both h2d + d2h for every mutable
    variable), which is conservative but over-reports directions.
    """
    try:
        source = wgsl_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    bindings: dict[str, str] = {}
    for match in _WGSL_STORAGE_BINDING_RE.finditer(source):
        name = match.group("name")
        access = match.group("access") or "read"
        # First declaration wins; WGSL forbids duplicate binding names, so
        # collisions would already be a parse error upstream.
        bindings.setdefault(name, access)
    return bindings


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


# `const <name>: <type> = <expr>;` pattern — the 270M fixture uses this shape
# for per-PE size constants (chunk_size, vec_width, flat_len) that feed the
# array dims. Resolving them is essential for elementsPerPE > 1.
_PE_PROGRAM_CONST_RE = re.compile(
    r"""const\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*
        [A-Za-z_][A-Za-z0-9_]*\s*=\s*
        (?P<expr>[^;\n]+?)\s*;""",
    re.VERBOSE,
)

# `param <name>: <type>[ = <default>];` — params with defaults that show up
# in-body (e.g. `param chunk_size: i16 = 1024;`). Capturing the default lets
# the synthesizer resolve size expressions even when the driver's compile
# command doesn't forward a matching --params binding.
_PE_PROGRAM_PARAM_RE = re.compile(
    r"""param\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*
        [A-Za-z_][A-Za-z0-9_]*\s*=\s*
        (?P<default>[^;\n]+?)\s*;""",
    re.VERBOSE,
)


def parse_pe_program_arrays(pe_program_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Parse `var <name>: [<size>]<elem>` + const/param defaults from pe_program.csl.

    Returns (array_decls, compile_time_values).

    array_decls is a map keyed by variable name with
    `{"sizeExpr": str, "elemType": str}`. The driver uses this to populate
    elementsPerPE and dataType on memcpy ops by matching exportedSymbols[].name
    to the pe_program declaration.

    compile_time_values aggregates `const NAME: T = <expr>;` and
    `param NAME: T = <default>;` declarations into a resolved
    `name -> integer` map. Expressions are resolved iteratively — a `const`
    can reference another const or a param as long as the reference was
    declared earlier (pe_program.csl ordering is top-down so this matches
    canonical emission).
    """
    try:
        source = pe_program_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ({}, {})
    decls: dict[str, dict[str, Any]] = {}
    for match in _PE_PROGRAM_VAR_RE.finditer(source):
        name = match.group("name")
        if name in decls:
            continue
        decls[name] = {
            "sizeExpr": match.group("size_expr").strip(),
            "elemType": match.group("elem_type"),
        }
    compile_time: dict[str, int] = {}
    # Walk source in order, resolving consts and params against the running
    # compile_time map. Skip anything that fails to resolve (treat as opaque).
    for match in re.finditer(
        r"(?P<kind>const|param)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?P<expr>[^;\n]+?)\s*;",
        source,
    ):
        name = match.group("name")
        expr = match.group("expr").strip()
        resolved = resolve_size_expr(expr, compile_time)
        if resolved is not None:
            compile_time[name] = resolved
    return (decls, compile_time)


def resolve_size_expr(size_expr: str, params: dict[str, int]) -> int | None:
    """Evaluate a CSL size expression (e.g. `chunk_size * 4`) against param bindings.

    Accepts literal integers, parameter references, and `*` / `+` / `-` of those.
    Returns None if the expression contains an unresolved symbol or unsupported
    operator. Intentionally narrow — this is not a general expression evaluator,
    just enough to cover the `chunk_size`, `chunk_size * N`, and `N * chunk_size`
    shapes the CSL emitter produces today.
    """
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[+\-*()]", size_expr)
    substituted: list[str] = []
    for tok in tokens:
        if tok.isidentifier():
            if tok not in params:
                return None
            substituted.append(str(params[tok]))
        elif tok.isdigit() or tok in "+-*()":
            substituted.append(tok)
        else:
            return None
    try:
        # Evaluate the restricted arithmetic expression with no builtins.
        value = eval("".join(substituted), {"__builtins__": {}}, {})
    except Exception:
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def dtype_for_elem_type(elem_type: str) -> str:
    """Map a CSL scalar element type to a memcpy dataType enum value.

    The operation graph schema only defines MEMCPY_16BIT and MEMCPY_32BIT today
    — the canonical SDK v1.4 memcpy datatypes. 64-bit loads are not part of
    the contract. Unknown types default to MEMCPY_32BIT (the SDK-default for
    f32/u32/i32) and a follow-up should extend the enum when Doe starts
    emitting f16/u16/i16 storage.
    """
    if elem_type in ("f16", "u16", "i16"):
        return "MEMCPY_16BIT"
    return "MEMCPY_32BIT"


_HOST_PLAN_KERNEL_PATTERNS: frozenset[str] = frozenset(
    {
        "gather",
        "reduction",
        "tiled_matmul",
        "attention_linear",
        "attention_tiled",
        "attention_decode",
        "element_wise",
        "fused_gemv_dequant",
        "rope",
        "sample",
    }
)


def load_host_plan_kernels(
    *,
    plan: dict[str, Any],
    plan_dir: Path,
) -> dict[str, dict[str, Any]]:
    """Return {kernelName: {pattern, count}} from the referenced HostPlan.

    Resolves the HostPlan from two sources, in order:
      1. `plan.hostPlan` — inline shape used by tests that synthesize a plan
         in-memory and don't want to stage a sidecar file.
      2. `plan.inputs.hostPlanArtifactPath` — the production shape: the
         simulator-plan schema requires this field to point at a separate
         `csl_host_plan` artifact. When present, we read it from disk and
         extract its `hostPlan.kernels[]`.

    Returns {} on any failure: missing path, unreadable file, malformed JSON,
    kernel pattern outside the known enum, or missing pattern/count fields.
    A broken HostPlan must NOT block op-graph synthesis; the graph's primary
    job is still the rpc_launch receipt for the chosen compile target.
    """
    raw_host_plan: Any = None
    inline = plan.get("hostPlan")
    if isinstance(inline, dict):
        raw_host_plan = inline
    else:
        inputs = plan.get("inputs", {}) or {}
        hp_path_raw = inputs.get("hostPlanArtifactPath")
        if not hp_path_raw:
            return {}
        hp_path = Path(hp_path_raw)
        if not hp_path.is_absolute():
            hp_path = (plan_dir / hp_path).resolve()
        try:
            payload = json.loads(hp_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        host_plan_section = payload.get("hostPlan")
        if not isinstance(host_plan_section, dict):
            return {}
        raw_host_plan = host_plan_section

    kernels_list = raw_host_plan.get("kernels") if isinstance(raw_host_plan, dict) else None
    if not isinstance(kernels_list, list):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for kernel in kernels_list:
        if not isinstance(kernel, dict):
            continue
        name = kernel.get("name")
        pattern = kernel.get("pattern")
        count = kernel.get("count")
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(pattern, str) or pattern not in _HOST_PLAN_KERNEL_PATTERNS:
            continue
        if not isinstance(count, int) or count < 1:
            continue
        out[name] = {"pattern": pattern, "count": count}
    return out


def synthesize_operation_graph(
    *,
    plan: dict[str, Any],
    compile_targets_payload: list[dict[str, Any]],
    compile_root: Path,
    host_plan_kernels: dict[str, dict[str, Any]] | None = None,
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

    # Parse pe_program.csl array declarations so memcpy ops can carry real
    # per-PE element counts and dtypes instead of elementsPerPE: 1
    # placeholders. The size expressions (e.g. `chunk_size * 4`, `flat_len`)
    # are resolved against the compile.params bindings plus any const/param
    # defaults declared in pe_program.csl itself.
    pe_program_rel = target.get("peProgramPath")
    pe_decls: dict[str, dict[str, Any]] = {}
    pe_compile_time: dict[str, int] = {}
    if pe_program_rel:
        pe_program_path = Path(pe_program_rel)
        if not pe_program_path.is_absolute():
            pe_program_path = (compile_root / pe_program_rel).resolve()
        pe_decls, pe_compile_time = parse_pe_program_arrays(pe_program_path)
    params_dict: dict[str, int] = {}
    # Merge ordering: driver-supplied compile params (width/height) come
    # first, then pe_program.csl const/param defaults. The pe_program values
    # are declaration-local defaults and shouldn't override host-supplied
    # bindings when they collide.
    params_dict.update(pe_compile_time)
    for p in compile_section["params"]:
        params_dict[p["name"]] = int(p["value"])
    # chunk_size is a conventional CSL param default; surface it so expressions
    # like `chunk_size * 4` resolve when neither the layout nor pe_program
    # declares a binding.
    params_dict.setdefault("chunk_size", 1024)

    def resolve_var(var_name: str) -> tuple[int, str]:
        """Returns (elementsPerPE, dataType) for a var; falls back to (1, MEMCPY_32BIT)
        when the pe_program decl is missing or its size expression is unresolvable."""
        decl = pe_decls.get(var_name)
        if decl is None:
            return (1, "MEMCPY_32BIT")
        count = resolve_size_expr(decl["sizeExpr"], params_dict)
        if count is None or count <= 0:
            return (1, dtype_for_elem_type(decl["elemType"]))
        return (count, dtype_for_elem_type(decl["elemType"]))

    # Per-symbol host-memcpy direction inference.
    # When the compile target declares sourceWgslPath, parse the WGSL for
    # storage-binding access modes (`read`, `read_write`, `write`) and use
    # them to decide memcpy direction:
    #   - read:       h2d only  (host writes input, device never writes back)
    #   - write:      d2h only  (host reads output, never writes)
    #   - read_write: both      (kernel reads input, writes result in place)
    # This replaces the layout.csl mutable-bit heuristic (which emitted both
    # h2d AND d2h for every mutable variable — conservative but imprecise).
    # Falls back to the heuristic when no WGSL source is available.
    wgsl_access: dict[str, str] = {}
    target_source_wgsl = target.get("sourceWgslPath") if isinstance(target, dict) else None
    if not target_source_wgsl:
        # Also check the original simulator-plan compileTargets entry for
        # sourceWgslPath (driver-target-payload strips it; the plan keeps it).
        for compile_target in inputs.get("compileTargets", []):
            if compile_target.get("name") == target.get("name"):
                target_source_wgsl = compile_target.get("sourceWgslPath")
                break
    if target_source_wgsl:
        wgsl_path = Path(target_source_wgsl)
        if not wgsl_path.is_absolute():
            wgsl_path = (REPO_ROOT / target_source_wgsl).resolve()
        wgsl_access = parse_wgsl_storage_bindings(wgsl_path)

    def needs_h2d(var_name: str, layout_mutable: bool) -> bool:
        access = wgsl_access.get(var_name)
        if access is None:
            # No WGSL source → fall back to layout.csl mutable bit. The host
            # writes to any var layout.csl declares mutable=true.
            return layout_mutable
        return access in ("read", "read_write")

    def needs_d2h(var_name: str, layout_mutable: bool) -> bool:
        access = wgsl_access.get(var_name)
        if access is None:
            return layout_mutable
        return access in ("write", "read_write")

    roi = {"x": 0, "y": 0, "width": width, "height": height}
    operations: list[dict[str, Any]] = []
    # All device_variable exports are candidates; whether each emits h2d,
    # d2h, both, or neither is decided per-var by the WGSL access mode.
    device_variables = [e for e in exports if e["kind"] == "device_variable"]
    for var in device_variables:
        if not needs_h2d(var["name"], var["mutable"]):
            continue
        elems, dtype = resolve_var(var["name"])
        operations.append(
            {
                "operationId": f"h2d-{var['name'].lower().replace('_', '-')}",
                "kind": "memcpy_h2d",
                "targetKind": "device_symbol",
                "deviceSymbol": var["name"],
                "roi": roi,
                "elementsPerPE": elems,
                "dataType": dtype,
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
    for var in device_variables:
        if not needs_d2h(var["name"], var["mutable"]):
            continue
        elems, dtype = resolve_var(var["name"])
        operations.append(
            {
                "operationId": f"d2h-{var['name'].lower().replace('_', '-')}",
                "kind": "memcpy_d2h",
                "targetKind": "device_symbol",
                "deviceSymbol": var["name"],
                "roi": roi,
                "elementsPerPE": elems,
                "dataType": dtype,
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

    graph: dict[str, Any] = {
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

    # Per-target HostPlan pattern bindings. Surface one entry per compile
    # target whose name matches a HostPlan kernel; skip targets with no
    # match rather than synthesizing a placeholder, so downstream gates can
    # distinguish "HostPlan said nothing about this target" from "target
    # has pattern X".
    if host_plan_kernels:
        kernel_patterns: list[dict[str, Any]] = []
        for compile_target in compile_targets:
            name = compile_target["name"]
            binding = host_plan_kernels.get(name)
            if binding is None:
                continue
            normalized = re.sub(r"[^a-z0-9_.-]", "-", name.lower()).strip("-.")
            if not normalized or not normalized[0].isalnum():
                continue
            kernel_patterns.append(
                {
                    "targetName": normalized,
                    "pattern": binding["pattern"],
                    "count": int(binding["count"]),
                }
            )
        if kernel_patterns:
            graph["kernelPatterns"] = kernel_patterns

    return graph


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
    parser.add_argument(
        "--cmaddr",
        default="",
        help=(
            "Optional Cerebras CM endpoint (IP_ADDRESS:PORT). When omitted, "
            "SdkRuntime host commands should run on simfabric."
        ),
    )
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
    csl_cmaddr = args.cmaddr.strip() or os.environ.get("DOE_CSL_CMADDR", "").strip()

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
            csl_cmaddr=csl_cmaddr,
        )
        host_plan_kernels = load_host_plan_kernels(plan=plan, plan_dir=plan_dir)
        operation_graph = synthesize_operation_graph(
            plan=plan,
            compile_targets_payload=compile_targets_payload,
            compile_root=working_paths["compileRoot"],
            host_plan_kernels=host_plan_kernels,
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
                "executionTarget": "system" if csl_cmaddr else "simfabric",
                "cmaddrProvided": bool(csl_cmaddr),
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
