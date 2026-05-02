#!/usr/bin/env python3
"""Gemma 4 31B af16 session runtime contract helpers.

The streaming front door owns CLI orchestration. This module owns the
session-scoped contract: real weight mappings, host I/O layout, serial launch
bindings, KV state threading, sampled-token feedback, and transcript capture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = REPO_ROOT.parent
RUNNER_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from int4ple_hostplan_execution_plan import build_hostplan_execution_plan  # noqa: E402
from int4ple_hostplan_executor_validator import validate_hostplan_executor  # noqa: E402
from int4ple_compile_target_sim_runner import (  # noqa: E402
    DEFAULT_LAUNCH_TIMEOUT_SECONDS,
    execute_hostplan_runtime,
    execute_hostplan_runtime_bootstrap,
)
from int4ple_checkpoint import (  # noqa: E402
    CheckpointError,
    CheckpointMissingError,
    compute_identity as compute_checkpoint_identity,
    init_checkpoint,
    load_checkpoint,
)

MODEL_ID = "gemma-4-31b-it-text-q4k-ehf16-af16"
LANE_KEY = "q4k-ehf16-af16"
SESSION_ARTIFACT_PREFIX = "gemma4_31b_af16"
DEFAULT_PROMPT_TOKEN_IDS = [2, 3]
LM_HEAD_KERNELS = frozenset({
    "lm_head_gemv",
    "lm_head_gemv_stable",
    "lm_head_prefill_stable",
})
PER_LAYER_INPUT_KERNELS = frozenset({
    "ple_embed",
    "ple_proj",
    "ple_rmsnorm",
    "ple_residual",
})
SUMMA_KERNELS = frozenset({"tiled", "ple_proj"})
PREFILL_Q4K_GEMV_KERNELS = frozenset({"tiled_31b"})
PREFILL_Q4K_GEMV_PATTERN = "prefill_q4k_gemv"


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    resolved = resolve(path)
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pass
    try:
        return "../" + resolved.relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def load_json(path: Path) -> Any:
    return json.loads(resolve(path).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with resolve(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_weight_root(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    manifest_root = resolve(manifest_path).parent
    weights_ref = manifest.get("weightsRef") or {}
    raw_root = weights_ref.get("artifactRoot")
    if isinstance(raw_root, str) and raw_root:
        return (manifest_root / raw_root).resolve()
    return manifest_root


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def expected_model_id(args: argparse.Namespace) -> str:
    return str(getattr(args, "expected_model_id", MODEL_ID) or MODEL_ID)


def session_artifact_prefix(args: argparse.Namespace) -> str:
    return str(
        getattr(args, "session_artifact_prefix", SESSION_ARTIFACT_PREFIX)
        or SESSION_ARTIFACT_PREFIX
    )


def optional_resolved_path(args: argparse.Namespace, name: str) -> Path | None:
    raw = getattr(args, name, None)
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return resolve(Path(text))


def runtime_dtype(manifest_dtype: str) -> str:
    if manifest_dtype == "BF16":
        return "bf16"
    if manifest_dtype == "F16":
        return "f16"
    if manifest_dtype == "Q4_K_M":
        return "u8_q4k"
    if manifest_dtype == "Q8_0":
        return "u8_q8"
    if manifest_dtype == "F32":
        return "f32"
    raise ValueError(f"unsupported runtime weight dtype: {manifest_dtype}")


def runtime_quant(manifest_dtype: str) -> dict[str, Any]:
    if manifest_dtype == "BF16":
        return {
            "format": "BF16",
            "storageDtype": "bfloat16",
            "sourceDtype": "bfloat16",
        }
    if manifest_dtype == "F16":
        return {
            "format": "F16",
            "storageDtype": "float16",
            "sourceDtype": "float16",
        }
    if manifest_dtype == "F32":
        return {
            "format": "F32",
            "storageDtype": "float32",
            "sourceDtype": "float32",
        }
    if manifest_dtype == "Q4_K_M":
        return {
            "format": "Q4_K_M",
            "storageDtype": "uint8",
            "sourceDtype": "float16",
            "blockSizeElements": 256,
            "blockSizeBytes": 144,
            "encoding": "rdrr_int4ple",
        }
    if manifest_dtype == "Q8_0":
        return {
            "format": "Q8_0",
            "storageDtype": "uint8",
            "sourceDtype": "float16",
            "blockSizeElements": 32,
            "blockSizeBytes": 34,
            "encoding": "rdrr_int4ple",
        }
    raise ValueError(f"unsupported runtime weight quant metadata: {manifest_dtype}")


def shard_identities_by_index(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    identities: dict[int, dict[str, Any]] = {}
    for shard in manifest.get("shards") or []:
        if not isinstance(shard, dict):
            continue
        index = int(shard.get("index", len(identities)))
        identities[index] = shard
    return identities


def tensor_spans_for_runtime(
    *,
    tensor: dict[str, Any],
    shard_identities: dict[int, dict[str, Any]],
    weight_root: Path,
) -> list[dict[str, Any]]:
    raw_spans = tensor.get("spans")
    if not isinstance(raw_spans, list):
        raw_spans = [
            {
                "shardIndex": int(tensor["shard"]),
                "offset": int(tensor["offset"]),
                "size": int(tensor["size"]),
            }
        ]
    spans: list[dict[str, Any]] = []
    for raw_span in raw_spans:
        shard_index = int(raw_span["shardIndex"])
        identity = shard_identities.get(shard_index, {})
        filename = str(identity.get("filename", f"shard_{shard_index:05d}.bin"))
        spans.append(
            {
                "shardIndex": shard_index,
                "shardPath": str((weight_root / filename).resolve()),
                "shardSha256": str(
                    identity.get("sha256")
                    or identity.get("hash")
                    or identity.get("blake3")
                    or "missing"
                ),
                "offset": int(raw_span["offset"]),
                "size": int(raw_span["size"]),
            }
        )
    return spans


def runtime_mapping_from_tensor(
    *,
    weight_key: str,
    tensor_name: str,
    tensor: dict[str, Any],
    spans: list[dict[str, Any]],
    pe_count: int,
) -> dict[str, Any]:
    manifest_dtype = str(tensor["dtype"])
    shape = [int(value) for value in tensor.get("shape", [])]
    return {
        "shard": spans[0]["shardPath"],
        "path": spans[0]["shardPath"],
        "sha256": spans[0]["shardSha256"],
        "peBuffer": weight_key,
        "peRange": [0, max(0, pe_count - 1)],
        "dtype": runtime_dtype(manifest_dtype),
        "tensor": weight_key,
        "offsetBytes": int(spans[0]["offset"]),
        "shape": shape,
        "quant": runtime_quant(manifest_dtype),
        "weightKey": weight_key,
        "tensorName": tensor_name,
        "role": str(tensor.get("role", "unknown")),
        "layout": str(tensor.get("layout", "unknown")),
        "byteSize": int(tensor["size"]),
        "byteOffset": int(spans[0]["offset"]),
        "spans": spans,
    }


def runtime_mapping_from_sidecar(
    *,
    weight_key: str,
    path: Path,
    pe_count: int,
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    size = path.stat().st_size
    element_count = size // 4
    return {
        "shard": str(path.resolve()),
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "peBuffer": weight_key,
        "peRange": [0, max(0, pe_count - 1)],
        "dtype": "f32",
        "tensor": weight_key,
        "offsetBytes": 0,
        "shape": sidecar_shape_for_runtime(
            weight_key=weight_key,
            element_count=element_count,
            runtime_config=runtime_config,
        ),
        "quant": runtime_quant("F32"),
        "weightKey": weight_key,
        "tensorName": weight_key,
        "role": "sidecar_weight",
        "layout": "flat_sidecar",
        "byteSize": size,
        "byteOffset": 0,
        "spans": [
            {
                "shardIndex": -1,
                "shardPath": str(path.resolve()),
                "shardSha256": sha256_file(path),
                "offset": 0,
                "size": size,
            }
        ],
    }


def sidecar_shape_for_runtime(
    *,
    weight_key: str,
    element_count: int,
    runtime_config: dict[str, Any],
) -> list[int]:
    model = runtime_config.get("modelConfig") or {}
    try:
        ple_width = int(model.get("pleWidth") or 0)
    except (TypeError, ValueError):
        ple_width = 0
    if (
        ".perLayerModelProjection.layer" in weight_key
        and ple_width > 0
        and element_count % ple_width == 0
    ):
        return [element_count // ple_width, ple_width]
    return [element_count]


def build_runtime_weight_mappings(
    *,
    manifest_path: Path,
    weight_plan: dict[str, Any],
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    tensors = manifest.get("tensors") or {}
    weight_root = resolve_weight_root(manifest_path, manifest)
    grid = (runtime_config.get("memoryPlan") or {}).get("grid") or {}
    pe_count = int(grid.get("width") or 1) * int(grid.get("height") or 1)
    shard_identities = shard_identities_by_index(manifest)
    mappings: list[dict[str, Any]] = []
    missing: list[str] = []
    sidecar_keys: list[str] = []

    for record in weight_plan.get("requiredWeights") or []:
        if not isinstance(record, dict):
            continue
        key = str(record.get("weightKey") or "")
        if not key:
            continue
        matched_tensor = record.get("matchedTensor")
        matched_file = record.get("matchedFile")
        if isinstance(matched_tensor, str) and isinstance(tensors.get(matched_tensor), dict):
            tensor = tensors[matched_tensor]
            spans = tensor_spans_for_runtime(
                tensor=tensor,
                shard_identities=shard_identities,
                weight_root=weight_root,
            )
            mappings.append(
                runtime_mapping_from_tensor(
                    weight_key=key,
                    tensor_name=matched_tensor,
                    tensor=tensor,
                    spans=spans,
                    pe_count=pe_count,
                )
            )
            continue
        if isinstance(matched_file, str) and matched_file:
            path = weight_root / matched_file
            if path.is_file():
                mappings.append(
                    runtime_mapping_from_sidecar(
                        weight_key=key,
                        path=path,
                        pe_count=pe_count,
                        runtime_config=runtime_config,
                    )
                )
                sidecar_keys.append(key)
                continue
        if record.get("resolutionKind") in {
            "linear_attention_absent_v_projection",
            "architecture_disabled_session_input",
            "linear_attention_session_state",
        }:
            continue
        missing.append(key)

    return {
        "mappings": mappings,
        "identity": {
            "modelId": manifest.get("modelId"),
            "manifestPath": rel(manifest_path),
            "manifestSha256": sha256_file(manifest_path),
            "weightSetId": (manifest.get("artifactIdentity") or {}).get(
                "weightPackId"
            ),
            "weightSetSha256": (manifest.get("artifactIdentity") or {}).get(
                "shardSetHash"
            ),
            "declaredShardCount": len(manifest.get("shards") or []),
            "requiredWeightCount": int(weight_plan.get("requiredWeightCount") or 0),
            "mappedWeightCount": len(mappings),
            "missingWeightCount": len(missing),
            "missingWeightKeys": missing,
            "sidecarWeightKeys": sidecar_keys,
            "requiredWeightKeysSha256": sha256_json(
                [
                    str(item.get("weightKey"))
                    for item in weight_plan.get("requiredWeights") or []
                    if isinstance(item, dict) and item.get("weightKey")
                ]
            ),
            "mappedWeightKeysSha256": sha256_json(
                [mapping["weightKey"] for mapping in mappings]
            ),
        },
    }


def normalize_smoke_execution(
    *,
    smoke_config_path: Path,
    out_dir: Path,
    model_layer_count: int,
) -> dict[str, Any]:
    smoke = load_json(smoke_config_path)
    payload = {
        "schemaVersion": 1,
        "artifactKind": "generic_af16_normalized_execution_v1",
        "source": {
            "path": rel(smoke_config_path),
            "sha256": sha256_file(smoke_config_path),
        },
        "modelConfig": {
            **(smoke.get("modelConfig") or {}),
            "numLayers": model_layer_count,
        },
        "steps": smoke.get("steps") or [],
    }
    payload["sourceGraphSha256"] = sha256_json(payload["steps"])
    path = out_dir / "normalized-execution-v1.json"
    write_json(path, payload)
    return {
        "present": True,
        "path": str(path),
        "sha256": sha256_file(path),
        "modelConfig": payload["modelConfig"],
        "steps": payload["steps"],
    }


def token_prompt_ids(args: argparse.Namespace) -> list[int]:
    supplied = [int(value) for value in args.prompt_token_id]
    source = supplied if supplied else DEFAULT_PROMPT_TOKEN_IDS
    count = max(1, int(args.prefill_token_count))
    if len(source) >= count:
        return source[:count]
    return [*source, *([source[-1]] * (count - len(source)))]


def build_reference_request(
    *,
    args: argparse.Namespace,
    session_dir: Path,
) -> dict[str, Any]:
    token_ids = token_prompt_ids(args)
    prompt_path = session_dir / "inputs" / "prompt.u32"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    np.asarray(token_ids, dtype=np.uint32).tofile(prompt_path)
    transcript_path = session_dir / "reference-request.json"
    transcript_payload = {
        "schemaVersion": 1,
        "artifactKind": f"{session_artifact_prefix(args)}_runtime_request",
        "promptTokenIds": token_ids,
        "requestedDecodeSteps": int(args.decode_token_count),
        "actualDecodeSteps": 0,
        "kvCache": {
            "mode": "runtime_capture_required",
            "layerDigestCount": 0,
        },
    }
    write_json(transcript_path, transcript_payload)
    return {
        "modelId": expected_model_id(args),
        "manifestPath": rel(args.source_doppler_manifest),
        "manifestSha256": sha256_file(args.source_doppler_manifest),
        "inputSetComponents": {"tokenCount": len(token_ids)},
        "tokenizedPrompt": {
            "path": str(prompt_path),
            "sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
            "tokenCount": len(token_ids),
        },
        "decodeTranscript": {
            "status": "request_ready",
            "requestedDecodeSteps": int(args.decode_token_count),
            "actualDecodeSteps": 0,
            "stopReason": "pending_runtime_execution",
            "generatedTokenIds": {"tokenCount": 0},
            "logitsDigests": [],
            "transcript": {"path": str(transcript_path)},
        },
    }


def binding(
    *,
    symbol: str,
    buffer: str,
    role: str,
    access: str,
    source: str,
    **fields: Any,
) -> dict[str, Any]:
    result = {
        "symbol": symbol,
        "buffer": buffer,
        "role": role,
        "access": access,
        "source": source,
    }
    for key, value in fields.items():
        if value is not None:
            result[key] = value
    return result


def symbol_table_entry(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "buffer": item["buffer"],
        "role": item["role"],
        "access": item["access"],
    }


def append_symbol_table_entry(
    symbols: dict[str, dict[str, Any]],
    item: dict[str, Any],
) -> None:
    symbol = item["symbol"]
    entry = symbol_table_entry(item)
    existing = symbols.get(symbol)
    if existing is None:
        symbols[symbol] = entry
        return
    bindings = existing.get("bindings")
    if isinstance(bindings, list):
        bindings.append(entry)
    else:
        bindings = [symbol_table_entry(existing), entry]
    buffers = {str(record.get("buffer") or "") for record in bindings}
    roles = {str(record.get("role") or "") for record in bindings}
    accesses = {str(record.get("access") or "") for record in bindings}
    symbols[symbol] = {
        "buffer": next(iter(buffers)) if len(buffers) == 1 else "multiple",
        "role": next(iter(roles)) if len(roles) == 1 else "inout",
        "access": next(iter(accesses)) if len(accesses) == 1 else "readwrite",
        "bindings": bindings,
    }


def routed_tensor_role(buffer: str) -> str:
    if buffer.startswith("state:kv_cache"):
        return "kv_cache"
    return "activation"


def output_buffer(step: dict[str, Any], launch_index: int) -> str:
    layer = step.get("layer")
    token = step.get("tokenIndex")
    layer_part = "global" if layer is None else f"layer{layer}"
    token_part = "" if token is None else f":token{token}"
    return f"activation:{step['phase']}{token_part}:{launch_index:04d}:{layer_part}:{step['name']}"


def build_real_session_scheduler(
    *,
    dispatch_plan: dict[str, Any],
    runtime_config: dict[str, Any],
    architecture_disabled_weight_keys: list[str] | None = None,
    per_layer_input_block_enabled: bool = True,
) -> dict[str, Any]:
    launches: list[dict[str, Any]] = []
    blockers: list[str] = []
    sample_feedback_edges: list[dict[str, Any]] = []
    kv_operations: list[dict[str, Any]] = []
    transcript_emitters: list[dict[str, Any]] = []
    elided_operations: list[dict[str, Any]] = []
    lifetimes: dict[str, dict[str, Any]] = {}
    current = "input:prompt_token_ids"
    layer_state: dict[int, dict[str, str]] = {}
    last_generated_token = "input:prompt_token_ids"
    last_logits = ""
    last_logits_launch_index: int | None = None
    disabled_weight_keys = {
        str(item)
        for item in architecture_disabled_weight_keys or []
        if str(item)
    }
    weight_shapes = {
        str(item.get("weightKey") or item.get("tensor") or ""): (
            item.get("shape") if isinstance(item.get("shape"), list) else []
        )
        for item in runtime_config.get("weightMappings") or []
        if isinstance(item, dict)
    }

    def weight_matrix_dims(weight_key: Any) -> tuple[int | None, int | None]:
        shape = weight_shapes.get(str(weight_key or "")) or []
        if len(shape) < 2:
            return None, None
        try:
            return int(shape[0]), int(shape[1])
        except (TypeError, ValueError):
            return None, None

    def touch_input(buffer: str, role: str, launch_index: int) -> None:
        item = lifetimes.setdefault(
            buffer,
            {
                "buffer": buffer,
                "role": role,
                "producerLaunchIndex": None,
                "firstConsumerLaunchIndex": None,
                "lastConsumerLaunchIndex": None,
                "consumerCount": 0,
            },
        )
        if item["firstConsumerLaunchIndex"] is None:
            item["firstConsumerLaunchIndex"] = launch_index
        item["lastConsumerLaunchIndex"] = launch_index
        item["consumerCount"] += 1

    def touch_output(buffer: str, role: str, launch_index: int) -> None:
        item = lifetimes.setdefault(
            buffer,
            {
                "buffer": buffer,
                "role": role,
                "producerLaunchIndex": None,
                "firstConsumerLaunchIndex": None,
                "lastConsumerLaunchIndex": None,
                "consumerCount": 0,
            },
        )
        if item["producerLaunchIndex"] is None:
            item["producerLaunchIndex"] = launch_index

    def make_launch(step: dict[str, Any]) -> None:
        nonlocal current, last_generated_token, last_logits, last_logits_launch_index
        launch_index = len(launches)
        kernel = str(step.get("kernelKey") or "")
        name = str(step.get("name") or kernel)
        weight_key = step.get("weightKey")
        is_lm_head = (
            name == "lm_head"
            or kernel in LM_HEAD_KERNELS
            or weight_key == "lm_head"
        )
        layer = step.get("layer")
        layer_idx = layer if isinstance(layer, int) else None
        state = layer_state.setdefault(layer_idx if layer_idx is not None else -1, {})
        inputs: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []

        def elide_operation(reason: str, *, input_buffer: str = "") -> None:
            elided_operations.append(
                {
                    "phase": step["phase"],
                    "layerIndex": layer_idx,
                    "decodeStepIndex": step.get("tokenIndex"),
                    "operationName": name,
                    "kernelName": kernel,
                    "weightKey": weight_key,
                    "reason": reason,
                    "inputBuffer": input_buffer,
                    "aliasRole": "current_activation",
                    "aliasBuffer": input_buffer,
                }
            )

        def add_input(
            symbol: str,
            buffer_name: str,
            role: str,
            source: str,
            **fields: Any,
        ) -> None:
            inputs.append(
                binding(
                    symbol=symbol,
                    buffer=buffer_name,
                    role=role,
                    access="read",
                    source=source,
                    **fields,
                )
            )
            touch_input(buffer_name, role, launch_index)

        def add_output(
            symbol: str,
            buffer_name: str,
            role: str,
            source: str,
            **fields: Any,
        ) -> None:
            outputs.append(
                binding(
                    symbol=symbol,
                    buffer=buffer_name,
                    role=role,
                    access="write",
                    source=source,
                    **fields,
                )
            )
            touch_output(buffer_name, role, launch_index)

        out = output_buffer(step, launch_index)
        if kernel in PER_LAYER_INPUT_KERNELS and not per_layer_input_block_enabled:
            elide_operation(
                "architecture_disabled_per_layer_input_block",
                input_buffer=current if kernel == "ple_residual" else "",
            )
            return
        if kernel in {"embed", "ple_embed"}:
            token_source = (
                "input:prompt_token_ids"
                if step["phase"] == "prefill"
                else last_generated_token
            )
            add_input("indices", token_source, "tokenized_prompt", "runtime_prompt")
            add_input("table", f"weight:{step.get('weightKey')}", "weight", "weights")
            add_output("output", out, "activation", f"{kernel}.output")
            if kernel == "ple_embed":
                state["ple_gather"] = out
            current = out
        elif kernel in SUMMA_KERNELS:
            matrix_n, matrix_k = weight_matrix_dims(weight_key)
            if kernel == "ple_proj":
                source = state.get("ple_gather", current)
            elif name in {"q_proj", "k_proj", "v_proj"}:
                source = state.get("attn_norm", current)
            elif name in {"gate_proj", "up_proj"}:
                source = state.get("ffn_norm", current)
            elif name == "down_proj":
                source = state.get("activation", current)
            else:
                source = current
            add_input(
                "a",
                source,
                "activation",
                "activation_router",
                matrixCols=matrix_k,
            )
            add_input("b", f"weight:{step.get('weightKey')}", "weight", "weights")
            add_output(
                "c",
                out,
                "logits" if is_lm_head else "activation",
                f"{kernel}.output",
                matrixCols=matrix_n,
            )
            if is_lm_head:
                decode_index = int(step.get("tokenIndex") or 0)
                last_logits = out
                last_logits_launch_index = launch_index
                transcript_emitters.append(
                    {
                        "kind": "logits_digest",
                        "stepIndex": decode_index,
                        "launchIndex": launch_index,
                        "symbol": "c",
                        "buffer": out,
                        "expectedSha256": None,
                    }
                )
            else:
                if kernel == "ple_proj":
                    state["ple_project"] = out
                    current = out
                elif name in {"q_proj", "k_proj", "v_proj"}:
                    state[name[0]] = out
                    state[f"{name[0]}_cols"] = matrix_n
                elif name in {"gate_proj", "up_proj"}:
                    state[name] = out
                else:
                    current = out
        elif kernel in PREFILL_Q4K_GEMV_KERNELS:
            matrix_n, matrix_k = weight_matrix_dims(weight_key)
            if name in {"q_proj", "k_proj", "v_proj"}:
                source = state.get("attn_norm", current)
            elif name in {"gate_proj", "up_proj"}:
                source = state.get("ffn_norm", current)
            elif name == "down_proj":
                source = state.get("activation", current)
            else:
                source = current
            add_input(
                "activation",
                source,
                "activation",
                "activation_router",
                matrixCols=matrix_k,
            )
            add_input("weight", f"weight:{step.get('weightKey')}", "weight", "weights")
            add_output(
                "output",
                out,
                "logits" if is_lm_head else "activation",
                f"{kernel}.output",
                matrixCols=matrix_n,
            )
            if is_lm_head:
                decode_index = int(step.get("tokenIndex") or 0)
                last_logits = out
                last_logits_launch_index = launch_index
                transcript_emitters.append(
                    {
                        "kind": "logits_digest",
                        "stepIndex": decode_index,
                        "launchIndex": launch_index,
                        "symbol": "output",
                        "buffer": out,
                        "expectedSha256": None,
                    }
                )
            else:
                if name in {"q_proj", "k_proj", "v_proj"}:
                    state[name[0]] = out
                    state[f"{name[0]}_cols"] = matrix_n
                elif name in {"gate_proj", "up_proj"}:
                    state[name] = out
                    current = out
                else:
                    current = out
        elif kernel in {"gemv", *LM_HEAD_KERNELS}:
            if name in {"q_proj", "k_proj", "v_proj"}:
                source = state.get("attn_norm", current)
            elif name in {"gate_proj", "up_proj"}:
                source = state.get("ffn_norm", current)
            elif name == "down_proj":
                source = state.get("activation", current)
            else:
                source = current
            add_input("activation", source, "activation", "activation_router")
            add_input("weight", f"weight:{weight_key}", "weight", "weights")
            add_output(
                "output",
                out,
                "logits" if is_lm_head else "activation",
                f"{kernel}.output",
            )
            if name in {"q_proj", "k_proj", "v_proj"}:
                state[name[0]] = out
            elif name in {"gate_proj", "up_proj"}:
                state[name] = out
            if is_lm_head:
                decode_index = int(step.get("tokenIndex") or 0)
                last_logits = out
                last_logits_launch_index = launch_index
                transcript_emitters.append(
                    {
                        "kind": "logits_digest",
                        "stepIndex": decode_index,
                        "launchIndex": launch_index,
                        "symbol": "output",
                        "buffer": out,
                        "expectedSha256": None,
                    }
                )
            else:
                if name not in {
                    "q_proj",
                    "k_proj",
                    "v_proj",
                    "gate_proj",
                    "up_proj",
                }:
                    current = out
        elif kernel in {"rmsnorm", "ple_rmsnorm"}:
            norm_input = (
                state.get("ple_project", current)
                if kernel == "ple_rmsnorm"
                else current
            )
            if kernel == "ple_rmsnorm" and str(weight_key or "") in disabled_weight_keys:
                state["ple_norm"] = norm_input
                current = norm_input
                elide_operation(
                    "architecture_disabled_session_input",
                    input_buffer=norm_input,
                )
                return
            add_input("input", norm_input, "activation", "activation_router")
            add_input("weight", f"weight:{step.get('weightKey')}", "weight", "weights")
            add_output("output", out, "activation", f"{kernel}.output")
            if kernel == "ple_rmsnorm":
                state["ple_norm"] = out
            if name == "input_norm":
                state["residual_base"] = current
                state["attn_norm"] = out
            elif name == "post_attn_norm":
                state["ffn_residual_base"] = current
                state["ffn_norm"] = out
            elif name == "q_norm":
                state["q"] = out
            elif name == "k_norm":
                state["k"] = out
            current = out
        elif kernel in {"rope", "rope_partial"}:
            source_key = "q" if name == "rope_q" else "k"
            source = state.get(source_key, current)
            source_cols = state.get(f"{source_key}_cols")
            add_input(
                "input",
                source,
                "activation",
                "activation_router",
                matrixCols=source_cols,
            )
            add_input(
                "cos_table",
                "state:rope_cos_table",
                "position_encoding",
                "runtime_state",
            )
            add_input(
                "sin_table",
                "state:rope_sin_table",
                "position_encoding",
                "runtime_state",
            )
            add_output(
                "input",
                out,
                "activation",
                "rope.output",
                matrixCols=source_cols,
            )
            state[source_key] = out
            if source_cols is not None:
                state[f"{source_key}_cols"] = source_cols
            if name not in {"rope_q", "rope_k"}:
                current = out
        elif kernel in {
            "attn_small",
            "attn_decode",
            "attn_decode_sliding",
            "attn_prefill_kv_axis_sharded",
        }:
            query = state.get("q", current)
            key = state.get("kv_key") or state.get("k", "state:kv_cache:key")
            val = state.get("kv_val") or state.get("v", "state:kv_cache:value")
            query_cols = state.get("q_cols")
            key_cols = state.get("k_cols")
            val_cols = state.get("v_cols")
            value_symbol = (
                "value"
                if kernel == "attn_prefill_kv_axis_sharded"
                else "val"
            )
            add_input(
                "query",
                query,
                "activation",
                "activation_router",
                matrixCols=query_cols,
            )
            add_input(
                "key",
                key,
                routed_tensor_role(key),
                "kv_or_activation_router",
                matrixCols=key_cols,
            )
            add_input(
                value_symbol,
                val,
                routed_tensor_role(val),
                "kv_or_activation_router",
                matrixCols=val_cols,
            )
            if kernel in {"attn_decode", "attn_decode_sliding"}:
                add_input(
                    "position",
                    "state:decode_position",
                    "position",
                    "runtime_state",
                )
                add_input(
                    "sliding_window",
                    "state:sliding_window",
                    "position",
                    "runtime_state",
                )
            add_output(
                "output",
                out,
                "activation",
                f"{kernel}.output",
                matrixCols=query_cols,
            )
            if query_cols is not None:
                state["attention_cols"] = query_cols
            kv_operations.append(
                {
                    "launchIndex": launch_index,
                    "phase": step["phase"],
                    "decodeStepIndex": step.get("tokenIndex"),
                    "layerIndex": layer_idx,
                    "attentionKernel": kernel,
                    "write": {
                        "keyBuffer": state.get("k", key),
                        "valueBuffer": state.get("v", val),
                        "cacheBuffer": "state:kv_cache",
                        "positionSource": "decode_position",
                    },
                    "read": {
                        "keyBuffer": key,
                        "valueBuffer": val,
                        "cacheBuffer": "state:kv_cache",
                        "slidingWindowSource": (
                            "sliding_window"
                            if kernel == "attn_decode"
                            else "prefill_full_context"
                        ),
                    },
                }
            )
            current = out
        elif kernel in {"kv_write", "kv_write_shared"}:
            key_cache = (
                f"state:kv_cache:layer{layer_idx}:"
                f"token{step.get('tokenIndex')}:key"
            )
            val_cache = (
                f"state:kv_cache:layer{layer_idx}:"
                f"token{step.get('tokenIndex')}:val"
            )
            add_input(
                "key_proj",
                state.get("k", current),
                "activation",
                "activation_router",
            )
            add_input(
                "val_proj",
                state.get("v", current),
                "activation",
                "activation_router",
            )
            add_input("position", "state:decode_position", "position", "runtime_state")
            add_output(
                "key_cache",
                key_cache,
                "kv_cache",
                f"{kernel}.key_cache",
            )
            add_output(
                "val_cache",
                val_cache,
                "kv_cache",
                f"{kernel}.val_cache",
            )
            state["kv_key"] = key_cache
            state["kv_val"] = val_cache
        elif kernel == "ssm_conv1d_depthwise":
            add_input("input", current, "activation", "activation_router")
            add_input("weight", f"weight:{weight_key}", "weight", "weights")
            add_input("bias", f"weight:{weight_key}:bias", "weight", "weights")
            add_output("output", out, "activation", f"{kernel}.output")
            current = out
        elif kernel == "ssm_l2_normalize":
            add_input("input", current, "activation", "activation_router")
            add_output("output", out, "activation", f"{kernel}.output")
            if name == "ssm_q_l2_normalize":
                state["q"] = out
            elif name == "ssm_k_l2_normalize":
                state["k"] = out
            current = out
        elif kernel == "ssm_linear_attention":
            add_input("query", state.get("q", current), "activation", "activation_router")
            add_input("key", state.get("k", current), "activation", "activation_router")
            add_input("value", state.get("v", current), "activation", "activation_router")
            add_input("gate", current, "activation", "activation_router")
            add_input(
                "linear_state",
                f"state:linear_attention:layer{layer_idx}",
                "linear_attention_state",
                "runtime_state",
            )
            add_output("output", out, "activation", f"{kernel}.output")
            current = out
        elif kernel in {"o_gate", "silu_gated", "gelu_gated", "sigmoid_gated"}:
            input_source = state.get("up_proj") if kernel == "gelu_gated" else current
            if not input_source:
                input_source = current
            gate_source = state.get("gate_proj") or current
            add_input("gate", gate_source, "activation", "activation_router")
            add_input("input", input_source, "activation", "activation_router")
            add_output("output", out, "activation", f"{kernel}.output")
            if name == "activation":
                state["activation"] = out
            current = out
        elif kernel == "residual":
            residual = (
                state.get("residual_base")
                if name == "attn_residual"
                else state.get("ffn_residual_base")
            )
            if not residual:
                residual = "activation:missing:residual"
                blockers.append(f"launch[{launch_index}].residual_base_missing:{name}")
            add_input("input", current, "activation", "activation_router")
            add_input("residual", residual, "activation", "activation_router")
            add_output("output", out, "activation", "residual.output")
            current = out
        elif kernel == "ple_residual":
            add_input("u", "state:decode_position", "position", "runtime_state")
            add_input(
                "input",
                state.get("ple_norm", current),
                "activation",
                "activation_router",
            )
            add_output("output", out, "activation", "ple_residual.output")
            state["ple_modulate"] = out
            current = out
        elif kernel == "gelu":
            gelu_input = state.get("gate_proj") or current
            add_input("input", gelu_input, "activation", "activation_router")
            add_output("output", out, "activation", "gelu.output")
            state["activation"] = out
            current = out
        elif kernel == "sample":
            if not last_logits:
                blockers.append(f"launch[{launch_index}].sample_logits_producer_missing")
                last_logits = "logits:missing"
            token_buffer = f"tokens:decode:{launch_index:04d}"
            add_input("logits", last_logits, "logits", "transcript_capture")
            add_output("tokens", token_buffer, "generated_tokens", "sample.output")
            transcript_emitters.append(
                {
                    "kind": "generated_token",
                    "stepIndex": int(step.get("tokenIndex") or 0),
                    "launchIndex": launch_index,
                    "symbol": "tokens",
                    "buffer": token_buffer,
                    "logitsBuffer": last_logits,
                    "logitsLaunchIndex": last_logits_launch_index,
                }
            )
            decode_index = int(step.get("tokenIndex") or 0)
            if decode_index + 1 < int(dispatch_plan["decodeTokenCount"]):
                sample_feedback_edges.append(
                    {
                        "fromLaunchIndex": launch_index,
                        "tokenBuffer": token_buffer,
                        "toDecodeStepIndex": decode_index + 1,
                    }
                )
            last_generated_token = token_buffer
        else:
            add_input("input", current, "activation", "activation_router")
            add_output("output", out, "activation", f"{kernel}.output")
            current = out

        symbols: dict[str, dict[str, Any]] = {}
        for item in [*inputs, *outputs]:
            append_symbol_table_entry(symbols, item)
        launches.append(
            {
                "launchIndex": launch_index,
                "phase": step["phase"],
                "phaseLaunchIndex": launch_index,
                "kernelName": kernel,
                "kernelPattern": PREFILL_Q4K_GEMV_PATTERN
                if kernel in PREFILL_Q4K_GEMV_KERNELS
                else kernel,
                "repeat": 1,
                "operationName": name,
                "layerIndex": layer_idx,
                "decodeStepIndex": step.get("tokenIndex"),
                "weightKey": step.get("weightKey"),
                "inputs": inputs,
                "outputs": outputs,
                "symbols": symbols,
                "symbolDataflowPresent": True,
                "inputSymbolCount": len(inputs),
                "outputSymbolCount": len(outputs),
                "symbolTablePresent": True,
            }
        )

    for step in dispatch_plan.get("prefillSteps") or []:
        make_launch(step)
    for token in dispatch_plan.get("decodeByToken") or []:
        for step in token.get("steps") or []:
            make_launch(step)

    model_layers = int(runtime_config.get("modelConfig", {}).get("numLayers") or 0)
    covered_layers = sorted(
        {
            op.get("layerIndex")
            for op in kv_operations
            if isinstance(op.get("layerIndex"), int)
        }
    )
    expected_decode_steps = int(dispatch_plan["decodeTokenCount"])
    logits_emitters = [
        item for item in transcript_emitters if item["kind"] == "logits_digest"
    ]
    token_emitters = [
        item for item in transcript_emitters if item["kind"] == "generated_token"
    ]
    if len(logits_emitters) != expected_decode_steps:
        blockers.append(
            f"transcript_logits_emitter_count:{len(logits_emitters)}!={expected_decode_steps}"
        )
    if len(token_emitters) != expected_decode_steps:
        blockers.append(
            f"transcript_token_emitter_count:{len(token_emitters)}!={expected_decode_steps}"
        )
    transcript_status = (
        "bound"
        if expected_decode_steps > 0
        and len(logits_emitters) == expected_decode_steps
        and len(token_emitters) == expected_decode_steps
        else "blocked_missing_decode_emitters"
    )
    status = "bound" if not blockers else "blocked"
    return {
        "status": status,
        "blockers": blockers,
        "runtimeExpansion": {
            "decodeIterationCount": int(dispatch_plan["decodeTokenCount"]),
            "runtimeLaunchCount": len(launches),
            "elidedOperationCount": len(elided_operations),
        },
        "elidedOperations": elided_operations,
        "activationRouting": {
            "status": "bound",
            "bufferCount": len(lifetimes),
            "routedBufferCount": len(lifetimes),
            "lifetimes": sorted(lifetimes.values(), key=lambda item: item["buffer"]),
        },
        "kvCacheSchedule": {
            "status": "bound" if kv_operations else "blocked_missing_kv_operations",
            "cacheWriteCount": len(kv_operations),
            "cacheReadCount": len(kv_operations),
            "layerCoverage": {
                "layerCount": model_layers,
                "coveredLayerCount": len(covered_layers),
                "coveredLayers": covered_layers,
            },
            "operations": kv_operations,
        },
        "sampleFeedback": {
            "status": (
                "bound"
                if len(sample_feedback_edges)
                == max(0, int(dispatch_plan["decodeTokenCount"]) - 1)
                else "blocked"
            ),
            "edges": sample_feedback_edges,
        },
        "transcriptCaptureSchedule": {
            "status": transcript_status,
            "expectedActualDecodeSteps": expected_decode_steps,
            "logitsEmitterCount": len(logits_emitters),
            "tokenEmitterCount": len(token_emitters),
            "emitters": transcript_emitters,
        },
        "launches": launches,
    }


def host_io_layout_from_buffer_plan(
    buffer_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    layout: list[dict[str, Any]] = []
    for buffer in buffer_plan.get("buffers") or []:
        if not isinstance(buffer, dict):
            continue
        storage = str(buffer.get("storageClass") or "")
        if storage not in {
            "shared_input",
            "captured_output",
            "persistent_state",
            "external_weight",
        }:
            continue
        layout.append(
            {
                "buffer": buffer.get("buffer"),
                "bufferRole": buffer.get("role"),
                "storageClass": storage,
                "dtype": buffer.get("dtype"),
                "plannedElementCount": buffer.get("plannedElementCount"),
                "plannedByteLength": buffer.get("plannedByteLength"),
            }
        )
    return layout


def _output_bindings_by_launch(
    execution_plan: dict[str, Any],
) -> dict[int, dict[str, dict[str, Any]]]:
    bindings: dict[int, dict[str, dict[str, Any]]] = {}
    for launch in execution_plan.get("launches") or []:
        if not isinstance(launch, dict):
            continue
        launch_index = int(launch.get("launchIndex") or 0)
        by_symbol: dict[str, dict[str, Any]] = {}
        for item in launch.get("outputBindings") or []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "")
            if symbol:
                by_symbol[symbol] = item
        bindings[launch_index] = by_symbol
    return bindings


def _array_file_digest(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "byteLength": len(data),
    }


def _read_first_u32(path: Path) -> int | None:
    values = np.load(path, allow_pickle=False).astype(np.uint32, copy=False).ravel()
    if values.size == 0:
        return None
    return int(values[0])


def build_runtime_transcript(
    *,
    session_dir: Path,
    runtime: dict[str, Any],
    execution_plan: dict[str, Any],
    requested_decode_steps: int,
    artifact_prefix: str = SESSION_ARTIFACT_PREFIX,
) -> dict[str, Any]:
    output_bindings = _output_bindings_by_launch(execution_plan)
    generated_tokens: list[dict[str, Any]] = []
    logits_digests: list[dict[str, Any]] = []
    kv_digests: list[dict[str, Any]] = []
    lm_head_dispatches: list[dict[str, Any]] = []

    for receipt in runtime.get("launches") or []:
        if not isinstance(receipt, dict):
            continue
        launch_index = int(receipt.get("launchIndex") or 0)
        bindings = output_bindings.get(launch_index, {})
        for output in receipt.get("outputs") or []:
            if not isinstance(output, dict):
                continue
            symbol = str(output.get("symbol") or "")
            binding = bindings.get(symbol) or {}
            role = str(binding.get("role") or "")
            path = Path(str(output.get("path") or ""))
            if not path.is_file():
                continue
            digest = _array_file_digest(path)
            record = {
                "launchIndex": launch_index,
                "symbol": symbol,
                "buffer": binding.get("buffer"),
                **digest,
            }
            if role == "generated_tokens":
                record["tokenId"] = _read_first_u32(path)
                generated_tokens.append(record)
            elif role == "logits":
                record["dispatchMode"] = str(
                    receipt.get("dispatchMode") or "monolithic_full_fabric"
                )
                if isinstance(receipt.get("sessionTileIdentity"), dict):
                    record["sessionTileIdentity"] = receipt[
                        "sessionTileIdentity"
                    ]
                if isinstance(receipt.get("tileCoverage"), dict):
                    record["tileCoverage"] = receipt["tileCoverage"]
                logits_digests.append(record)
                lm_head_dispatches.append(
                    {
                        "launchIndex": launch_index,
                        "dispatchMode": record["dispatchMode"],
                        "buffer": binding.get("buffer"),
                        "sessionTileIdentity": record.get(
                            "sessionTileIdentity",
                            {},
                        ),
                    }
                )
            elif role == "kv_cache":
                kv_digests.append(record)

    transcript = {
        "schemaVersion": 1,
        "artifactKind": f"{artifact_prefix}_csl_runtime_transcript",
        "status": "output_ready",
        "requestedDecodeSteps": requested_decode_steps,
        "actualDecodeSteps": len(generated_tokens),
        "generatedTokenIds": [item.get("tokenId") for item in generated_tokens],
        "generatedTokenDigests": generated_tokens,
        "logitsDigests": logits_digests,
        "lmHeadDispatches": lm_head_dispatches,
        "kvCache": {
            "mode": "runtime_captured",
            "digestCount": len(kv_digests),
            "digests": kv_digests,
        },
    }
    transcript_path = session_dir / "transcript.json"
    write_json(transcript_path, transcript)
    return {
        "path": rel(transcript_path),
        "sha256": sha256_file(transcript_path),
        "payload": transcript,
    }


def build_real_session_runtime(
    args: argparse.Namespace,
    dispatch_plan: dict[str, Any],
    weight_plan: dict[str, Any],
) -> dict[str, Any]:
    session_dir = resolve(args.session_out_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    plan = load_json(args.simulator_plan)
    runtime_config = load_json(args.runtime_config)
    runtime_config["mode"] = "sdk-runtime-command"
    runtime_config["modelConfig"] = {
        **(runtime_config.get("modelConfig") or {}),
        "numLayers": int(weight_plan.get("modelLayerCount") or 0),
    }
    state_buffers = runtime_config.setdefault("stateBuffers", [])
    existing_state_names = {
        str(item.get("name") or "")
        for item in state_buffers
        if isinstance(item, dict)
    }
    for name, role in (
        ("linear_attention", "linear_attention_state"),
        ("sliding_window", "position"),
    ):
        if name not in existing_state_names:
            state_buffers.append({"name": name, "role": role})
    mappings = build_runtime_weight_mappings(
        manifest_path=args.source_doppler_manifest,
        weight_plan=weight_plan,
        runtime_config=runtime_config,
    )
    runtime_config["weightMappings"] = mappings["mappings"]
    runtime_config["weightIdentity"] = mappings["identity"]
    normalized = normalize_smoke_execution(
        smoke_config_path=args.smoke_config,
        out_dir=session_dir,
        model_layer_count=int(weight_plan.get("modelLayerCount") or 0),
    )
    reference = build_reference_request(args=args, session_dir=session_dir)
    scheduler = build_real_session_scheduler(
        dispatch_plan=dispatch_plan,
        runtime_config=runtime_config,
        architecture_disabled_weight_keys=[
            str(item)
            for item in weight_plan.get("architectureDisabledWeightKeys") or []
        ],
        per_layer_input_block_enabled=bool(
            (weight_plan.get("perLayerInputBlock") or {}).get("enabled", True)
        ),
    )
    scheduler_record = {
        "path": str(args.host_plan),
        "present": True,
        "runtimeScheduler": scheduler,
        "launchesCarrySymbolDataflow": bool(scheduler.get("launches")),
    }
    manifest_preflight = {
        "status": "passed",
        "blockers": [],
        "source": f"{session_artifact_prefix(args)}_session_runtime_contract",
    }
    validator = validate_hostplan_executor(
        plan=plan,
        compile_root=resolve(args.compile_root),
        runtime_config=runtime_config,
        scheduler={"hostPlan": scheduler_record},
        manifest_preflight=manifest_preflight,
    )
    execution_plan = build_hostplan_execution_plan(
        plan=plan,
        compile_root=resolve(args.compile_root),
        runtime_config=runtime_config,
        scheduler={"hostPlan": scheduler_record},
        executor_validator=validator,
    )
    runtime_config["hostIoLayout"] = host_io_layout_from_buffer_plan(
        execution_plan.get("bufferPlan") or {}
    )
    runtime_config_path = session_dir / "runtime-config.json"
    execution_plan_path = session_dir / "hostplan-execution-plan.json"
    scheduler_path = session_dir / "runtime-scheduler.json"
    write_json(runtime_config_path, runtime_config)
    write_json(scheduler_path, scheduler)
    write_json(execution_plan_path, execution_plan)
    checkpoint_dir = optional_resolved_path(args, "checkpoint_dir")
    resume_dir = (
        optional_resolved_path(args, "resume_from_checkpoint")
        if not bool(getattr(args, "ignore_checkpoint", False))
        else None
    )
    result: dict[str, Any] = {
        "requested": bool(args.execute),
        "status": "planned",
        "sessionDir": rel(session_dir),
        "runtimeConfigPath": rel(runtime_config_path),
        "runtimeConfigSha256": sha256_file(runtime_config_path),
        "normalizedExecution": {
            "path": rel(Path(normalized["path"])),
            "sha256": normalized["sha256"],
        },
        "runtimeSchedulerPath": rel(scheduler_path),
        "executionPlanPath": rel(execution_plan_path),
        "weightMappingStatus": mappings["identity"],
        "hostIoLayoutCount": len(runtime_config["hostIoLayout"]),
        "schedulerStatus": scheduler.get("status"),
        "schedulerBlockers": scheduler.get("blockers") or [],
        "executorValidatorStatus": validator.get("status"),
        "executorValidatorBlockers": validator.get("blockers") or [],
        "executionPlanStatus": execution_plan.get("status"),
        "executionPlanBlockers": execution_plan.get("blockers") or [],
        "sampleFeedback": scheduler.get("sampleFeedback") or {},
        "checkpoint": {
            "checkpointDir": rel(checkpoint_dir) if checkpoint_dir else "",
            "resumeFromCheckpoint": rel(resume_dir) if resume_dir else "",
            "ignoreCheckpoint": bool(getattr(args, "ignore_checkpoint", False)),
            "allowRunnerVersionDrift": bool(
                getattr(args, "allow_checkpoint_runner_drift", False)
            ),
        },
    }
    blockers = [
        *[f"scheduler:{item}" for item in scheduler.get("blockers") or []],
        *[f"executor_validator:{item}" for item in validator.get("blockers") or []],
        *[f"execution_plan:{item}" for item in execution_plan.get("blockers") or []],
    ]
    if mappings["identity"]["missingWeightCount"]:
        blockers.append("runtime_weight_mappings_incomplete")
    if blockers:
        result["status"] = "blocked"
        result["blockers"] = blockers
        return result
    if not args.execute:
        result["status"] = "ready_not_executed"
        result["blockers"] = ["execution_not_requested"]
        return result

    progress_path = session_dir / "progress.jsonl"
    bootstrap = execute_hostplan_runtime_bootstrap(
        execution_plan=execution_plan,
        progress_path=progress_path,
        cmaddr=args.cmaddr.strip() or None,
    )
    result["bootstrap"] = bootstrap
    if bootstrap.get("status") != "ready_for_tensor_movement":
        result["status"] = "blocked"
        result["blockers"] = [
            f"bootstrap:{item}" for item in bootstrap.get("blockers") or ["unknown"]
        ]
        return result
    identity = compute_checkpoint_identity(
        plan=plan,
        plan_path=resolve(args.simulator_plan),
        runtime_config=runtime_config,
        runtime_config_path=runtime_config_path,
        export=reference,
        reference_export_path=session_dir / "reference-request.json",
        runner_version=sha256_file(Path(__file__)),
    )
    result["checkpoint"]["identitySha256"] = sha256_json(identity)
    resume_state = None
    if resume_dir is not None:
        try:
            resume_state = load_checkpoint(
                checkpoint_dir=resume_dir,
                identity=identity,
                allow_runner_version_drift=bool(
                    getattr(args, "allow_checkpoint_runner_drift", False)
                ),
            )
            result["checkpoint"]["resumeStatus"] = "loaded"
            result["checkpoint"]["resumeStartIndex"] = resume_state.start_index
            result["checkpoint"]["resumeBufferCount"] = len(
                resume_state.buffer_files
            )
        except CheckpointMissingError:
            result["checkpoint"]["resumeStatus"] = "missing_treated_as_empty"
        except CheckpointError as exc:
            result["status"] = "blocked"
            result["blockers"] = [f"checkpoint:{getattr(exc, 'code', 'error')}"]
            result["checkpoint"]["resumeStatus"] = "rejected"
            result["checkpoint"]["resumeError"] = str(exc)
            return result
    if checkpoint_dir is not None:
        try:
            init_checkpoint(
                checkpoint_dir,
                identity,
                allow_runner_version_drift=bool(
                    getattr(args, "allow_checkpoint_runner_drift", False)
                ),
            )
            result["checkpoint"]["checkpointStatus"] = "initialized"
        except CheckpointError as exc:
            result["status"] = "blocked"
            result["blockers"] = [f"checkpoint:{getattr(exc, 'code', 'error')}"]
            result["checkpoint"]["checkpointStatus"] = "rejected"
            result["checkpoint"]["checkpointError"] = str(exc)
            return result
    runtime = execute_hostplan_runtime(
        bootstrap=bootstrap,
        export=reference,
        progress_path=progress_path,
        cmaddr=args.cmaddr.strip() or None,
        trace_path=session_dir / "trace.json",
        checkpoint_dir=checkpoint_dir,
        resume_state=resume_state,
        stop_after_launch=args.stop_after_launch,
        launch_timeout_seconds=getattr(
            args,
            "launch_timeout_seconds",
            DEFAULT_LAUNCH_TIMEOUT_SECONDS,
        ),
        session_lm_head_dispatch_mode=getattr(
            args,
            "session_lm_head_dispatch_mode",
            "monolithic",
        ),
        session_lm_head_tile_width=int(
            getattr(args, "session_lm_head_tile_width", 120)
        ),
        session_lm_head_tile_jobs=int(
            getattr(args, "session_lm_head_tile_jobs", 1)
        ),
        session_embed_roi_jobs=int(getattr(args, "session_embed_roi_jobs", 1)),
        session_embed_roi_hidden_per_pe=int(
            getattr(args, "session_embed_roi_hidden_per_pe", 0)
        ),
        session_prefill_q4k_gemv_jobs=int(
            getattr(args, "session_prefill_q4k_gemv_jobs", 1)
        ),
        session_prefill_q4k_gemv_output_pe_rows=int(
            getattr(args, "session_prefill_q4k_gemv_output_pe_rows", 1)
        ),
        session_ple_proj_dispatch_mode=str(
            getattr(args, "session_ple_proj_dispatch_mode", "monolithic_summa")
            or "monolithic_summa"
        ),
        session_lm_head_batch_runtime=bool(
            getattr(args, "session_lm_head_batch_runtime", False)
        ),
        session_lm_head_batch_runtime_step_budget=int(
            getattr(args, "session_lm_head_batch_runtime_step_budget", 16)
        ),
        session_lm_head_tile_dispatch_budget=int(
            getattr(args, "session_lm_head_tile_dispatch_budget", 0)
        ),
    )
    result["runtime"] = runtime
    runtime_status = str(runtime.get("status") or "")
    if runtime_status == "succeeded":
        result["status"] = "output_ready"
    elif runtime_status == "stopped_at_checkpoint":
        result["status"] = "checkpoint_stopped"
        result["blockers"] = ["execution_stopped_at_checkpoint"]
        result["checkpoint"] = {
            "stopAfterLaunch": int(args.stop_after_launch),
            "completedLaunchCount": len(runtime.get("launches") or []),
        }
    else:
        result["status"] = "blocked"
    if result["status"] == "blocked":
        runtime_blockers = runtime.get("blockers") or []
        if not runtime_blockers:
            runtime_blockers = [runtime_status or "unknown"]
        result["blockers"] = [
            f"runtime:{item}" for item in runtime_blockers
        ]
    elif result["status"] == "output_ready":
        transcript = build_runtime_transcript(
            session_dir=session_dir,
            runtime=runtime,
            execution_plan=execution_plan,
            requested_decode_steps=int(args.decode_token_count),
            artifact_prefix=session_artifact_prefix(args),
        )
        result["runtimeTranscriptPath"] = transcript["path"]
        result["runtimeTranscriptSha256"] = transcript["sha256"]
        result["runtimeTranscript"] = {
            key: transcript["payload"].get(key)
            for key in (
                "status",
                "requestedDecodeSteps",
                "actualDecodeSteps",
                "generatedTokenIds",
                "logitsDigests",
                "lmHeadDispatches",
                "kvCache",
            )
        }
        actual_steps = int(
            transcript["payload"].get("actualDecodeSteps") or 0
        )
        if actual_steps != int(args.decode_token_count):
            result["status"] = "blocked"
            result["blockers"] = [
                "runtime_transcript_decode_count_mismatch:"
                f"{actual_steps}!={int(args.decode_token_count)}"
            ]
    return result
