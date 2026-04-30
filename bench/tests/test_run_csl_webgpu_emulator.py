from __future__ import annotations

import json
import math
import struct
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

import jsonschema

from bench.tools.build_csl_webgpu_emulator_input import (
    build_emulator_input,
    validate_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_SCHEMA = REPO_ROOT / "config/csl-webgpu-emulator-input.schema.json"
RESULT_SCHEMA = REPO_ROOT / "config/csl-webgpu-emulator-result.schema.json"
EMULATOR = REPO_ROOT / "bench/tools/run_csl_webgpu_emulator.mjs"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_f32(path: Path, values: list[float]) -> bytes:
    payload = struct.pack(f"<{len(values)}f", *values)
    path.write_bytes(payload)
    return payload


def _write_u32(path: Path, values: list[int]) -> bytes:
    payload = struct.pack(f"<{len(values)}I", *values)
    path.write_bytes(payload)
    return payload


def _seed_residual_bundle(root: Path) -> None:
    compile_dir = root / "compile" / "residual"
    compile_dir.mkdir(parents=True)
    (compile_dir / "layout.csl").write_text(
        '@export_name("input", input, true);\n'
        '@export_name("residual", residual, true);\n'
        '@export_name("output", output, true);\n'
        '@export_name("compute", compute, false);\n',
        encoding="utf-8",
    )
    (compile_dir / "pe_program.csl").write_text(
        """
param memcpy_params;
param width: u16;
param height: u16;
param chunk_size: i16 = 4;
const sys_mod = @import_module("<memcpy/memcpy>", memcpy_params);
var input: [chunk_size]f32 = @zeros([chunk_size]f32);
var residual: [chunk_size]f32 = @zeros([chunk_size]f32);
var output: [chunk_size]f32 = @zeros([chunk_size]f32);
var input_ptr: [*]f32 = &input;
var residual_ptr: [*]f32 = &residual;
var output_ptr: [*]f32 = &output;
fn compute() void {
    for (@range(i16, chunk_size)) |_idx| {
        const idx = @as(u32, _idx);
        output[idx] = input[idx] + residual[idx];
    }
    sys_mod.unblock_cmd_stream();
}
comptime {
    @export_symbol(input_ptr, "input");
    @export_symbol(residual_ptr, "residual");
    @export_symbol(output_ptr, "output");
    @export_symbol(compute);
}
""".lstrip(),
        encoding="utf-8",
    )
    operation_graph = {
        "schemaVersion": 1,
        "artifactKind": "csl_operation_graph",
        "graphId": "residual-rpc-launch",
        "orchestrationMode": "memcpy",
        "executionPattern": "rpc_launch",
        "sdkVersionFloor": "2.10.0",
        "compile": {
            "arch": "wse3",
            "fabricDims": [8, 3],
            "fabricOffsets": [4, 1],
            "peGrid": {"width": 1, "height": 1},
            "channels": 1,
            "memcpy": True,
            "params": [
                {"name": "width", "type": "i16", "value": 1},
                {"name": "height", "type": "i16", "value": 1},
            ],
            "importPaths": [],
            "outputDir": "compile/compiled/residual",
            "compileTargets": [
                {
                    "name": "residual",
                    "layout": "compile/residual/layout.csl",
                    "peProgram": "compile/residual/pe_program.csl",
                    "compileParams": {"width": 1, "height": 1, "chunk_size": 4},
                }
            ],
        },
        "exportedSymbols": [
            {"name": "input", "type": "[*]f32", "mutable": True, "kind": "device_variable"},
            {"name": "residual", "type": "[*]f32", "mutable": True, "kind": "device_variable"},
            {"name": "output", "type": "[*]f32", "mutable": True, "kind": "device_variable"},
            {"name": "compute", "type": "fn()void", "mutable": False, "kind": "device_function"},
        ],
        "kernelPatterns": [
            {"targetName": "residual", "pattern": "residual", "count": 1}
        ],
        "operations": [
            {
                "operationId": "h2d-input",
                "kind": "memcpy_h2d",
                "targetKind": "device_symbol",
                "deviceSymbol": "input",
                "roi": {"x": 0, "y": 0, "width": 1, "height": 1},
                "elementsPerPE": 4,
                "dataType": "MEMCPY_32BIT",
                "order": "ROW_MAJOR",
                "streaming": False,
                "nonblock": True,
            },
            {
                "operationId": "h2d-residual",
                "kind": "memcpy_h2d",
                "targetKind": "device_symbol",
                "deviceSymbol": "residual",
                "roi": {"x": 0, "y": 0, "width": 1, "height": 1},
                "elementsPerPE": 4,
                "dataType": "MEMCPY_32BIT",
                "order": "ROW_MAJOR",
                "streaming": False,
                "nonblock": True,
            },
            {
                "operationId": "launch-compute",
                "kind": "launch",
                "functionName": "compute",
                "args": [],
                "nonblock": False,
                "unblockCheckpointRequired": True,
            },
            {
                "operationId": "d2h-output",
                "kind": "memcpy_d2h",
                "targetKind": "device_symbol",
                "deviceSymbol": "output",
                "roi": {"x": 0, "y": 0, "width": 1, "height": 1},
                "elementsPerPE": 4,
                "dataType": "MEMCPY_32BIT",
                "order": "ROW_MAJOR",
                "streaming": False,
                "nonblock": False,
            },
        ],
    }
    simulator_plan = {
        "schemaVersion": 1,
        "artifactKind": "doe_wgsl_simulator_plan",
        "target": "wse3",
        "inputs": {
            "hostPlanArtifactPath": "host-plan.json",
            "runtimeConfigPath": "runtime-config.json",
            "compileRootPath": "compile",
            "compileTargets": [
                {
                    "name": "residual",
                    "layout": "residual/layout.csl",
                    "peProgram": "residual/pe_program.csl",
                    "compileParams": {"width": 1, "height": 1, "chunk_size": 4},
                }
            ],
        },
        "runtime": {"peGrid": {"width": 1, "height": 1}},
        "outputs": {"tracePath": "trace.json"},
    }
    driver_result = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_driver_result",
        "target": "wse3",
        "contract": "explicit_driver_outcome",
        "simulatorPlanPath": str(root / "simulator-plan.json"),
        "runtimeConfigPath": str(root / "runtime-config.json"),
        "compile": {
            "attempted": True,
            "status": "succeeded",
            "reason": "compiled",
            "targets": [{"name": "residual", "status": "succeeded"}],
        },
        "run": {
            "attempted": False,
            "status": "blocked",
            "reason": "compile_only_fixture",
            "tracePath": str(root / "trace.json"),
            "traceProduced": False,
        },
        "operationGraph": operation_graph,
    }
    _write_json(root / "host-plan.json", {"artifactKind": "doe_wgsl_host_plan"})
    _write_json(root / "runtime-config.json", {"schemaVersion": 1})
    _write_json(root / "simulator-plan.json", simulator_plan)
    _write_json(root / "driver-result.json", driver_result)


