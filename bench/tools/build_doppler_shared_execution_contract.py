#!/usr/bin/env python3
"""Build the canonical Doe shared execution contract from Doppler artifacts."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.run_doe_csl_int4ple_transcript import (
    DEFAULT_HOSTPLAN_BUNDLE_ROOT,
    export_from_program_bundle,
    graph_path_from_export,
    load_json,
    manifest_tensor_spans,
    normalized_hostplan_execution,
    program_bundle_kv_cache_summary,
    reference_transcript_digest,
    rel,
    resolve,
    runtime_quant,
    schema_failures,
    sha256_file,
    sha256_json,
    source_program,
    strip_doppler_hash,
    tensor_name_for_weight_key,
    write_json,
)
DEFAULT_OUT = Path(
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-shared-execution-contract.json"
)
DEFAULT_SCHEMA = Path("config/doe-shared-execution-contract.schema.json")
DEFAULT_DOE_WEBGPU_HOST = "node"
DEFAULT_DOE_WEBGPU_PROVIDER_BY_HOST = {
    "node": "packages/doe-gpu/src/compute.js",
    "bun": "packages/doe-gpu/src/bun.js",
}
DEFAULT_DOE_WEBGPU_KERNEL_PATH_POLICY = {
    "mode": "capability-aware",
    "sourceScope": ["model", "manifest", "config"],
    "allowSources": ["model", "manifest", "config"],
    "onIncompatible": "remap",
}
SIM_RUNNER_PATH = (
    REPO_ROOT
    / "bench/runners/csl-runners/int4ple_compile_target_sim_runner.py"
)


def load_host_plan_phase_summary() -> Any:
    runner_dir = str(SIM_RUNNER_PATH.parent)
    if runner_dir not in sys.path:
        sys.path.insert(0, runner_dir)
    spec = importlib.util.spec_from_file_location(
        "int4ple_compile_target_sim_runner",
        SIM_RUNNER_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load simulator runner from {SIM_RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.host_plan_phase_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference-export",
        default=(
            "bench/out/doppler-reference/"
            "gemma-4-e2b-int4ple-production-final-logits/"
            "doppler_int4ple_reference_export.json"
        ),
        help="Existing Doppler reference export receipt to bind.",
    )
    parser.add_argument(
        "--program-bundle",
        default=None,
        help=(
            "Optional Doppler Program Bundle. When present, the tool refreshes "
            "the reference-export projection from the bundle."
        ),
    )
    parser.add_argument(
        "--hostplan-bundle-root",
        default=str(DEFAULT_HOSTPLAN_BUNDLE_ROOT),
        help=(
            "Optional existing HostPlan bundle root. When present and complete, "
            "launch-schedule linkage is attached."
        ),
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Schema used to validate the emitted contract.",
    )
    parser.add_argument(
        "--doe-webgpu-host",
        choices=("node", "bun"),
        default=DEFAULT_DOE_WEBGPU_HOST,
        help="Default Doe JS WebGPU host encoded into the shared contract.",
    )
    parser.add_argument(
        "--doe-webgpu-host-executable",
        default=None,
        help="Optional host executable override encoded into the shared contract.",
    )
    parser.add_argument(
        "--doe-webgpu-provider-module",
        default=None,
        help="Optional Doe provider module override encoded into the shared contract.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Output shared execution contract path.",
    )
    return parser.parse_args()


def hash_link(path: Path, source: str | None = None) -> dict[str, Any]:
    link: dict[str, Any] = {
        "path": rel(path),
        "sha256": sha256_file(path),
    }
    if source is not None:
        link["source"] = source
    return link


def prompt_input(export: dict[str, Any]) -> dict[str, Any]:
    prompt = export.get("prompt") or {}
    tokenized = export.get("tokenizedPrompt") or {}
    result = {
        "inputSetSha256": export.get("inputSetSha256", "pending"),
        "inputSetComponents": export.get("inputSetComponents") or {},
        "prompt": {
            "path": prompt.get("path", "pending"),
            "sha256": prompt.get("sha256", "pending"),
            "source": prompt.get("source", "unknown"),
        },
        "tokenizedPrompt": {
            "path": tokenized.get("path", "pending"),
            "sha256": tokenized.get("sha256", "pending"),
            "dtype": tokenized.get("dtype", "uint32"),
            "tokenCount": int(tokenized.get("tokenCount") or 0),
            "preview": tokenized.get("preview") or [],
        },
    }
    prompt_path = prompt.get("path")
    if (
        result["prompt"]["sha256"] == "pending"
        and isinstance(prompt_path, str)
        and prompt_path
    ):
        path = resolve(prompt_path)
        if path.is_file():
            result["prompt"]["sha256"] = sha256_file(path)
    tokenized_path = tokenized.get("path")
    if (
        result["tokenizedPrompt"]["sha256"] == "pending"
        and isinstance(tokenized_path, str)
        and tokenized_path
    ):
        path = resolve(tokenized_path)
        if path.is_file():
            result["tokenizedPrompt"]["sha256"] = sha256_file(path)
    return result


def decode_request(export: dict[str, Any]) -> dict[str, Any]:
    transcript = export.get("decodeTranscript") or {}
    return {
        "requestedDecodeSteps": int(transcript.get("requestedDecodeSteps") or 0),
        "expectedActualDecodeSteps": int(transcript.get("actualDecodeSteps") or 0),
        "expectedStopReason": transcript.get("stopReason", "pending"),
        "samplingSha256": strip_doppler_hash(
            (export.get("inputSetComponents") or {}).get("samplingSha256")
        ),
        "inputSetSha256": export.get("inputSetSha256", "pending"),
        "sampling": transcript.get("sampling") or {},
    }


def doe_webgpu_runtime(
    *,
    host: str,
    host_executable: str | None,
    provider_module: str | None,
) -> dict[str, Any]:
    return {
        "host": host,
        "hostExecutable": host_executable or host,
        "providerModule": (
            provider_module or DEFAULT_DOE_WEBGPU_PROVIDER_BY_HOST[host]
        ),
        "kernelPathPolicy": DEFAULT_DOE_WEBGPU_KERNEL_PATH_POLICY,
    }


def required_weight_keys(normalized_execution: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(step["weightsKey"])
            for step in normalized_execution.get("steps") or []
            if isinstance(step, dict) and isinstance(step.get("weightsKey"), str)
        }
    )


def simple_weight_mapping(
    *,
    weight_key: str,
    tensor_name: str,
    tensor: dict[str, Any],
    spans: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_dtype = str(tensor["dtype"])
    mapping = {
        "weightKey": weight_key,
        "tensorName": tensor_name,
        "role": str(tensor.get("role", "unknown")),
        "layout": str(tensor.get("layout", "unknown")),
        "dtype": manifest_dtype,
        "shape": [int(value) for value in tensor.get("shape", [])],
        "byteLength": int(tensor["size"]),
        "byteOffset": int(spans[0]["offset"]),
        "spans": spans,
        "quant": runtime_quant(manifest_dtype),
    }
    source_transform = tensor.get("sourceTransform")
    if isinstance(source_transform, dict):
        mapping["sourceTransform"] = source_transform
    return mapping


def weight_mappings(export: dict[str, Any], normalized_execution: dict[str, Any]) -> dict[str, Any]:
    manifest_path = resolve(export["manifestPath"])
    manifest_root = manifest_path.parent
    manifest = load_json(manifest_path)
    tensors = manifest.get("tensors") or {}
    shard_identities = {
        int(shard["index"]): shard for shard in export.get("shardIdentities") or []
        if isinstance(shard, dict) and "index" in shard
    }
    required_keys = required_weight_keys(normalized_execution)
    mappings: list[dict[str, Any]] = []
    missing: list[str] = []

    for weight_key in required_keys:
        try:
            tensor_name = tensor_name_for_weight_key(weight_key)
        except ValueError:
            missing.append(weight_key)
            continue
        tensor = tensors.get(tensor_name)
        if not isinstance(tensor, dict):
            missing.append(weight_key)
            continue
        spans = manifest_tensor_spans(tensor, shard_identities, manifest_root)
        mappings.append(
            simple_weight_mapping(
                weight_key=weight_key,
                tensor_name=tensor_name,
                tensor=tensor,
                spans=spans,
            )
        )

    return {
        "status": "complete" if mappings and not missing else "incomplete",
        "manifestPath": export["manifestPath"],
        "manifestSha256": export["manifestSha256"],
        "weightSetId": export["weightSetId"],
        "weightSetSha256": export["weightSetSha256"],
        "declaredShardCount": len(export.get("shardIdentities") or []),
        "requiredWeightCount": len(required_keys),
        "mappedWeightCount": len(mappings),
        "missingWeightCount": len(missing),
        "missingWeightKeys": missing,
        "requiredWeightKeysSha256": sha256_json(required_keys),
        "mappedWeightKeysSha256": sha256_json(
            [mapping["weightKey"] for mapping in mappings]
        ),
        "mappings": mappings,
    }


def program_bundle_source(
    export: dict[str, Any],
    program_bundle_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if program_bundle_path is None or not program_bundle_path.is_file():
        return source_program(export), None
    program_bundle = load_json(program_bundle_path)
    try:
        source = source_program(
            export,
            program_bundle=program_bundle,
            program_bundle_link=hash_link(program_bundle_path, "doppler_program_bundle"),
        )
    except (KeyError, ValueError):
        source = source_program(export)
        source["programBundle"] = hash_link(
            program_bundle_path,
            "doppler_program_bundle",
        )
        if program_bundle.get("schema") == "doppler.program-bundle/v1":
            source["programContractVersion"] = program_bundle["schema"]
    return (source, program_bundle)


def state_inputs(hostplan_bundle_root: Path | None) -> dict[str, Any]:
    if hostplan_bundle_root is None or not hostplan_bundle_root.is_dir():
        return {
            "status": "not_bound",
            "stateBufferCount": 0,
            "hostStateEntryCount": 0,
            "stateBuffers": [],
            "hostStateEntries": [],
        }
    runtime_config_path = hostplan_bundle_root / "runtime-config.json"
    if not runtime_config_path.is_file():
        return {
            "status": "not_bound",
            "stateBufferCount": 0,
            "hostStateEntryCount": 0,
            "stateBuffers": [],
            "hostStateEntries": [],
        }
    runtime_config = load_json(runtime_config_path)
    state_buffers = runtime_config.get("stateBuffers") or []
    if not isinstance(state_buffers, list):
        state_buffers = []
    host_io_layout = runtime_config.get("hostIoLayout") or []
    if not isinstance(host_io_layout, list):
        host_io_layout = []
    host_state_entries = [
        entry
        for entry in host_io_layout
        if isinstance(entry, dict) and entry.get("bufferRole") == "state"
    ]
    return {
        "status": "bound",
        "runtimeConfig": hash_link(runtime_config_path, "doe_csl_host_plan_tool"),
        "stateBufferCount": len(state_buffers),
        "hostStateEntryCount": len(host_state_entries),
        "stateBuffers": state_buffers,
        "hostStateEntries": host_state_entries,
    }


def hostplan_projection(
    *,
    export: dict[str, Any],
    normalized: dict[str, Any],
    hostplan_bundle_root: Path | None,
) -> dict[str, Any]:
    if hostplan_bundle_root is None or not hostplan_bundle_root.is_dir():
        return {"status": "not_bound"}
    host_plan_path = hostplan_bundle_root / "host-plan.json"
    runtime_config_path = hostplan_bundle_root / "runtime-config.json"
    memory_plan_path = hostplan_bundle_root / "memory-plan.json"
    simulator_plan_path = hostplan_bundle_root / "simulator-plan.json"
    normalized_path = hostplan_bundle_root / "normalized-execution-v1.json"
    program_bundle_path = hostplan_bundle_root / "doppler-program-bundle.json"
    required = [
        normalized_path,
        host_plan_path,
        runtime_config_path,
        memory_plan_path,
        simulator_plan_path,
    ]
    if not all(path.is_file() for path in required):
        return {"status": "not_bound"}
    host_plan_phase_summary = load_host_plan_phase_summary()
    runtime_config = load_json(runtime_config_path)
    summary = host_plan_phase_summary(
        host_plan_path,
        runtime_config=runtime_config,
        normalized_execution={
            "present": True,
            "path": rel(resolve(normalized["path"])),
            "sha256": normalized["sha256"],
            **normalized,
        },
        reference=export,
    )
    projection: dict[str, Any] = {
        "status": "bound",
        "bundleRoot": rel(hostplan_bundle_root),
        "normalizedExecution": hash_link(
            normalized_path,
            "production_graph_normalized_to_execution_v1",
        ),
        "hostPlan": hash_link(host_plan_path, "doe_csl_host_plan_tool"),
        "runtimeConfig": hash_link(runtime_config_path, "doe_csl_host_plan_tool"),
        "memoryPlan": hash_link(memory_plan_path, "doe_csl_host_plan_tool"),
        "simulatorPlan": hash_link(simulator_plan_path, "doe_csl_host_plan_tool"),
        "launchSchedule": summary.get("launchSchedule") or {},
    }
    if program_bundle_path.is_file():
        projection["programBundle"] = hash_link(
            program_bundle_path,
            "doe_program_bundle_ingest",
        )
    return projection


def materialize_export(
    *,
    reference_export_path: Path,
    program_bundle_path: Path | None,
    out_dir: Path,
) -> tuple[dict[str, Any], Path]:
    if reference_export_path.is_file():
        return load_json(reference_export_path), reference_export_path
    if program_bundle_path is None:
        raise FileNotFoundError(f"reference export not found: {reference_export_path}")
    source_out_dir = out_dir / "program-bundle-export"
    export, export_path = export_from_program_bundle(program_bundle_path, source_out_dir)
    return export, export_path


def build_contract(
    *,
    export: dict[str, Any],
    export_path: Path,
    out_path: Path,
    program_bundle_path: Path | None,
    hostplan_bundle_root: Path | None,
    doe_webgpu_host: str = DEFAULT_DOE_WEBGPU_HOST,
    doe_webgpu_host_executable: str | None = None,
    doe_webgpu_provider_module: str | None = None,
) -> dict[str, Any]:
    graph = load_json(graph_path_from_export(export))
    normalized_payload = normalized_hostplan_execution(export, graph)
    normalized_path = out_path.parent / "normalized-execution-v1.json"
    write_json(normalized_path, normalized_payload)
    normalized = {
        "path": rel(normalized_path),
        "sha256": sha256_file(normalized_path),
        "sourceGraphSha256": normalized_payload["sourceGraphSha256"],
        "modelConfig": normalized_payload["modelConfig"],
        "stepCount": len(normalized_payload.get("steps") or []),
    }
    source, _program_bundle = program_bundle_source(export, program_bundle_path)
    transcript_payload = load_json(resolve(reference_transcript_digest(export)["path"]))
    contract = {
        "schemaVersion": 1,
        "artifactKind": "doe_shared_execution_contract",
        "modelId": export["modelId"],
        "sourceProgram": source,
        "referenceExport": hash_link(export_path, "doppler_reference_export"),
        "doeWebgpuRuntime": doe_webgpu_runtime(
            host=doe_webgpu_host,
            host_executable=doe_webgpu_host_executable,
            provider_module=doe_webgpu_provider_module,
        ),
        "normalizedExecution": normalized,
        "promptInput": prompt_input(export),
        "decodeRequest": decode_request(export),
        "weightMappings": weight_mappings(export, normalized_payload),
        "stateInputs": state_inputs(hostplan_bundle_root),
        "transcriptContract": {
            "referenceTranscript": reference_transcript_digest(export),
            "kvCache": program_bundle_kv_cache_summary(
                transcript_payload.get("sourceReferenceTranscript")
                or transcript_payload
            ),
        },
        "hostPlanProjection": hostplan_projection(
            export=export,
            normalized=normalized,
            hostplan_bundle_root=hostplan_bundle_root,
        ),
    }
    return contract


def main() -> int:
    args = parse_args()
    out_path = resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    program_bundle_path = (
        resolve(args.program_bundle) if args.program_bundle is not None else None
    )
    hostplan_bundle_root = (
        resolve(args.hostplan_bundle_root)
        if args.hostplan_bundle_root
        else None
    )
    reference_export_path = resolve(args.reference_export)
    export, export_path = materialize_export(
        reference_export_path=reference_export_path,
        program_bundle_path=program_bundle_path,
        out_dir=out_path.parent,
    )
    contract = build_contract(
        export=export,
        export_path=export_path,
        out_path=out_path,
        program_bundle_path=program_bundle_path,
        hostplan_bundle_root=hostplan_bundle_root,
        doe_webgpu_host=args.doe_webgpu_host,
        doe_webgpu_host_executable=args.doe_webgpu_host_executable,
        doe_webgpu_provider_module=args.doe_webgpu_provider_module,
    )
    schema = load_json(resolve(args.schema))
    failures = schema_failures(contract, schema)
    if failures:
        joined = "; ".join(failures[:4])
        raise ValueError(f"shared execution contract schema validation failed: {joined}")
    write_json(out_path, contract)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
