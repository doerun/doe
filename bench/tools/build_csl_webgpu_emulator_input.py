#!/usr/bin/env python3
"""Build the source-preserving input contract for a CSL WebGPU emulator."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = "config/csl-webgpu-emulator-input.schema.json"
OPERATION_GRAPH_SCHEMA = "config/csl-operation-graph.schema.json"
GENERATED_BY = "bench/tools/build_csl_webgpu_emulator_input.py"
SUPPORTED_SUBSET = (
    "layout_exports",
    "pe_program_source",
    "compile_params",
    "memcpy_h2d",
    "launch",
    "memcpy_d2h",
    "rpc_launch",
    "tiled_matmul",
    "rope",
    "attention_tiled",
    "attention_decode",
    "fused_gemv_dequant",
    "kv_write",
    "sample",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--driver-result", default="")
    parser.add_argument("--operation-graph", default="")
    parser.add_argument("--simulator-plan", default="")
    parser.add_argument("--host-plan", default="")
    parser.add_argument("--runtime-config", default="")
    parser.add_argument("--program-bundle", default="")
    parser.add_argument("--rdrr-manifest", default="")
    parser.add_argument("--reference-transcript", default="")
    parser.add_argument(
        "--fixture",
        action="append",
        default=[],
        help="Bind a raw fixture file as DEVICE_SYMBOL=PATH for H2D inputs.",
    )
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    return parser.parse_args()


def resolve(raw: str | Path, *, base: Path | None = None) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    if base is not None:
        return (base / path).resolve()
    return (REPO_ROOT / path).resolve()


def repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return payload


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def file_ref(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"required file is missing: {path}")
    return {
        "path": repo_relative(path),
        "sha256": sha256_file(path),
    }


def optional_file_ref(path: Path) -> dict[str, str] | None:
    return file_ref(path) if path.is_file() else None


def find_default_driver_result(bundle_root: Path, simulator_plan: dict[str, Any]) -> Path | None:
    candidates = [
        bundle_root / "driver-result.json",
        bundle_root / "trace.json.driver-result.json",
    ]
    trace_path = (
        (simulator_plan.get("outputs") or {}).get("tracePath")
        if isinstance(simulator_plan.get("outputs"), dict)
        else None
    )
    if isinstance(trace_path, str) and trace_path:
        resolved_trace = resolve(trace_path, base=bundle_root)
        candidates.append(Path(str(resolved_trace) + ".driver-result.json"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def compile_targets_by_name(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not payload:
        return {}
    targets = (((payload.get("compile") or {}).get("targets")) or [])
    if not isinstance(targets, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict):
            continue
        name = target.get("name")
        if isinstance(name, str) and name:
            out[name] = target
    return out


def operation_compile_targets_by_name(operation_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    compile_section = operation_graph.get("compile") if isinstance(operation_graph, dict) else None
    targets = (compile_section or {}).get("compileTargets") if isinstance(compile_section, dict) else None
    if not isinstance(targets, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict):
            continue
        name = target.get("name")
        if isinstance(name, str) and name:
            out[name] = target
    return out


def resolve_compile_source(compile_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    if path.parts and path.parts[0] == compile_root.name:
        return resolve(path, base=compile_root.parent)
    return resolve(path, base=compile_root)


def build_compile_targets(
    *,
    compile_root: Path,
    simulator_plan: dict[str, Any],
    driver_result: dict[str, Any] | None,
    operation_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    inputs = simulator_plan.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("simulator plan missing inputs object")
    sim_targets = inputs.get("compileTargets")
    if not isinstance(sim_targets, list) or not sim_targets:
        raise ValueError("simulator plan missing inputs.compileTargets")

    driver_targets = compile_targets_by_name(driver_result)
    op_targets = operation_compile_targets_by_name(operation_graph)
    entries: list[dict[str, Any]] = []
    for raw_target in sim_targets:
        if not isinstance(raw_target, dict):
            raise ValueError("simulator plan compile target must be an object")
        name = raw_target.get("name")
        layout = raw_target.get("layout")
        pe_program = raw_target.get("peProgram")
        if not isinstance(name, str) or not name:
            raise ValueError("simulator plan compile target missing name")
        if not isinstance(layout, str) or not layout:
            raise ValueError(f"compile target {name} missing layout")
        if not isinstance(pe_program, str) or not pe_program:
            raise ValueError(f"compile target {name} missing peProgram")

        layout_path = resolve_compile_source(compile_root, layout)
        pe_program_path = resolve_compile_source(compile_root, pe_program)
        entry: dict[str, Any] = {
            "name": name,
            "layout": file_ref(layout_path),
            "peProgram": file_ref(pe_program_path),
        }

        layout_metadata = optional_file_ref(layout_path.parent / "layout.metadata.json")
        if layout_metadata is not None:
            entry["layoutMetadata"] = layout_metadata
        pe_metadata = optional_file_ref(pe_program_path.parent / "pe_program.metadata.json")
        if pe_metadata is not None:
            entry["peProgramMetadata"] = pe_metadata

        compile_params = raw_target.get("compileParams")
        op_params = (op_targets.get(name) or {}).get("compileParams")
        if isinstance(compile_params, dict):
            entry["compileParams"] = compile_params
        elif isinstance(op_params, dict):
            entry["compileParams"] = op_params

        metadata = raw_target.get("metadata")
        if isinstance(metadata, dict):
            entry["metadata"] = metadata

        source_wgsl = raw_target.get("sourceWgslPath")
        if isinstance(source_wgsl, str) and source_wgsl:
            entry["sourceWgslPath"] = source_wgsl

        driver_status = (driver_targets.get(name) or {}).get("status")
        entry["driverStatus"] = driver_status if isinstance(driver_status, str) else "not_run"
        entries.append(entry)
    return entries


def source_refs(
    *,
    bundle_root: Path,
    compile_root: Path,
    simulator_plan_path: Path,
    host_plan_path: Path,
    runtime_config_path: Path,
    driver_result_path: Path | None,
    operation_graph_path: Path | None,
    operation_graph_source: str,
) -> dict[str, Any]:
    sources: dict[str, Any] = {
        "bundleRoot": {"path": repo_relative(bundle_root)},
        "compileRoot": {"path": repo_relative(compile_root)},
        "simulatorPlan": file_ref(simulator_plan_path),
        "hostPlan": file_ref(host_plan_path),
        "runtimeConfig": file_ref(runtime_config_path),
        "operationGraphSource": operation_graph_source,
    }
    if driver_result_path is not None:
        sources["driverResult"] = file_ref(driver_result_path)
    if operation_graph_path is not None:
        sources["operationGraphFile"] = file_ref(operation_graph_path)
    return sources


def host_inputs(
    *,
    program_bundle: Path | None,
    rdrr_manifest: Path | None,
    reference_transcript: Path | None,
    fixture_files: list[tuple[str, Path]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {"mode": "unbound", "notes": []}
    if fixture_files and any(
        item is not None
        for item in (program_bundle, rdrr_manifest, reference_transcript)
    ):
        raise ValueError("fixture files cannot be combined with Doppler/RDRR inputs")
    if fixture_files:
        payload["mode"] = "fixture_files"
        payload["fixtureFiles"] = []
        for device_symbol, path in fixture_files:
            ref: dict[str, Any] = file_ref(path)
            ref["deviceSymbol"] = device_symbol
            ref["byteLength"] = path.stat().st_size
            payload["fixtureFiles"].append(ref)
        payload["notes"].append(
            "Raw fixture files provide emulator H2D payloads by device symbol."
        )
        return payload

    if program_bundle is not None:
        payload["programBundle"] = file_ref(program_bundle)
    if rdrr_manifest is not None:
        payload["rdrrManifest"] = file_ref(rdrr_manifest)
    if reference_transcript is not None:
        payload["referenceTranscript"] = file_ref(reference_transcript)
    if any(
        key in payload
        for key in ("programBundle", "rdrrManifest", "referenceTranscript")
    ):
        payload["mode"] = "doppler_rdrr"
        payload["notes"].append(
            "Weights and request inputs are bound by Doppler/RDRR artifacts; "
            "the emulator should materialize per-kernel buffers from those sources."
        )
    else:
        payload["notes"].append(
            "No Doppler Program Bundle, RDRR manifest, or reference transcript "
            "was provided."
        )
    return payload


def build_emulator_input(
    *,
    bundle_root: Path,
    simulator_plan_path: Path | None = None,
    host_plan_path: Path | None = None,
    runtime_config_path: Path | None = None,
    driver_result_path: Path | None = None,
    operation_graph_path: Path | None = None,
    program_bundle: Path | None = None,
    rdrr_manifest: Path | None = None,
    reference_transcript: Path | None = None,
    fixture_files: list[tuple[str, Path]] | None = None,
) -> dict[str, Any]:
    simulator_plan_path = simulator_plan_path or (bundle_root / "simulator-plan.json")
    host_plan_path = host_plan_path or (bundle_root / "host-plan.json")
    runtime_config_path = runtime_config_path or (bundle_root / "runtime-config.json")
    simulator_plan = load_json_object(simulator_plan_path)

    driver_result: dict[str, Any] | None = None
    if driver_result_path is None and operation_graph_path is None:
        driver_result_path = find_default_driver_result(bundle_root, simulator_plan)
    if driver_result_path is not None:
        driver_result = load_json_object(driver_result_path)

    if operation_graph_path is not None:
        operation_graph = load_json_object(operation_graph_path)
        operation_graph_source = "operation_graph_file"
    elif driver_result is not None and isinstance(driver_result.get("operationGraph"), dict):
        operation_graph = driver_result["operationGraph"]
        operation_graph_source = "driver_result"
    else:
        raise ValueError(
            "operation graph is required: pass --operation-graph or a driver "
            "result containing operationGraph"
        )
    if operation_graph.get("artifactKind") != "csl_operation_graph":
        raise ValueError("operation graph artifactKind must be csl_operation_graph")

    inputs = simulator_plan.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("simulator plan missing inputs")
    compile_root_raw = inputs.get("compileRootPath")
    if not isinstance(compile_root_raw, str) or not compile_root_raw:
        raise ValueError("simulator plan missing inputs.compileRootPath")
    compile_root = resolve(compile_root_raw, base=bundle_root)

    payload = {
        "schemaVersion": 1,
        "artifactKind": "csl_webgpu_emulator_input",
        "contract": "csl_source_to_webgpu_emulator_input",
        "claimScope": "input_contract_only_not_execution",
        "emulator": {
            "targetSurface": "webgpu",
            "hostController": "cpu",
            "deviceCompute": "webgpu_compute_passes",
            "sourceMode": "csl_source_subset",
            "executionModel": "ordered_host_operations_from_csl_operation_graph",
            "supportedSubset": list(SUPPORTED_SUBSET),
        },
        "sources": source_refs(
            bundle_root=bundle_root,
            compile_root=compile_root,
            simulator_plan_path=simulator_plan_path,
            host_plan_path=host_plan_path,
            runtime_config_path=runtime_config_path,
            driver_result_path=driver_result_path,
            operation_graph_path=operation_graph_path,
            operation_graph_source=operation_graph_source,
        ),
        "compileTargets": build_compile_targets(
            compile_root=compile_root,
            simulator_plan=simulator_plan,
            driver_result=driver_result,
            operation_graph=operation_graph,
        ),
        "operationGraph": operation_graph,
        "operationGraphSha256": sha256_bytes(canonical_json_bytes(operation_graph)),
        "hostInputs": host_inputs(
            program_bundle=program_bundle,
            rdrr_manifest=rdrr_manifest,
            reference_transcript=reference_transcript,
            fixture_files=fixture_files or [],
        ),
        "validation": {
            "status": "input_ready",
            "generatedBy": GENERATED_BY,
            "blockers": [],
        },
    }
    return payload


def parse_fixture_specs(specs: list[str]) -> list[tuple[str, Path]]:
    fixture_files: list[tuple[str, Path]] = []
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"fixture must use DEVICE_SYMBOL=PATH: {spec}")
        device_symbol, raw_path = spec.split("=", 1)
        if not device_symbol or not raw_path:
            raise ValueError(f"fixture must use DEVICE_SYMBOL=PATH: {spec}")
        fixture_files.append((device_symbol, resolve(raw_path)))
    return fixture_files


def validate_payload(payload: dict[str, Any], schema_path: Path) -> None:
    schema = load_json_object(schema_path)
    jsonschema.Draft202012Validator(schema).validate(payload)
    operation_graph_schema = load_json_object(resolve(OPERATION_GRAPH_SCHEMA))
    jsonschema.Draft202012Validator(operation_graph_schema).validate(payload["operationGraph"])


def main() -> int:
    args = parse_args()
    bundle_root = resolve(args.bundle_root)
    payload = build_emulator_input(
        bundle_root=bundle_root,
        simulator_plan_path=resolve(args.simulator_plan) if args.simulator_plan else None,
        host_plan_path=resolve(args.host_plan) if args.host_plan else None,
        runtime_config_path=resolve(args.runtime_config) if args.runtime_config else None,
        driver_result_path=resolve(args.driver_result) if args.driver_result else None,
        operation_graph_path=resolve(args.operation_graph) if args.operation_graph else None,
        program_bundle=resolve(args.program_bundle) if args.program_bundle else None,
        rdrr_manifest=resolve(args.rdrr_manifest) if args.rdrr_manifest else None,
        reference_transcript=resolve(args.reference_transcript) if args.reference_transcript else None,
        fixture_files=parse_fixture_specs(args.fixture),
    )
    validate_payload(payload, resolve(args.schema))
    out_path = resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote CSL WebGPU emulator input: {repo_relative(out_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
