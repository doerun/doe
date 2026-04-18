#!/usr/bin/env python3
"""Validate CSL operation-graph referential and source contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.lib.bench_utils import detect_repo_root, load_json

OPERATION_GRAPH_SCHEMA = "config/csl-operation-graph.schema.json"


@dataclass(frozen=True)
class OperationGraphTarget:
    path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="", help="Repository root. Auto-detected when omitted.")
    parser.add_argument(
        "--graph",
        action="append",
        default=[],
        help=(
            "Operation graph path relative to root. May be repeated. "
            "Defaults to csl-operation-graph schema targets."
        ),
    )
    return parser.parse_args()


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def require_array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def load_registered_targets(root: Path) -> list[OperationGraphTarget]:
    registry = require_object(
        load_json(root / "config" / "schema-targets.json"),
        "config/schema-targets.json",
    )
    targets: list[OperationGraphTarget] = []
    for index, entry in enumerate(require_array(registry.get("targets"), "targets")):
        entry_obj = require_object(entry, f"targets[{index}]")
        schema_path = require_string(entry_obj.get("schema"), f"targets[{index}].schema")
        data_path = require_string(entry_obj.get("data"), f"targets[{index}].data")
        if schema_path == OPERATION_GRAPH_SCHEMA:
            targets.append(OperationGraphTarget(path=data_path))
    if not targets:
        raise ValueError(
            f"no registered schema targets found for {OPERATION_GRAPH_SCHEMA}"
        )
    return targets


def resolve_repo_path(root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return root / path


def collect_symbols(graph: dict[str, Any], kind: str) -> set[str]:
    symbols = require_array(graph.get("exportedSymbols"), "exportedSymbols")
    names: set[str] = set()
    for index, symbol in enumerate(symbols):
        symbol_obj = require_object(symbol, f"exportedSymbols[{index}]")
        symbol_kind = require_string(symbol_obj.get("kind"), f"exportedSymbols[{index}].kind")
        if symbol_kind == kind:
            names.add(require_string(symbol_obj.get("name"), f"exportedSymbols[{index}].name"))
    return names


def collect_color_names(graph: dict[str, Any]) -> set[str]:
    compile_obj = require_object(graph.get("compile"), "compile")
    colors = compile_obj.get("colors", [])
    if colors is None:
        colors = []
    names: set[str] = set()
    for index, color in enumerate(require_array(colors, "compile.colors")):
        color_obj = require_object(color, f"compile.colors[{index}]")
        names.add(require_string(color_obj.get("name"), f"compile.colors[{index}].name"))
    return names


def validate_unique_ids(items: list[Any], field: str, label: str) -> list[str]:
    failures: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(items):
        obj = require_object(value, f"{label}[{index}]")
        item_id = require_string(obj.get(field), f"{label}[{index}].{field}")
        if item_id in seen:
            failures.append(f"{label}: duplicate {field}={item_id}")
        seen.add(item_id)
    return failures


def roi_fits(roi: dict[str, Any], pe_grid: dict[str, Any]) -> bool:
    return (
        roi["x"] + roi["width"] <= pe_grid["width"]
        and roi["y"] + roi["height"] <= pe_grid["height"]
    )


def strip_line_comments(source: str) -> str:
    return re.sub(r"//.*", "", source)


def find_function_body(source: str, function_name: str) -> str | None:
    pattern = re.compile(r"\bfn\s+" + re.escape(function_name) + r"\s*\([^)]*\)[^{]*\{")
    match = pattern.search(source)
    if match is None:
        return None
    body_start = match.end()
    depth = 1
    cursor = body_start
    while cursor < len(source):
        char = source[cursor]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[body_start:cursor]
        cursor += 1
    return None


def body_ends_with_unblock(body: str) -> bool:
    uncommented = strip_line_comments(body)
    return re.search(r"sys_mod\.unblock_cmd_stream\(\)\s*;\s*$", uncommented) is not None


def target_sources(root: Path, graph: dict[str, Any]) -> list[Path]:
    compile_obj = require_object(graph.get("compile"), "compile")
    targets = require_array(compile_obj.get("compileTargets"), "compile.compileTargets")
    sources: list[Path] = []
    for index, target in enumerate(targets):
        target_obj = require_object(target, f"compile.compileTargets[{index}]")
        pe_program = require_string(
            target_obj.get("peProgram"),
            f"compile.compileTargets[{index}].peProgram",
        )
        sources.append(resolve_repo_path(root, pe_program))
    return sources


def validate_unblock_checkpoint(
    root: Path,
    graph_path: str,
    graph: dict[str, Any],
    function_name: str,
) -> list[str]:
    failures: list[str] = []
    sources = target_sources(root, graph)
    missing_sources = [path for path in sources if not path.exists()]
    if missing_sources:
        for path in missing_sources:
            failures.append(f"{graph_path}: missing CSL source for unblock check: {path}")
        return failures

    inspected = 0
    for source_path in sources:
        source = source_path.read_text(encoding="utf-8")
        body = find_function_body(source, function_name)
        if body is None:
            continue
        inspected += 1
        if body_ends_with_unblock(body):
            return []
        failures.append(
            f"{graph_path}: {source_path}: function {function_name} must end "
            "with sys_mod.unblock_cmd_stream()"
        )
    if inspected == 0:
        failures.append(
            f"{graph_path}: function {function_name} not found in compileTargets peProgram sources"
        )
    return failures


def validate_memcpy_graph(root: Path, graph_path: str, graph: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    variable_symbols = collect_symbols(graph, "device_variable")
    function_symbols = collect_symbols(graph, "device_function")
    color_names = collect_color_names(graph)
    execution_pattern = require_string(graph.get("executionPattern"), "executionPattern")
    compile_obj = require_object(graph.get("compile"), "compile")
    pe_grid = require_object(compile_obj.get("peGrid"), "compile.peGrid")

    operations = require_array(graph.get("operations"), "operations")
    failures.extend(validate_unique_ids(operations, "operationId", "operations"))
    has_launch = False
    has_streaming_color_memcpy = False
    for index, operation in enumerate(operations):
        op_obj = require_object(operation, f"operations[{index}]")
        op_kind = require_string(op_obj.get("kind"), f"operations[{index}].kind")
        op_id = require_string(op_obj.get("operationId"), f"operations[{index}].operationId")
        if op_kind in {"memcpy_h2d", "memcpy_d2h"}:
            target_kind = require_string(
                op_obj.get("targetKind"),
                f"operations[{index}].targetKind",
            )
            if target_kind == "device_symbol":
                symbol = require_string(
                    op_obj.get("deviceSymbol"),
                    f"operations[{index}].deviceSymbol",
                )
                if symbol not in variable_symbols:
                    failures.append(
                        f"{graph_path}: {op_id}: deviceSymbol {symbol} is not "
                        "an exported device_variable"
                    )
            elif target_kind == "memcpy_color":
                color = require_string(
                    op_obj.get("memcpyColor"),
                    f"operations[{index}].memcpyColor",
                )
                if color not in color_names:
                    failures.append(
                        f"{graph_path}: {op_id}: memcpyColor {color} is not "
                        "declared in compile.colors"
                    )
                if op_obj.get("streaming") is True:
                    has_streaming_color_memcpy = True
            else:
                failures.append(f"{graph_path}: {op_id}: unknown targetKind {target_kind}")
            roi = require_object(op_obj.get("roi"), f"operations[{index}].roi")
            if not roi_fits(roi, pe_grid):
                failures.append(
                    f"{graph_path}: {op_id}: roi exceeds peGrid "
                    f"{pe_grid['width']}x{pe_grid['height']}"
                )
        elif op_kind == "launch":
            has_launch = True
            function_name = require_string(
                op_obj.get("functionName"),
                f"operations[{index}].functionName",
            )
            if function_name not in function_symbols:
                failures.append(
                    f"{graph_path}: {op_id}: functionName {function_name} is not "
                    "an exported device_function"
                )
            if op_obj.get("unblockCheckpointRequired") is True:
                failures.extend(
                    validate_unblock_checkpoint(root, graph_path, graph, function_name)
                )
        elif op_kind in {"send", "receive"}:
            failures.append(
                f"{graph_path}: {op_id}: {op_kind} operation requires orchestrationMode=sdklayout"
            )
        else:
            failures.append(f"{graph_path}: {op_id}: unknown operation kind {op_kind}")

    if execution_pattern == "rpc_launch" and not has_launch:
        failures.append(f"{graph_path}: rpc_launch pattern requires at least one launch op")
    if execution_pattern == "streaming_memcpy_driven":
        if not has_streaming_color_memcpy:
            failures.append(
                f"{graph_path}: streaming_memcpy_driven pattern requires at least "
                "one streaming memcpy_color operation"
            )
    elif execution_pattern != "rpc_launch":
        failures.append(
            f"{graph_path}: unsupported memcpy executionPattern {execution_pattern}"
        )
    return failures


def validate_sdklayout_graph(graph_path: str, graph: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    execution_pattern = require_string(graph.get("executionPattern"), "executionPattern")
    if execution_pattern != "sdklayout_stream_graph":
        failures.append(
            f"{graph_path}: sdklayout mode requires executionPattern=sdklayout_stream_graph"
        )
    code_regions = require_array(graph.get("codeRegions"), "codeRegions")
    ports = require_array(graph.get("ports"), "ports")
    connections = require_array(graph.get("connections"), "connections")
    streams = require_array(graph.get("streams"), "streams")
    operations = require_array(graph.get("operations"), "operations")

    failures.extend(validate_unique_ids(code_regions, "regionId", "codeRegions"))
    failures.extend(validate_unique_ids(ports, "portId", "ports"))
    failures.extend(validate_unique_ids(connections, "connectionId", "connections"))
    failures.extend(validate_unique_ids(streams, "streamId", "streams"))
    failures.extend(validate_unique_ids(operations, "operationId", "operations"))

    region_ids = {
        require_string(require_object(item, "codeRegion").get("regionId"), "codeRegion.regionId")
        for item in code_regions
    }
    port_ids = {
        require_string(require_object(item, "port").get("portId"), "port.portId")
        for item in ports
    }
    stream_ids = {
        require_string(require_object(item, "stream").get("streamId"), "stream.streamId")
        for item in streams
    }

    for index, port in enumerate(ports):
        port_obj = require_object(port, f"ports[{index}]")
        region_id = require_string(port_obj.get("regionId"), f"ports[{index}].regionId")
        if region_id not in region_ids:
            failures.append(f"{graph_path}: ports[{index}]: unknown regionId {region_id}")

    for index, connection in enumerate(connections):
        connection_obj = require_object(connection, f"connections[{index}]")
        for field in ("fromPortId", "toPortId"):
            port_id = require_string(connection_obj.get(field), f"connections[{index}].{field}")
            if port_id not in port_ids:
                failures.append(f"{graph_path}: connections[{index}]: unknown {field} {port_id}")

    for index, stream in enumerate(streams):
        stream_obj = require_object(stream, f"streams[{index}]")
        port_id = require_string(stream_obj.get("portId"), f"streams[{index}].portId")
        if port_id not in port_ids:
            failures.append(f"{graph_path}: streams[{index}]: unknown portId {port_id}")

    for index, operation in enumerate(operations):
        op_obj = require_object(operation, f"operations[{index}]")
        op_kind = require_string(op_obj.get("kind"), f"operations[{index}].kind")
        op_id = require_string(op_obj.get("operationId"), f"operations[{index}].operationId")
        if op_kind in {"send", "receive"}:
            stream_id = require_string(op_obj.get("streamId"), f"operations[{index}].streamId")
            if stream_id not in stream_ids:
                failures.append(f"{graph_path}: {op_id}: unknown streamId {stream_id}")
        elif op_kind in {"memcpy_h2d", "memcpy_d2h", "launch"}:
            failures.append(
                f"{graph_path}: {op_id}: {op_kind} operation requires orchestrationMode=memcpy"
            )
        else:
            failures.append(f"{graph_path}: {op_id}: unknown operation kind {op_kind}")
    return failures


def validate_graph(root: Path, target: OperationGraphTarget) -> list[str]:
    graph_path = root / target.path
    if not graph_path.exists():
        return [f"missing CSL operation graph: {target.path}"]
    graph = require_object(load_json(graph_path), target.path)
    mode = require_string(graph.get("orchestrationMode"), f"{target.path}.orchestrationMode")
    if mode == "memcpy":
        return validate_memcpy_graph(root, target.path, graph)
    if mode == "sdklayout":
        return validate_sdklayout_graph(target.path, graph)
    return [f"{target.path}: unknown orchestrationMode {mode}"]


def main() -> int:
    args = parse_args()
    root = detect_repo_root(Path(args.root) if args.root else None)
    targets = (
        [OperationGraphTarget(path=path) for path in args.graph]
        if args.graph
        else load_registered_targets(root)
    )

    failures: list[str] = []
    for target in targets:
        try:
            failures.extend(validate_graph(root, target))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            failures.append(f"{target.path}: {exc}")

    if failures:
        print("FAIL: csl operation graph gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(f"PASS: csl operation graph gate (validated={len(targets)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