def _seed_gather_bundle(root: Path) -> None:
    compile_dir = root / "compile" / "embed"
    compile_dir.mkdir(parents=True)
    (compile_dir / "layout.csl").write_text(
        '@export_name("indices", indices, true);\n'
        '@export_name("table", table, true);\n'
        '@export_name("output", output, true);\n'
        '@export_name("compute", compute, false);\n',
        encoding="utf-8",
    )
    (compile_dir / "pe_program.csl").write_text(
        """
// PE program: embedding gather
param memcpy_params;
param width: u16;
param height: u16;
param rows_per_pe: i16;
param hidden_per_pe: i16;
param tokens_per_chunk: i16;
const sys_mod = @import_module("<memcpy/memcpy>", memcpy_params);
var indices: [tokens_per_chunk]u32 = @zeros([tokens_per_chunk]u32);
var table: [rows_per_pe * hidden_per_pe]f32 = @zeros([rows_per_pe * hidden_per_pe]f32);
var output: [tokens_per_chunk * hidden_per_pe]f32 = @zeros([tokens_per_chunk * hidden_per_pe]f32);
var indices_ptr: [*]u32 = &indices;
var table_ptr: [*]f32 = &table;
var output_ptr: [*]f32 = &output;
fn compute() void {
    sys_mod.unblock_cmd_stream();
}
comptime {
    @export_symbol(indices_ptr, "indices");
    @export_symbol(table_ptr, "table");
    @export_symbol(output_ptr, "output");
    @export_symbol(compute);
}
""".lstrip(),
        encoding="utf-8",
    )
    compile_params = {
        "width": 2,
        "height": 1,
        "rows_per_pe": 2,
        "hidden_per_pe": 2,
        "tokens_per_chunk": 2,
    }
    operation_graph = {
        "schemaVersion": 1,
        "artifactKind": "csl_operation_graph",
        "graphId": "embed-rpc-launch",
        "orchestrationMode": "memcpy",
        "executionPattern": "rpc_launch",
        "sdkVersionFloor": "2.10.0",
        "compile": {
            "arch": "wse3",
            "fabricDims": [9, 3],
            "fabricOffsets": [4, 1],
            "peGrid": {"width": 2, "height": 1},
            "channels": 1,
            "memcpy": True,
            "params": [
                {"name": "width", "type": "i16", "value": 2},
                {"name": "height", "type": "i16", "value": 1},
            ],
            "importPaths": [],
            "outputDir": "compile/compiled/embed",
            "compileTargets": [
                {
                    "name": "embed",
                    "layout": "compile/embed/layout.csl",
                    "peProgram": "compile/embed/pe_program.csl",
                    "compileParams": compile_params,
                }
            ],
        },
        "exportedSymbols": [
            {"name": "indices", "type": "[*]u32", "mutable": True, "kind": "device_variable"},
            {"name": "table", "type": "[*]f32", "mutable": True, "kind": "device_variable"},
            {"name": "output", "type": "[*]f32", "mutable": True, "kind": "device_variable"},
            {"name": "compute", "type": "fn()void", "mutable": False, "kind": "device_function"},
        ],
        "kernelPatterns": [{"targetName": "embed", "pattern": "gather", "count": 1}],
        "operations": [
            {
                "operationId": "h2d-indices",
                "kind": "memcpy_h2d",
                "targetKind": "device_symbol",
                "deviceSymbol": "indices",
                "roi": {"x": 0, "y": 0, "width": 2, "height": 1},
                "elementsPerPE": 2,
                "dataType": "MEMCPY_32BIT",
                "order": "ROW_MAJOR",
                "streaming": False,
                "nonblock": True,
            },
            {
                "operationId": "h2d-table",
                "kind": "memcpy_h2d",
                "targetKind": "device_symbol",
                "deviceSymbol": "table",
                "roi": {"x": 0, "y": 0, "width": 2, "height": 1},
                "elementsPerPE": 4,
                "dataType": "MEMCPY_32BIT",
                "order": "ROW_MAJOR",
                "streaming": False,
                "nonblock": True,
            },
            {
                "operationId": "launch-compute",
                "kind": "launch",
                "functionName": "compute",
                "args": [],
                "nonblock": False,
                "unblockCheckpointRequired": True,
            },
            {
                "operationId": "d2h-output",
                "kind": "memcpy_d2h",
                "targetKind": "device_symbol",
                "deviceSymbol": "output",
                "roi": {"x": 0, "y": 0, "width": 2, "height": 1},
                "elementsPerPE": 4,
                "dataType": "MEMCPY_32BIT",
                "order": "ROW_MAJOR",
                "streaming": False,
                "nonblock": False,
            },
        ],
    }
    simulator_plan = {
        "schemaVersion": 1,
        "artifactKind": "doe_wgsl_simulator_plan",
        "target": "wse3",
        "inputs": {
            "hostPlanArtifactPath": "host-plan.json",
            "runtimeConfigPath": "runtime-config.json",
            "compileRootPath": "compile",
            "compileTargets": [
                {
                    "name": "embed",
                    "layout": "embed/layout.csl",
                    "peProgram": "embed/pe_program.csl",
                    "compileParams": compile_params,
                }
            ],
        },
        "runtime": {"peGrid": {"width": 2, "height": 1}},
        "outputs": {"tracePath": "trace.json"},
    }
    driver_result = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_driver_result",
        "target": "wse3",
        "contract": "explicit_driver_outcome",
        "simulatorPlanPath": str(root / "simulator-plan.json"),
        "runtimeConfigPath": str(root / "runtime-config.json"),
        "compile": {
            "attempted": True,
            "status": "succeeded",
            "reason": "compiled",
            "targets": [{"name": "embed", "status": "succeeded"}],
        },
        "run": {
            "attempted": False,
            "status": "blocked",
            "reason": "compile_only_fixture",
            "tracePath": str(root / "trace.json"),
            "traceProduced": False,
        },
        "operationGraph": operation_graph,
    }
    _write_json(root / "host-plan.json", {"artifactKind": "doe_wgsl_host_plan"})
    _write_json(root / "runtime-config.json", {"schemaVersion": 1})
    _write_json(root / "simulator-plan.json", simulator_plan)
    _write_json(root / "driver-result.json", driver_result)


