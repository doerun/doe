#!/usr/bin/env python3
"""Emit the Doe CSL INT4 PLE transcript receipt.

This is the governed front door for the missing proof producer. Today it emits
an explicit blocked receipt because the production INT4 PLE prefill/decode CSL
lowering is not implemented. The receipt shape is intentionally the same shape
the future simfabric runner must populate when it exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_REGISTRY = Path("config/csl-runtime-fixtures.json")
HOST_PLAN_TOOL = Path("runtime/zig/zig-out/bin/doe-csl-host-plan-tool")
DEFAULT_HOSTPLAN_BUNDLE_ROOT = Path(
    "bench/out/doppler-reference/"
    "gemma-4-e2b-int4ple-doe-csl-hostplan"
)
CSL_SDK_DRIVER = Path("runtime/zig/tools/csl_sdk_driver.py")

FIXTURE_BY_DOPPLER_KERNEL = {
    "attn_decode": "attention-decode",
    "attn_head256": "attention-tiled",
    "attn_head512": "attention-tiled",
    "embed": "gather",
    "gelu": "gelu",
    "gemv": "fused-gemv-dequant",
    "lm_head_gemv": "fused-gemv-dequant",
    "lm_head_gemv_stable": "fused-gemv-dequant",
    "lm_head_prefill_stable": "tiled-matmul",
    "rope": "rope",
    "sample": "sample",
    "tiled": "tiled-matmul",
}

DOPPLER_KERNEL_TO_HOSTPLAN_OP = {
    "attn_decode": "attention",
    "attn_head256": "attention_prefill",
    "attn_head512": "attention_prefill",
    "embed": "embed",
    "final_norm_stable": "rmsnorm",
    "gelu": "gelu",
    "gemv": "matmul_q4k",
    "lm_head_gemv": "matmul_q4k",
    "lm_head_gemv_stable": "matmul_q4k",
    "lm_head_prefill_stable": "matmul",
    "residual": "residual",
    "rmsnorm": "rmsnorm",
    "rope": "rope",
    "sample": "sample",
    "tiled": "matmul",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference-export",
        default=(
            "bench/out/doppler-reference/"
            "gemma-4-e2b-int4ple-production-final-logits/"
            "doppler_int4ple_reference_export.json"
        ),
    )
    parser.add_argument(
        "--schema",
        default="config/doe-csl-int4ple-transcript.schema.json",
    )
    parser.add_argument(
        "--out",
        default=(
            "bench/out/doppler-reference/"
            "gemma-4-e2b-int4ple-doe-csl-transcript.blocked.json"
        ),
    )
    parser.add_argument(
        "--fixture-registry",
        default=str(FIXTURE_REGISTRY),
        help="CSL fixture registry used to classify graph lowering gaps.",
    )
    parser.add_argument(
        "--hostplan-tool",
        default=str(HOST_PLAN_TOOL),
        help="Doe execution-v1 HostPlan lowering tool.",
    )
    parser.add_argument(
        "--hostplan-bundle-root",
        default=str(DEFAULT_HOSTPLAN_BUNDLE_ROOT),
        help="Output directory for the normalized HostPlan bundle.",
    )
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def clean_directory(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_dir():
        raise ValueError(f"expected directory: {path}")
    for child in path.iterdir():
        if child.is_dir():
            clean_directory(child)
            child.rmdir()
        else:
            child.unlink()


def sha256_json(value: Any) -> str:
    data = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data + b"\n").hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def schema_failures(data: Any, schema: Any) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(
            validator.iter_errors(data),
            key=lambda item: tuple(str(p) for p in item.absolute_path),
        )
    ]


def reference_transcript_digest(export: dict[str, Any]) -> dict[str, Any]:
    transcript = export.get("decodeTranscript") or {}
    linked = transcript.get("transcript") or {}
    generated = transcript.get("generatedTokenIds") or {}
    return {
        "path": linked.get("path", "pending"),
        "sha256": linked.get("sha256", "pending"),
        "requestedDecodeSteps": transcript.get(
            "requestedDecodeSteps",
            transcript.get("decodeStepsRequested", 0),
        ),
        "actualDecodeSteps": transcript.get(
            "actualDecodeSteps",
            transcript.get("decodeStepsProduced", 0),
        ),
        "stopReason": transcript.get("stopReason", "pending"),
        "generatedTokenIdsSha256": generated.get("sha256", "pending"),
        "logitsDigestSha256": sha256_json(transcript.get("logitsDigests", [])),
    }


def source_program(export: dict[str, Any]) -> dict[str, Any]:
    graph = export.get("executionGraph") or {}
    return {
        "authoringSurface": "doppler_execution_v1",
        "manifestPath": export["manifestPath"],
        "manifestSha256": export["manifestSha256"],
        "graphPath": graph.get("path", "pending"),
        "graphSha256": export["executionGraphSha256"],
        "weightSetId": export["weightSetId"],
        "weightSha256": export["weightSetSha256"],
        "inputSetSha256": export["inputSetSha256"],
        "executionDepth": "not_executed",
    }


def load_fixture_ids(path: Path) -> set[str]:
    registry = load_json(path)
    fixtures = registry.get("fixtures") or []
    return {
        fixture["id"]
        for fixture in fixtures
        if isinstance(fixture, dict) and isinstance(fixture.get("id"), str)
    }


def hash_link(path: Path, source: str | None = None) -> dict[str, Any]:
    link: dict[str, Any] = {
        "path": rel(path),
        "sha256": sha256_file(path),
    }
    if source is not None:
        link["source"] = source
    return link


def graph_path_from_export(export: dict[str, Any]) -> Path:
    graph = export.get("executionGraph") or {}
    graph_path = graph.get("path")
    if not isinstance(graph_path, str) or not graph_path:
        raise ValueError("reference export is missing executionGraph.path")
    return resolve(graph_path)


def prefill_group_name(group: dict[str, Any], index: int) -> str:
    layers = group.get("layers") or []
    steps = group.get("steps") or []
    kernels = {
        step[1]
        for step in steps
        if isinstance(step, list) and len(step) >= 2
    }
    if "attn_head256" in kernels:
        label = "local_attention_layers"
    elif "attn_head512" in kernels:
        label = "global_attention_layers"
    else:
        label = f"group_{index}"
    if not layers:
        return f"prefill.{label}"
    return f"prefill.{label}.{layers[0]}-{layers[-1]}"


def graph_stage_records(graph: dict[str, Any]) -> list[dict[str, str]]:
    execution = graph.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("execution graph is missing execution object")

    records: list[dict[str, str]] = []

    for step in execution.get("preLayer") or []:
        records.append(stage_record("preLayer", step))

    for index, group in enumerate(execution.get("prefill") or []):
        if not isinstance(group, dict):
            continue
        stage = prefill_group_name(group, index)
        for step in group.get("steps") or []:
            records.append(stage_record(stage, step))

    for step in execution.get("decode") or []:
        records.append(stage_record("decode.layers.0-34", step))

    for step in execution.get("postLayer") or []:
        records.append(stage_record("postLayer", step))

    return records


def stage_record(stage: str, step: Any) -> dict[str, str]:
    if not isinstance(step, list) or len(step) < 2:
        raise ValueError(f"invalid execution graph step in {stage}: {step!r}")
    operation, kernel_id = step[0], step[1]
    if not isinstance(operation, str) or not isinstance(kernel_id, str):
        raise ValueError(f"invalid execution graph step in {stage}: {step!r}")
    record = {
        "stage": stage,
        "operation": operation,
        "kernelId": kernel_id,
    }
    if len(step) >= 3 and isinstance(step[2], str):
        record["weightRef"] = step[2]
    return record


def kernel_metadata(
    graph: dict[str, Any],
    kernel_id: str,
) -> dict[str, Any]:
    kernels = graph.get("execution", {}).get("kernels", {})
    metadata = kernels.get(kernel_id, {})
    return metadata if isinstance(metadata, dict) else {}


def manifest_model_config(
    export: dict[str, Any],
    bounded_max_seq_len: int,
) -> dict[str, Any]:
    manifest = load_json(resolve(export["manifestPath"]))
    arch = manifest.get("architecture")
    if not isinstance(arch, dict):
        raise ValueError("Doppler manifest is missing architecture")
    return {
        "hiddenDim": int(arch["hiddenSize"]),
        "numHeads": int(arch["numAttentionHeads"]),
        "headDim": int(arch["headDim"]),
        "globalHeadDim": int(arch["globalHeadDim"]),
        "numKeyValueHeads": int(arch["numKeyValueHeads"]),
        "numLayers": int(arch["numLayers"]),
        "vocabSize": int(arch["vocabSize"]),
        "maxSeqLen": bounded_max_seq_len,
        "quantFormat": "q4k",
        "ffnExpansionFactor": (
            int(arch["intermediateSize"]) // int(arch["hiddenSize"])
        ),
        "ffnMatrixCount": 3,
        "pleWidth": int(arch["hiddenSizePerLayerInput"]),
        "pleVocabSize": int(arch["vocabSizePerLayerInput"]),
    }


def transcript_seq_len_bound(export: dict[str, Any]) -> int:
    components = export.get("inputSetComponents") or {}
    token_count = int(components.get("tokenCount") or 0)
    decode_steps = int(components.get("decodeSteps") or 0)
    return max(1, token_count + decode_steps)


def sliding_window_size(export: dict[str, Any]) -> int:
    manifest = load_json(resolve(export["manifestPath"]))
    inference = manifest.get("inference") or {}
    attention = inference.get("attention") or {}
    value = attention.get("slidingWindow")
    return int(value) if isinstance(value, int) and value > 0 else 512


def step_to_hostplan(
    phase: str,
    step: Any,
    *,
    layer_index: int | None = None,
) -> dict[str, Any]:
    record = stage_record(phase, step)
    kernel_id = record["kernelId"]
    op = DOPPLER_KERNEL_TO_HOSTPLAN_OP.get(kernel_id)
    if op is None:
        raise ValueError(f"no HostPlan op mapping for kernel {kernel_id!r}")
    entry = {
        "name": record["operation"],
        "phase": phase,
        "op": op,
        "kernelKey": kernel_id,
    }
    if "weightRef" in record:
        weight_ref = record["weightRef"]
        if layer_index is not None:
            weight_ref = weight_ref.replace("{L}", str(layer_index))
        entry["weightsKey"] = weight_ref
    return entry


def find_prefill_group_for_layer(
    groups: list[Any],
    layer_index: int,
) -> dict[str, Any]:
    for group in groups:
        if not isinstance(group, dict):
            continue
        layers = group.get("layers") or []
        if layer_index in layers:
            return group
    raise ValueError(f"prefill group missing layer {layer_index}")


def normalized_hostplan_execution(
    export: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    model_config = manifest_model_config(export, transcript_seq_len_bound(export))
    execution = graph.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("execution graph is missing execution object")

    prefill_steps: list[dict[str, Any]] = []
    decode_steps: list[dict[str, Any]] = []
    for step in execution.get("preLayer") or []:
        prefill_steps.append(step_to_hostplan("prefill", step))

    prefill_groups = execution.get("prefill") or []
    for layer_index in range(model_config["numLayers"]):
        group = find_prefill_group_for_layer(prefill_groups, layer_index)
        for step in group.get("steps") or []:
            prefill_steps.append(
                step_to_hostplan(
                    "prefill",
                    step,
                    layer_index=layer_index,
                )
            )

    for layer_index in range(model_config["numLayers"]):
        for step in execution.get("decode") or []:
            decode_steps.append(
                step_to_hostplan(
                    "decode",
                    step,
                    layer_index=layer_index,
                )
            )

    for step in execution.get("postLayer") or []:
        name = step[0] if isinstance(step, list) and step else ""
        if name == "sample":
            decode_steps.append(step_to_hostplan("decode", step))
        elif name == "lm_head":
            decode_steps.append(step_to_hostplan("decode", step))
        elif isinstance(name, str) and name.endswith("_prefill"):
            prefill_steps.append(step_to_hostplan("prefill", step))
        else:
            prefill_steps.append(step_to_hostplan("prefill", step))
            decode_steps.append(step_to_hostplan("decode", step))

    return {
        "modelFamily": "gemma4",
        "modelId": export["modelId"],
        "sourceGraphSha256": export["executionGraphSha256"],
        "modelConfig": model_config,
        "placementPolicy": {
            "maxGridWidth": 512,
            "maxGridHeight": 512,
            "preferSquare": True,
        },
        "eosTokenId": 1,
        "slidingWindowSize": sliding_window_size(export),
        "layerPattern": {
            "type": "every_n",
            "period": 5,
            "offset": 4,
        },
        "numKvSharedLayers": int(model_config["numLayers"]),
        "steps": prefill_steps + decode_steps,
    }


def hostplan_bundle_blocked(source_graph_sha256: str, message: str) -> dict[str, Any]:
    return {
        "status": "hostplan_failed",
        "sourceGraphSha256": source_graph_sha256,
        "normalizedExecution": {
            "path": "pending",
            "sha256": "pending",
            "source": "hostplan_normalization_failed",
        },
        "bundleRoot": "pending",
        "hostPlan": {
            "path": "pending",
            "sha256": "pending",
            "source": "hostplan_lowering_failed",
        },
        "runtimeConfig": {
            "path": "pending",
            "sha256": "pending",
            "source": "hostplan_lowering_failed",
        },
        "memoryPlan": {
            "path": "pending",
            "sha256": "pending",
            "source": "hostplan_lowering_failed",
        },
        "simulatorPlan": {
            "path": "pending",
            "sha256": "pending",
            "source": "hostplan_lowering_failed",
        },
        "prefillLaunchCount": 0,
        "decodeLaunchCount": 0,
        "kernelCount": 0,
        "blocker": message,
    }


def build_hostplan_bundle(
    export: dict[str, Any],
    bundle_root: Path,
    hostplan_tool: Path,
) -> dict[str, Any]:
    graph_path = graph_path_from_export(export)
    graph = load_json(graph_path)
    source_graph_sha256 = export["executionGraphSha256"]
    if sha256_file(graph_path) != source_graph_sha256:
        raise ValueError("execution graph hash mismatch before HostPlan lowering")

    bundle_root.mkdir(parents=True, exist_ok=True)
    clean_directory(bundle_root)
    normalized_path = bundle_root / "normalized-execution-v1.json"
    normalized = normalized_hostplan_execution(export, graph)
    write_json(normalized_path, normalized)

    command = [
        str(hostplan_tool),
        "--input",
        str(normalized_path),
        "--bundle-root",
        str(bundle_root),
        "--mode",
        "steps",
        "--driver-executable-path",
        str(resolve(CSL_SDK_DRIVER)),
    ]
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        log_path = bundle_root / "hostplan-lowering-error.json"
        write_json(
            log_path,
            {
                "command": command,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            },
        )
        blocked = hostplan_bundle_blocked(
            source_graph_sha256,
            f"HostPlan lowering failed with exit code {proc.returncode}.",
        )
        blocked["normalizedExecution"] = hash_link(
            normalized_path,
            "production_graph_normalized_to_execution_v1",
        )
        return blocked

    host_plan_path = bundle_root / "host-plan.json"
    runtime_config_path = bundle_root / "runtime-config.json"
    memory_plan_path = bundle_root / "memory-plan.json"
    simulator_plan_path = bundle_root / "simulator-plan.json"
    host_plan = load_json(host_plan_path)
    host_plan_body = host_plan.get("hostPlan") or {}
    phases = host_plan_body.get("phases") or {}
    return {
        "status": "hostplan_ready",
        "sourceGraphSha256": source_graph_sha256,
        "normalizedExecution": hash_link(
            normalized_path,
            "production_graph_normalized_to_execution_v1",
        ),
        "bundleRoot": rel(bundle_root),
        "hostPlan": hash_link(host_plan_path, "doe_csl_host_plan_tool"),
        "runtimeConfig": hash_link(runtime_config_path, "doe_csl_host_plan_tool"),
        "memoryPlan": hash_link(memory_plan_path, "doe_csl_host_plan_tool"),
        "simulatorPlan": hash_link(simulator_plan_path, "doe_csl_host_plan_tool"),
        "prefillLaunchCount": len(phases.get("prefill") or []),
        "decodeLaunchCount": len(phases.get("decode") or []),
        "kernelCount": len(host_plan_body.get("kernels") or []),
        "blocker": (
            "HostPlan bundle is generated, but the CSL transcript runner is "
            "still blocked until these production-bound kernels are compiled, "
            "wired to real RDRR weights/KV state, run under simfabric, and "
            "emit token/logit/KV transcript artifacts."
        ),
    }


def build_lowering_plan(
    export: dict[str, Any],
    fixture_ids: set[str],
) -> dict[str, Any]:
    graph_path = graph_path_from_export(export)
    graph = load_json(graph_path)
    graph_hash = sha256_file(graph_path)
    expected_hash = export["executionGraphSha256"]
    if graph_hash != expected_hash:
        raise ValueError(
            "execution graph hash mismatch: "
            f"{graph_hash} != {expected_hash}"
        )

    stages = []
    unsupported = []
    available_fixtures = set()
    for record in graph_stage_records(graph):
        kernel_id = record["kernelId"]
        metadata = kernel_metadata(graph, kernel_id)
        fixture_id = FIXTURE_BY_DOPPLER_KERNEL.get(kernel_id)
        stage = {
            "stage": record["stage"],
            "operation": record["operation"],
            "kernelId": kernel_id,
            "status": "missing_production_csl_kernel",
        }
        if isinstance(metadata.get("kernel"), str):
            stage["kernelFile"] = metadata["kernel"]
        if isinstance(metadata.get("entry"), str):
            stage["entry"] = metadata["entry"]
        if fixture_id and fixture_id in fixture_ids:
            stage["fixtureId"] = fixture_id
            stage["status"] = "fixture_available_not_production_bound"
            stage["blocker"] = (
                f"CSL fixture {fixture_id!r} exists, but no production "
                "Doppler INT4 PLE graph binding emits this full-model "
                "transcript stage."
            )
            available_fixtures.add(fixture_id)
            reason = (
                f"fixture {fixture_id!r} is runtime-ready only as an "
                "isolated pattern, not as a production transcript kernel"
            )
        else:
            stage["blocker"] = (
                "No production CSL lowering is registered for this "
                "Doppler execution-v1 kernel in the INT4 PLE transcript lane."
            )
            reason = "no production CSL lowering registered for this kernel"
        stages.append(stage)
        unsupported_stage = {
            "stage": stage["stage"],
            "operation": stage["operation"],
            "kernelId": kernel_id,
            "reason": reason,
        }
        if "kernelFile" in stage:
            unsupported_stage["kernelFile"] = stage["kernelFile"]
        unsupported.append(unsupported_stage)

    production_count = sum(
        1 for stage in stages
        if stage["status"] == "production_csl_kernel_available"
    )
    status = (
        "ready_for_simfabric"
        if production_count == len(stages) and not unsupported
        else "blocked_missing_production_kernels"
    )
    return {
        "status": status,
        "sourceGraphSha256": expected_hash,
        "operationCount": len(stages),
        "supportedOperationCount": production_count,
        "missingOperationCount": len(unsupported),
        "availableFixtureIds": sorted(available_fixtures),
        "stages": stages,
        "unsupportedKernels": unsupported,
    }


def summarize_lowering_blocker(plan: dict[str, Any]) -> str:
    unsupported = plan.get("unsupportedKernels") or []
    kernels = []
    for item in unsupported:
        kernel_id = item.get("kernelId")
        if isinstance(kernel_id, str) and kernel_id not in kernels:
            kernels.append(kernel_id)
    preview = ", ".join(kernels[:8])
    suffix = "" if len(kernels) <= 8 else f", +{len(kernels) - 8} more"
    return (
        "Doe CSL simfabric bounded prefill+decode transcript is blocked: "
        f"{plan.get('missingOperationCount', 0)} graph stage(s) lack "
        "production-bound CSL lowering"
        f" ({preview}{suffix})."
    )


def build_blocked_receipt(
    export: dict[str, Any],
    lowering_plan: dict[str, Any],
    hostplan_bundle: dict[str, Any],
) -> dict[str, Any]:
    transcript = export.get("decodeTranscript") or {}
    input_components = export.get("inputSetComponents") or {}
    reference = reference_transcript_digest(export)
    requested = reference["requestedDecodeSteps"]
    actual = reference["actualDecodeSteps"]
    stop_reason = reference["stopReason"]
    blocker = summarize_lowering_blocker(lowering_plan)
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_int4ple_transcript",
        "status": "blocked_missing_csl_lowering",
        "modelId": export["modelId"],
        "sourceProgram": source_program(export),
        "decodeRequest": {
            "requestedDecodeSteps": requested,
            "expectedActualDecodeSteps": actual,
            "expectedStopReason": stop_reason,
            "samplingSha256": input_components.get("samplingSha256", "pending"),
            "inputSetSha256": export["inputSetSha256"],
        },
        "referenceTranscript": reference,
        "loweringPlan": lowering_plan,
        "hostPlanBundle": hostplan_bundle,
        "cslTranscript": {
            "status": "not_produced",
            "requestedDecodeSteps": requested,
            "actualDecodeSteps": 0,
            "stopReason": "not_run",
            "transcript": {
                "path": "pending",
                "sha256": "pending",
                "source": "pending_full_int4ple_csl_transcript_lowering",
            },
            "generatedTokenIds": {
                "path": "pending",
                "sha256": "pending",
                "dtype": "uint32",
                "tokenCount": 0,
                "preview": [],
            },
            "logitsDigests": [],
        },
        "kvCacheEvidence": {
            "realKvCache": False,
            "evidenceSource": "not_available",
            "cacheWriteCount": 0,
            "cacheReadCount": 0,
            "blocker": (
                "full production INT4 PLE CSL prefill/decode lowering is "
                "not implemented"
            ),
            "layerSpanCoverage": {
                "layerCount": 35,
                "coveredLayerCount": 0,
                "spans": [],
            },
            "stepStateDigests": [],
        },
        "simulatorRun": {
            "runner": rel(Path(__file__)),
            "status": "not_run",
            "tracePath": "pending",
            "traceSha256": "pending",
            "kernelStage": "pending_full_int4ple_csl_transcript_lowering",
            "kernelIsStub": True,
            "elapsedMs": None,
        },
        "inputsSynthetic": False,
        "weightsSynthetic": False,
        "blocker": blocker,
    }


def main() -> int:
    args = parse_args()
    try:
        export = load_json(resolve(args.reference_export))
        schema = load_json(resolve(args.schema))
        fixture_ids = load_fixture_ids(resolve(args.fixture_registry))
        lowering_plan = build_lowering_plan(export, fixture_ids)
        hostplan_bundle = build_hostplan_bundle(
            export,
            resolve(args.hostplan_bundle_root),
            resolve(args.hostplan_tool),
        )
        receipt = build_blocked_receipt(export, lowering_plan, hostplan_bundle)
        failures = schema_failures(receipt, schema)
        if failures:
            print("FAIL: Doe CSL INT4 PLE transcript receipt schema")
            for failure in failures:
                print(f"  {failure}")
            return 1
        out = resolve(args.out)
        write_json(out, receipt)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: Doe CSL INT4 PLE transcript receipt: {exc}")
        return 1

    print(
        "PASS: wrote blocked Doe CSL INT4 PLE transcript receipt "
        f"({rel(resolve(args.out))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