def _memcpy_op(kind: str, symbol: str, elements: int, width: int = 1, height: int = 1) -> dict:
    return {
        "operationId": f"{kind.removeprefix('memcpy_')}-{symbol}",
        "kind": kind,
        "targetKind": "device_symbol",
        "deviceSymbol": symbol,
        "roi": {"x": 0, "y": 0, "width": width, "height": height},
        "elementsPerPE": elements,
        "dataType": "MEMCPY_32BIT",
        "order": "ROW_MAJOR",
        "streaming": False,
        "nonblock": kind == "memcpy_h2d",
    }


def _seed_single_target_bundle(
    root: Path,
    *,
    name: str,
    pattern: str | None,
    pe_program: str,
    compile_params: dict,
    variables: list[tuple[str, str]],
    operations: list[dict],
    functions: tuple[str, ...] = ("compute",),
) -> None:
    compile_dir = root / "compile" / name
    compile_dir.mkdir(parents=True)
    layout_lines = [
        f'@export_name("{symbol}", {symbol}, true);\n'
        for symbol, _type in variables
    ]
    layout_lines.extend(
        f'@export_name("{function}", {function}, false);\n'
        for function in functions
    )
    (compile_dir / "layout.csl").write_text("".join(layout_lines), encoding="utf-8")
    (compile_dir / "pe_program.csl").write_text(pe_program, encoding="utf-8")

    width = int(compile_params.get("width", 1))
    height = int(compile_params.get("height", 1))
    exported = [
        {"name": symbol, "type": _type, "mutable": True, "kind": "device_variable"}
        for symbol, _type in variables
    ]
    exported.extend(
        {"name": function, "type": "fn()void", "mutable": False, "kind": "device_function"}
        for function in functions
    )
    operation_graph = {
        "schemaVersion": 1,
        "artifactKind": "csl_operation_graph",
        "graphId": f"{name}-rpc-launch",
        "orchestrationMode": "memcpy",
        "executionPattern": "rpc_launch",
        "sdkVersionFloor": "2.10.0",
        "compile": {
            "arch": "wse3",
            "fabricDims": [width + 8, height + 2],
            "fabricOffsets": [4, 1],
            "peGrid": {"width": width, "height": height},
            "channels": 1,
            "memcpy": True,
            "params": [
                {"name": "width", "type": "i16", "value": width},
                {"name": "height", "type": "i16", "value": height},
            ],
            "importPaths": [],
            "outputDir": f"compile/compiled/{name}",
            "compileTargets": [
                {
                    "name": name,
                    "layout": f"compile/{name}/layout.csl",
                    "peProgram": f"compile/{name}/pe_program.csl",
                    "compileParams": compile_params,
                }
            ],
        },
        "exportedSymbols": exported,
        "operations": operations,
    }
    if pattern is not None:
        operation_graph["kernelPatterns"] = [
            {"targetName": name, "pattern": pattern, "count": 1}
        ]
    simulator_plan = {
        "schemaVersion": 1,
        "artifactKind": "doe_wgsl_simulator_plan",
        "target": "wse3",
        "inputs": {
            "hostPlanArtifactPath": "host-plan.json",
            "runtimeConfigPath": "runtime-config.json",
            "compileRootPath": "compile",
            "compileTargets": [
                {
                    "name": name,
                    "layout": f"{name}/layout.csl",
                    "peProgram": f"{name}/pe_program.csl",
                    "compileParams": compile_params,
                }
            ],
        },
        "runtime": {"peGrid": {"width": width, "height": height}},
        "outputs": {"tracePath": "trace.json"},
    }
    driver_result = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_driver_result",
        "target": "wse3",
        "contract": "explicit_driver_outcome",
        "simulatorPlanPath": str(root / "simulator-plan.json"),
        "runtimeConfigPath": str(root / "runtime-config.json"),
        "compile": {
            "attempted": True,
            "status": "succeeded",
            "reason": "compiled",
            "targets": [{"name": name, "status": "succeeded"}],
        },
        "run": {
            "attempted": False,
            "status": "blocked",
            "reason": "compile_only_fixture",
            "tracePath": str(root / "trace.json"),
            "traceProduced": False,
        },
        "operationGraph": operation_graph,
    }
    _write_json(root / "host-plan.json", {"artifactKind": "doe_wgsl_host_plan"})
    _write_json(root / "runtime-config.json", {"schemaVersion": 1})
    _write_json(root / "simulator-plan.json", simulator_plan)
    _write_json(root / "driver-result.json", driver_result)


def _d2h_bytes(receipt: dict, operation_id: str) -> bytes:
    op = [
        item for item in receipt["execution"]["operations"]
        if item["operationId"] == operation_id
    ][0]
    return (REPO_ROOT / op["outputFile"]["path"]).read_bytes()


def _build_input(root: Path, fixtures: list[tuple[str, Path]]) -> Path:
    payload = build_emulator_input(bundle_root=root, fixture_files=fixtures)
    validate_payload(payload, INPUT_SCHEMA)
    input_path = root / "csl-webgpu-emulator-input.json"
    _write_json(input_path, payload)
    return input_path


def _run_emulator(
    input_path: Path,
    out_path: Path,
    d2h_out_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        "node",
        str(EMULATOR),
        "--input",
        str(input_path),
        "--out",
        str(out_path),
        "--backend",
        "cpu",
    ]
    if d2h_out_dir is not None:
        command.extend(["--d2h-out-dir", str(d2h_out_dir)])
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class CslWebgpuEmulatorTests(unittest.TestCase):
    def test_cpu_backend_executes_gather_pe_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_gather_bundle(root)
            _write_u32(root / "indices.bin", [0, 3, 0, 3])
            _write_f32(root / "table.bin", [10.0, 11.0, 20.0, 21.0, 30.0, 31.0, 40.0, 41.0])
            expected = struct.pack("<8f", 10.0, 11.0, 0.0, 0.0, 0.0, 0.0, 40.0, 41.0)
            input_path = _build_input(
                root,
                [("indices", root / "indices.bin"), ("table", root / "table.bin")],
            )
            out_path = root / "result.json"

            result = _run_emulator(input_path, out_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            d2h = [
                op for op in receipt["execution"]["operations"]
                if op["operationId"] == "d2h-output"
            ][0]
            self.assertEqual(d2h["sha256"], "sha256:" + sha256(expected).hexdigest())
            self.assertEqual(
                receipt["sourceInspection"]["compileTargets"][0]["semantic"],
                "gather",
            )

    def test_cpu_backend_executes_residual_add_and_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_residual_bundle(root)
            input_bytes = _write_f32(root / "input.bin", [1.0, 2.0, 3.0, 4.0])
            residual_bytes = _write_f32(root / "residual.bin", [10.0, 20.0, 30.0, 40.0])
            expected = struct.pack("<4f", 11.0, 22.0, 33.0, 44.0)
            input_path = _build_input(
                root,
                [("input", root / "input.bin"), ("residual", root / "residual.bin")],
            )
            out_path = root / "result.json"
            d2h_dir = root / "d2h"

            result = _run_emulator(input_path, out_path, d2h_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(receipt)
            self.assertEqual(receipt["status"], "succeeded")
            self.assertEqual(receipt["executedBackend"], "cpu")
            self.assertEqual(receipt["unsupported"], [])
            d2h = [
                op for op in receipt["execution"]["operations"]
                if op["operationId"] == "d2h-output"
            ][0]
            self.assertEqual(d2h["sha256"], "sha256:" + sha256(expected).hexdigest())
            self.assertEqual(d2h["outputFile"]["sha256"], d2h["sha256"])
            self.assertEqual(
                (REPO_ROOT / d2h["outputFile"]["path"]).read_bytes(),
                expected,
            )
            self.assertEqual(
                receipt["execution"]["operations"][0]["sha256"],
                "sha256:" + sha256(input_bytes).hexdigest(),
            )
            self.assertEqual(
                receipt["execution"]["operations"][1]["sha256"],
                "sha256:" + sha256(residual_bytes).hexdigest(),
            )

    def test_missing_h2d_fixture_blocks_without_fabricating_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_residual_bundle(root)
            _write_f32(root / "input.bin", [1.0, 2.0, 3.0, 4.0])
            input_path = _build_input(root, [("input", root / "input.bin")])
            out_path = root / "result.json"

            result = _run_emulator(input_path, out_path)

            self.assertEqual(result.returncode, 1)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(receipt)
            self.assertEqual(receipt["status"], "blocked")
            self.assertEqual(receipt["unsupported"][0]["code"], "fixture_missing")
            self.assertEqual(
                receipt["execution"]["operations"][1]["operationId"],
                "h2d-residual",
            )

    def test_unsupported_launch_semantic_blocks_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_residual_bundle(root)
            driver_result_path = root / "driver-result.json"
            driver_result = json.loads(driver_result_path.read_text(encoding="utf-8"))
            driver_result["operationGraph"].pop("kernelPatterns")
            _write_json(driver_result_path, driver_result)
            pe_program = root / "compile" / "residual" / "pe_program.csl"
            pe_program.write_text(
                """
param memcpy_params;
const sys_mod = @import_module("<memcpy/memcpy>", memcpy_params);
fn compute() void {
    var x: f32 = 1.0;
    x = x * 2.0;
    sys_mod.unblock_cmd_stream();
}
comptime {
    @export_symbol(compute);
}
""".lstrip(),
                encoding="utf-8",
            )
            _write_f32(root / "input.bin", [1.0, 2.0, 3.0, 4.0])
            _write_f32(root / "residual.bin", [10.0, 20.0, 30.0, 40.0])
            input_path = _build_input(
                root,
                [("input", root / "input.bin"), ("residual", root / "residual.bin")],
            )
            out_path = root / "result.json"

            result = _run_emulator(input_path, out_path)

            self.assertEqual(result.returncode, 1)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "blocked")
            self.assertEqual(
                receipt["unsupported"][0]["code"],
                "unsupported_csl_launch_semantic",
            )

    def test_cpu_backend_executes_elementwise_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_residual_bundle(root)
            driver_result_path = root / "driver-result.json"
            driver_result = json.loads(driver_result_path.read_text(encoding="utf-8"))
            graph = driver_result["operationGraph"]
            graph["kernelPatterns"] = [
                {"targetName": "residual", "pattern": "element_wise", "count": 1}
            ]
            graph["exportedSymbols"] = [
                item for item in graph["exportedSymbols"]
                if item["name"] != "residual"
            ]
            graph["operations"] = [
                item for item in graph["operations"]
                if item.get("deviceSymbol") != "residual"
            ]
            _write_json(driver_result_path, driver_result)
            pe_program = root / "compile" / "residual" / "pe_program.csl"
            pe_program.write_text(
                """
param memcpy_params;
param chunk_size: i16 = 4;
const sys_mod = @import_module("<memcpy/memcpy>", memcpy_params);
var input: [chunk_size]f32 = @zeros([chunk_size]f32);
var output: [chunk_size]f32 = @zeros([chunk_size]f32);
var input_ptr: [*]f32 = &input;
var output_ptr: [*]f32 = &output;
fn compute() void {
    for (@range(i16, chunk_size)) |_idx| {
        const idx = @as(u32, _idx);
        output[idx] = input[idx] * 1.0;
    }
    sys_mod.unblock_cmd_stream();
}
comptime {
    @export_symbol(input_ptr, "input");
    @export_symbol(output_ptr, "output");
    @export_symbol(compute);
}
""".lstrip(),
                encoding="utf-8",
            )
            input_bytes = _write_f32(root / "input.bin", [5.0, 6.0, 7.0, 8.0])
            input_path = _build_input(root, [("input", root / "input.bin")])
            out_path = root / "result.json"

            result = _run_emulator(input_path, out_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            d2h = [
                op for op in receipt["execution"]["operations"]
                if op["operationId"] == "d2h-output"
            ][0]
            self.assertEqual(d2h["sha256"], "sha256:" + sha256(input_bytes).hexdigest())
            self.assertEqual(
                receipt["sourceInspection"]["compileTargets"][0]["semantic"],
                "elementwise_identity",
            )

    def test_cpu_backend_executes_tiled_matmul(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_single_target_bundle(
                root,
                name="tiled",
                pattern="tiled_matmul",
                pe_program="// PE program: SUMMA tiled matmul\nfn compute() void {}\n",
                compile_params={"width": 2, "height": 2, "P": 2, "Mt": 1, "Kt": 1, "Nt": 1},
                variables=[("a", "[*]f32"), ("b", "[*]f32"), ("c", "[*]f32")],
                operations=[
                    _memcpy_op("memcpy_h2d", "a", 1, 2, 2),
                    _memcpy_op("memcpy_h2d", "b", 1, 2, 2),
                    _memcpy_op("memcpy_h2d", "c", 1, 2, 2),
                    {
                        "operationId": "launch-compute",
                        "kind": "launch",
                        "functionName": "compute",
                        "args": [],
                        "nonblock": False,
                        "unblockCheckpointRequired": True,
                    },
                    _memcpy_op("memcpy_d2h", "c", 1, 2, 2),
                ],
            )
            _write_f32(root / "a.bin", [1.0, 2.0, 3.0, 4.0])
            _write_f32(root / "b.bin", [10.0, 20.0, 30.0, 40.0])
            _write_f32(root / "c.bin", [0.0, 0.0, 0.0, 0.0])
            input_path = _build_input(
                root,
                [("a", root / "a.bin"), ("b", root / "b.bin"), ("c", root / "c.bin")],
            )
            out_path = root / "result.json"

            result = _run_emulator(input_path, out_path, root / "d2h")

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(
                _d2h_bytes(receipt, "d2h-c"),
                struct.pack("<4f", 70.0, 100.0, 150.0, 220.0),
            )
            self.assertEqual(receipt["sourceInspection"]["compileTargets"][0]["semantic"], "tiled_matmul")

    def test_cpu_backend_executes_rope_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_single_target_bundle(
                root,
                name="rope",
                pattern="rope",
                pe_program="// PE program: rotary position embeddings\nfn compute() void {}\n",
                compile_params={"width": 1, "height": 1, "head_dim": 4, "num_pairs": 2},
                variables=[
                    ("input", "[*]f32"),
                    ("cos_table", "[*]f32"),
                    ("sin_table", "[*]f32"),
                ],
                operations=[
                    _memcpy_op("memcpy_h2d", "input", 4),
                    _memcpy_op("memcpy_h2d", "cos_table", 2),
                    _memcpy_op("memcpy_h2d", "sin_table", 2),
                    {
                        "operationId": "launch-compute",
                        "kind": "launch",
                        "functionName": "compute",
                        "args": [],
                        "nonblock": False,
                        "unblockCheckpointRequired": True,
                    },
                    _memcpy_op("memcpy_d2h", "input", 4),
                ],
            )
            _write_f32(root / "input.bin", [1.0, 2.0, 3.0, 4.0])
            _write_f32(root / "cos.bin", [0.0, 1.0])
            _write_f32(root / "sin.bin", [1.0, 0.0])
            input_path = _build_input(
                root,
                [
                    ("input", root / "input.bin"),
                    ("cos_table", root / "cos.bin"),
                    ("sin_table", root / "sin.bin"),
                ],
            )
            out_path = root / "result.json"

            result = _run_emulator(input_path, out_path, root / "d2h")

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(_d2h_bytes(receipt, "d2h-input"), struct.pack("<4f", -2.0, 1.0, 3.0, 4.0))

    def test_cpu_backend_executes_attention_tiled_compute_and_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            launch_compute = {
                "operationId": "launch-compute",
                "kind": "launch",
                "functionName": "compute",
                "args": [],
                "nonblock": False,
                "unblockCheckpointRequired": True,
            }
            launch_finalize = dict(launch_compute, operationId="launch-finalize", functionName="finalize")
            _seed_single_target_bundle(
                root,
                name="attn_small",
                pattern="attention_tiled",
                pe_program="// PE program: tiled Flash Attention\nfn compute() void {}\nfn finalize() void {}\n",
                compile_params={
                    "width": 1,
                    "height": 1,
                    "head_dim": 2,
                    "q_len": 1,
                    "q_len_per_pe": 1,
                    "block_size": 2,
                    "scale": 1,
                },
                variables=[
                    ("query", "[*]f32"),
                    ("key", "[*]f32"),
                    ("val", "[*]f32"),
                    ("output", "[*]f32"),
                ],
                operations=[
                    _memcpy_op("memcpy_h2d", "query", 2),
                    _memcpy_op("memcpy_h2d", "key", 4),
                    _memcpy_op("memcpy_h2d", "val", 4),
                    _memcpy_op("memcpy_h2d", "output", 2),
                    launch_compute,
                    launch_finalize,
                    _memcpy_op("memcpy_d2h", "output", 2),
                ],
                functions=("compute", "finalize"),
            )
            _write_f32(root / "query.bin", [1.0, 0.0])
            _write_f32(root / "key.bin", [1.0, 0.0, 0.0, 1.0])
            _write_f32(root / "val.bin", [10.0, 11.0, 20.0, 21.0])
            _write_f32(root / "output.bin", [0.0, 0.0])
            input_path = _build_input(
                root,
                [
                    ("query", root / "query.bin"),
                    ("key", root / "key.bin"),
                    ("val", root / "val.bin"),
                    ("output", root / "output.bin"),
                ],
            )
            out_path = root / "result.json"
            weight = math.exp(-1.0)
            expected = struct.pack(
                "<2f",
                (10.0 + weight * 20.0) / (1.0 + weight),
                (11.0 + weight * 21.0) / (1.0 + weight),
            )

            result = _run_emulator(input_path, out_path, root / "d2h")

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            actual_values = struct.unpack("<2f", _d2h_bytes(receipt, "d2h-output"))
            expected_values = struct.unpack("<2f", expected)
            for actual, expected_value in zip(actual_values, expected_values):
                self.assertAlmostEqual(actual, expected_value, places=5)
            self.assertEqual(
                sorted(item["name"] for item in receipt["execution"]["state"]),
                ["attn_small:l_state", "attn_small:m_state"],
            )

    def test_cpu_backend_executes_attention_decode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_single_target_bundle(
                root,
                name="attn_decode",
                pattern="attention_decode",
                pe_program="// PE program: decode attention\nfn compute() void {}\n",
                compile_params={"width": 1, "height": 1, "head_dim": 2, "kv_chunk": 2, "scale": 1},
                variables=[
                    ("query", "[*]f32"),
                    ("key", "[*]f32"),
                    ("val", "[*]f32"),
                    ("output", "[*]f32"),
                    ("position", "[*]u32"),
                    ("sliding_window", "[*]u32"),
                ],
                operations=[
                    _memcpy_op("memcpy_h2d", "query", 2),
                    _memcpy_op("memcpy_h2d", "key", 4),
                    _memcpy_op("memcpy_h2d", "val", 4),
                    _memcpy_op("memcpy_h2d", "output", 2),
                    _memcpy_op("memcpy_h2d", "position", 1),
                    _memcpy_op("memcpy_h2d", "sliding_window", 1),
                    {
                        "operationId": "launch-compute",
                        "kind": "launch",
                        "functionName": "compute",
                        "args": [],
                        "nonblock": False,
                        "unblockCheckpointRequired": True,
                    },
                    _memcpy_op("memcpy_d2h", "output", 2),
                ],
            )
            _write_f32(root / "query.bin", [1.0, 0.0])
            _write_f32(root / "key.bin", [1.0, 0.0, 0.0, 1.0])
            _write_f32(root / "val.bin", [10.0, 11.0, 20.0, 21.0])
            _write_f32(root / "output.bin", [0.0, 0.0])
            _write_u32(root / "position.bin", [1])
            _write_u32(root / "sliding.bin", [0])
            input_path = _build_input(
                root,
                [
                    ("query", root / "query.bin"),
                    ("key", root / "key.bin"),
                    ("val", root / "val.bin"),
                    ("output", root / "output.bin"),
                    ("position", root / "position.bin"),
                    ("sliding_window", root / "sliding.bin"),
                ],
            )
            out_path = root / "result.json"
            weight = math.exp(-1.0)
            expected = struct.pack(
                "<2f",
                (10.0 + weight * 20.0) / (1.0 + weight),
                (11.0 + weight * 21.0) / (1.0 + weight),
            )

            result = _run_emulator(input_path, out_path, root / "d2h")

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            actual_values = struct.unpack("<2f", _d2h_bytes(receipt, "d2h-output"))
            expected_values = struct.unpack("<2f", expected)
            for actual, expected_value in zip(actual_values, expected_values):
                self.assertAlmostEqual(actual, expected_value, places=6)

    def test_cpu_backend_executes_kv_write_and_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_single_target_bundle(
                root,
                name="kv_write",
                pattern=None,
                pe_program=(
                    "var key_proj: [head_dim]f32 = @zeros([head_dim]f32);\n"
                    "var val_proj: [head_dim]f32 = @zeros([head_dim]f32);\n"
                    "var key_cache: [max_seq_len * head_dim]f32 = @zeros([max_seq_len * head_dim]f32);\n"
                    "var val_cache: [max_seq_len * head_dim]f32 = @zeros([max_seq_len * head_dim]f32);\n"
                    "fn compute() void {}\n"
                ),
                compile_params={"width": 1, "height": 1, "head_dim": 2, "max_seq_len": 3},
                variables=[
                    ("key_proj", "[*]f32"),
                    ("val_proj", "[*]f32"),
                    ("key_cache", "[*]f32"),
                    ("val_cache", "[*]f32"),
                    ("position", "[*]u32"),
                ],
                operations=[
                    _memcpy_op("memcpy_h2d", "key_proj", 2),
                    _memcpy_op("memcpy_h2d", "val_proj", 2),
                    _memcpy_op("memcpy_h2d", "key_cache", 6),
                    _memcpy_op("memcpy_h2d", "val_cache", 6),
                    _memcpy_op("memcpy_h2d", "position", 1),
                    {
                        "operationId": "launch-compute",
                        "kind": "launch",
                        "functionName": "compute",
                        "args": [],
                        "nonblock": False,
                        "unblockCheckpointRequired": True,
                    },
                    _memcpy_op("memcpy_d2h", "key_cache", 6),
                    _memcpy_op("memcpy_d2h", "val_cache", 6),
                ],
            )
            _write_f32(root / "key_proj.bin", [5.0, 6.0])
            _write_f32(root / "val_proj.bin", [7.0, 8.0])
            _write_f32(root / "key_cache.bin", [0.0] * 6)
            _write_f32(root / "val_cache.bin", [0.0] * 6)
            _write_u32(root / "position.bin", [1])
            input_path = _build_input(
                root,
                [
                    ("key_proj", root / "key_proj.bin"),
                    ("val_proj", root / "val_proj.bin"),
                    ("key_cache", root / "key_cache.bin"),
                    ("val_cache", root / "val_cache.bin"),
                    ("position", root / "position.bin"),
                ],
            )
            out_path = root / "result.json"

            result = _run_emulator(input_path, out_path, root / "d2h")

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(_d2h_bytes(receipt, "d2h-key_cache"), struct.pack("<6f", 0.0, 0.0, 5.0, 6.0, 0.0, 0.0))
            self.assertEqual(_d2h_bytes(receipt, "d2h-val_cache"), struct.pack("<6f", 0.0, 0.0, 7.0, 8.0, 0.0, 0.0))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_single_target_bundle(
                root,
                name="sample",
                pattern="sample",
                pe_program="// PE program: token sampling\nvar output_token: [1]u32 = @zeros([1]u32);\nfn compute() void {}\n",
                compile_params={"width": 2, "height": 1, "chunk_size": 3},
                variables=[("logits", "[*]f32"), ("tokens", "[*]u32")],
                operations=[
                    _memcpy_op("memcpy_h2d", "logits", 3, 2, 1),
                    _memcpy_op("memcpy_h2d", "tokens", 1, 2, 1),
                    {
                        "operationId": "launch-compute",
                        "kind": "launch",
                        "functionName": "compute",
                        "args": [],
                        "nonblock": False,
                        "unblockCheckpointRequired": True,
                    },
                    _memcpy_op("memcpy_d2h", "tokens", 1, 2, 1),
                ],
            )
            _write_f32(root / "logits.bin", [0.1, 0.4, 0.3, 0.5, 0.2, 0.6])
            _write_u32(root / "tokens.bin", [0, 0])
            input_path = _build_input(
                root,
                [("logits", root / "logits.bin"), ("tokens", root / "tokens.bin")],
            )
            out_path = root / "result.json"

            result = _run_emulator(input_path, out_path, root / "d2h")

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(_d2h_bytes(receipt, "d2h-tokens"), struct.pack("<2I", 0, 5))

    def test_cpu_backend_executes_fused_gemv_dequant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_single_target_bundle(
                root,
                name="gemv",
                pattern="fused_gemv_dequant",
                pe_program="// PE program: fused GEMV + Q4K dequant\nfn compute() void {}\n",
                compile_params={
                    "width": 2,
                    "height": 1,
                    "out_dim_per_pe": 1,
                    "in_dim_per_pe": 256,
                    "num_blocks_per_row": 1,
                },
                variables=[
                    ("activation", "[*]f32"),
                    ("weight", "[*]u8"),
                    ("output", "[*]f32"),
                ],
                operations=[
                    _memcpy_op("memcpy_h2d", "activation", 256, 2, 1),
                    _memcpy_op("memcpy_h2d", "weight", 36, 2, 1),
                    _memcpy_op("memcpy_h2d", "output", 1, 2, 1),
                    {
                        "operationId": "launch-compute",
                        "kind": "launch",
                        "functionName": "compute",
                        "args": [],
                        "nonblock": False,
                        "unblockCheckpointRequired": True,
                    },
                    _memcpy_op("memcpy_d2h", "output", 1, 2, 1),
                ],
            )
            _write_f32(root / "activation.bin", [1.0] * 512)
            block = bytearray(144)
            block[0] = 0x00
            block[1] = 0x3c
            block[16] = 0x21
            (root / "weight.bin").write_bytes(bytes(block) + bytes(block))
            _write_f32(root / "output.bin", [0.0, 0.0])
            input_path = _build_input(
                root,
                [
                    ("activation", root / "activation.bin"),
                    ("weight", root / "weight.bin"),
                    ("output", root / "output.bin"),
                ],
            )
            out_path = root / "result.json"

            result = _run_emulator(input_path, out_path, root / "d2h")

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(_d2h_bytes(receipt, "d2h-output"), struct.pack("<2f", 3.0, 6.0))


if __name__ == "__main__":
    unittest.main()
