#!/usr/bin/env python3
"""HostPlan scheduler synthesis for the INT4 PLE CSL transcript runner."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
LAYER_STEP_SCAN_WINDOW = 8
LAYER_WEIGHT_RE = re.compile(r"^layer\.(?P<layer>[0-9]+)\.")
ATTENTION_KERNELS = frozenset({"attn_head256", "attn_head512", "attn_decode"})
PREFILL_Q4K_GEMV_PATTERN = "prefill_q4k_gemv"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        if not isinstance(value, str) or not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def reference_decode_steps(reference: dict[str, Any] | None) -> int:
    if not isinstance(reference, dict):
        return 0
    return int(reference.get("actualDecodeSteps") or 0)


def expand_runtime_launches(
    launches: list[dict[str, Any]],
    reference: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Expand the single HostPlan decode phase into runtime decode iterations."""

    decode_steps = reference_decode_steps(reference)
    if decode_steps <= 1:
        expanded: list[dict[str, Any]] = []
        for launch in launches:
            copied = dict(launch)
            copied["hostPlanLaunchIndex"] = int(copied.get("launchIndex") or 0)
            copied["runtimeLaunchIndex"] = len(expanded)
            copied["launchIndex"] = len(expanded)
            if copied.get("_phase") == "decode" and decode_steps == 1:
                copied["decodeStepIndex"] = 0
            expanded.append(copied)
        return expanded

    prefill = [item for item in launches if item.get("_phase") == "prefill"]
    decode = [item for item in launches if item.get("_phase") == "decode"]
    other = [
        item
        for item in launches
        if item.get("_phase") not in {"prefill", "decode"}
    ]

    expanded = []

    def append_launch(raw: dict[str, Any], decode_step: int | None) -> None:
        copied = dict(raw)
        copied["hostPlanLaunchIndex"] = int(copied.get("launchIndex") or 0)
        copied["runtimeLaunchIndex"] = len(expanded)
        copied["launchIndex"] = len(expanded)
        if decode_step is not None:
            copied["decodeStepIndex"] = decode_step
        expanded.append(copied)

    for launch in prefill:
        append_launch(launch, None)
    for decode_step in range(decode_steps):
        for launch in decode:
            append_launch(launch, decode_step)
    for launch in other:
        append_launch(launch, None)
    return expanded


def resolve_artifact_path(anchor: Path, raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    anchored = anchor.parent / candidate
    if anchored.is_file():
        return anchored
    repo_relative = REPO_ROOT / candidate
    if repo_relative.is_file():
        return repo_relative
    return anchored


def normalized_execution_path(plan_path: Path) -> Path:
    return plan_path.parent / "normalized-execution-v1.json"


def load_normalized_execution(plan_path: Path) -> dict[str, Any]:
    path = normalized_execution_path(plan_path)
    if not path.is_file():
        return {
            "present": False,
            "path": str(path),
            "steps": [],
            "sha256": "missing",
        }
    value = load_json(path)
    steps = value.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    return {
        "present": True,
        "path": str(path),
        "sha256": sha256_file(path),
        "modelConfig": value.get("modelConfig") or {},
        "steps": steps,
    }


def weight_index(runtime_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in runtime_config.get("weightMappings") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("weightKey") or item.get("tensor")
        if not isinstance(key, str) or not key:
            continue
        result[key] = {
            "buffer": f"weight:{key}",
            "weightKey": key,
            "tensor": item.get("tensor") or item.get("tensorName") or key,
            "peBuffer": item.get("peBuffer") or key,
            "dtype": item.get("dtype", "unknown"),
            "shape": item.get("shape") or [],
            "byteSize": int(item.get("byteSize") or 0),
            "path": item.get("path") or item.get("shard") or "",
            "sha256": item.get("sha256", ""),
            "role": item.get("role", "weight"),
        }
    return result


def layer_index_from_weight_key(weight_key: Any) -> int | None:
    if not isinstance(weight_key, str):
        return None
    match = LAYER_WEIGHT_RE.match(weight_key)
    if match is None:
        return None
    return int(match.group("layer"))


def infer_step_layer_index(
    phase_steps: list[dict[str, Any]],
    phase_index: int,
) -> int | None:
    current = phase_steps[phase_index]
    name = str(current.get("name") or "")
    if name in {"embed", "final_norm", "lm_head", "lm_head_prefill", "sample"}:
        return None
    current_layer = layer_index_from_weight_key(current.get("weightsKey"))
    if current_layer is not None:
        return current_layer
    for offset in range(1, LAYER_STEP_SCAN_WINDOW + 1):
        next_index = phase_index + offset
        if next_index < len(phase_steps):
            next_name = str(phase_steps[next_index].get("name") or "")
            if next_name in {"final_norm", "lm_head", "lm_head_prefill", "sample"}:
                break
            next_layer = layer_index_from_weight_key(
                phase_steps[next_index].get("weightsKey")
            )
            if next_layer is not None:
                return next_layer
        prev_index = phase_index - offset
        if prev_index >= 0:
            prev_name = str(phase_steps[prev_index].get("name") or "")
            if prev_name in {"embed", "final_norm", "lm_head", "lm_head_prefill"}:
                continue
            prev_layer = layer_index_from_weight_key(
                phase_steps[prev_index].get("weightsKey")
            )
            if prev_layer is not None:
                return prev_layer
    return None


def activation_buffer(
    phase: str,
    launch_index: int,
    name: str,
    layer_index: int | None,
) -> str:
    layer = "global" if layer_index is None else f"layer{layer_index}"
    return f"activation:{phase}:{launch_index:04d}:{layer}:{name}"


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


def weight_binding(
    symbol: str,
    weight_key: Any,
    weights: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    if not isinstance(weight_key, str) or not weight_key:
        return (
            binding(
                symbol=symbol,
                buffer="weight:missing",
                role="weight",
                access="read",
                source="missing_weight_key",
            ),
            f"missing weight key for symbol {symbol}",
        )
    item = weights.get(weight_key)
    if item is None:
        return (
            binding(
                symbol=symbol,
                buffer=f"weight:{weight_key}",
                role="weight",
                access="read",
                source="runtime_config_weight_mapping",
                weightKey=weight_key,
                status="missing",
            ),
            f"runtime config is missing weight mapping {weight_key!r}",
        )
    return (
        binding(
            symbol=symbol,
            buffer=item["buffer"],
            role="weight",
            access="read",
            source="runtime_config_weight_mapping",
            weightKey=item["weightKey"],
            tensor=item["tensor"],
            dtype=item["dtype"],
            shape=item["shape"],
            byteSize=item["byteSize"],
            sha256=item["sha256"],
        ),
        None,
    )


def weight_binding_candidates(
    symbol: str,
    weight_keys: list[str],
    weights: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    candidates = [key for key in dict.fromkeys(weight_keys) if key]
    for key in candidates:
        if key in weights:
            return weight_binding(symbol, key, weights)
    missing_key = candidates[0] if candidates else ""
    item, blocker = weight_binding(symbol, missing_key, weights)
    item["weightCandidates"] = candidates
    if blocker is None:
        blocker = f"runtime config is missing weight mapping from candidates {candidates!r}"
    return item, blocker


def rmsnorm_weight_key_candidates(op_name: str, layer_index: int | None, raw_key: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(raw_key, str) and raw_key:
        keys.append(raw_key)
    if layer_index is None:
        if op_name == "final_norm":
            keys.extend(["norm", "model.norm", "model.norm.weight"])
        return keys
    layer_prefix = f"layer.{layer_index}"
    model_prefix = f"model.layers.{layer_index}"
    suffix_by_step = {
        "input_norm": "input_layernorm",
        "post_attn_norm": "post_attention_layernorm",
        "pre_ffn_norm": "pre_feedforward_layernorm",
        "post_ffn_norm": "post_feedforward_layernorm",
    }
    suffix = suffix_by_step.get(op_name)
    if suffix is None:
        return keys
    keys.extend(
        [
            f"{layer_prefix}.{suffix}",
            f"{layer_prefix}.{suffix}.weight",
            f"{model_prefix}.{suffix}",
            f"{model_prefix}.{suffix}.weight",
        ]
    )
    return keys


def state_buffer_names(runtime_config: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in runtime_config.get("stateBuffers") or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.add(item["name"])
    return names


def dedupe_bindings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            str(item.get("symbol", "")),
            str(item.get("buffer", "")),
            str(item.get("access", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def bind_launch_dataflow(
    *,
    record: dict[str, Any],
    normalized_step: dict[str, Any],
    layer_index: int | None,
    weights: dict[str, dict[str, Any]],
    states: set[str],
    scheduler_state: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    phase = str(record["phase"])
    launch_index = int(record["launchIndex"])
    kernel_name = str(record["kernelName"])
    kernel_pattern = str(record.get("kernelPattern") or "")
    op_name = str(normalized_step.get("name") or kernel_name)
    op = str(normalized_step.get("op") or kernel_name)
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    blockers: list[str] = []
    phase_state = scheduler_state.setdefault(
        phase,
        {
            "current": f"activation:{phase}:input",
            "layers": {},
            "last_logits": "",
        },
    )
    layers = phase_state.setdefault("layers", {})
    layer_key = "global" if layer_index is None else str(layer_index)
    layer_state = layers.setdefault(layer_key, {})

    def current_buffer() -> str:
        return str(phase_state.get("current") or f"activation:{phase}:input")

    def set_current(buffer: str) -> None:
        phase_state["current"] = buffer

    def next_buffer(name: str) -> str:
        return activation_buffer(phase, launch_index, name, layer_index)

    def add_weight(symbol: str) -> None:
        item, blocker = weight_binding(symbol, normalized_step.get("weightsKey"), weights)
        inputs.append(item)
        if blocker is not None:
            blockers.append(blocker)

    def add_rmsnorm_weight() -> None:
        item, blocker = weight_binding_candidates(
            "weight",
            rmsnorm_weight_key_candidates(
                op_name,
                layer_index,
                normalized_step.get("weightsKey"),
            ),
            weights,
        )
        inputs.append(item)
        if blocker is not None:
            blockers.append(blocker)

    if kernel_name == "embed":
        output = next_buffer(op_name)
        inputs.append(
            binding(
                symbol="indices",
                buffer="input:prompt_token_ids",
                role="tokenized_prompt",
                access="read",
                source="doppler_reference_input",
            )
        )
        add_weight("table")
        outputs.append(
            binding(
                symbol="output",
                buffer=output,
                role="activation",
                access="write",
                source="embed.output",
            )
        )
        set_current(output)
    elif kernel_name == "rmsnorm":
        source = current_buffer()
        if op_name == "input_norm" and layer_index is not None:
            layer_state["residual_base"] = source
        if op_name == "post_attn_norm" and layer_index is not None:
            layer_state["ffn_residual_base"] = source
        output = next_buffer(op_name)
        inputs.append(
            binding(
                symbol="input",
                buffer=source,
                role="activation",
                access="read",
                source="activation_router",
            )
        )
        add_rmsnorm_weight()
        outputs.append(
            binding(
                symbol="output",
                buffer=output,
                role="activation",
                access="write",
                source="rmsnorm.output",
            )
        )
        if op_name == "input_norm" and layer_index is not None:
            layer_state["attn_input"] = output
        elif op_name == "post_attn_norm" and layer_index is not None:
            layer_state["ffn_input"] = output
        set_current(output)
    elif kernel_name in {
        "tiled",
        "gemv",
        "lm_head_gemv",
        "lm_head_gemv_stable",
        "lm_head_prefill_stable",
        "q4_widetile",
        "q4_decode_gemv",
    } or kernel_pattern == PREFILL_Q4K_GEMV_PATTERN:
        is_lm_head = op_name in {"lm_head", "lm_head_prefill"} or (
            kernel_name
            in {"lm_head_gemv", "lm_head_gemv_stable", "lm_head_prefill_stable"}
        )
        is_tiled_kernel = kernel_name == "tiled" or (
            kernel_name == "tiled_31b" and kernel_pattern == "tiled_matmul"
        )
        if op_name in {"q_proj", "k_proj", "v_proj"} and layer_index is not None:
            source = str(layer_state.get("attn_input") or current_buffer())
        else:
            source = current_buffer()
        output = (
            f"logits:{phase}:{launch_index:04d}:{op_name}"
            if is_lm_head
            else next_buffer(op_name)
        )
        weight_item, weight_blocker = weight_binding(
            "b" if is_tiled_kernel else "weight",
            normalized_step.get("weightsKey"),
            weights,
        )
        weight_shape = weight_item.get("shape") if isinstance(weight_item, dict) else []
        matrix_n = None
        matrix_k = None
        if isinstance(weight_shape, list) and len(weight_shape) >= 2:
            try:
                matrix_n = int(weight_shape[0])
                matrix_k = int(weight_shape[1])
            except (TypeError, ValueError):
                matrix_n = None
                matrix_k = None
        activation_symbol = "a" if is_tiled_kernel else "activation"
        output_symbol = "c" if is_tiled_kernel else "output"
        inputs.append(
            binding(
                symbol=activation_symbol,
                buffer=source,
                role="activation",
                access="read",
                source="activation_router",
                matrixCols=matrix_k,
                opName=op_name,
            )
        )
        inputs.append(weight_item)
        if weight_blocker is not None:
            blockers.append(weight_blocker)
        outputs.append(
            binding(
                symbol=output_symbol,
                buffer=output,
                role="logits" if is_lm_head else "activation",
                access="write",
                source=f"{kernel_name}.output",
                matrixCols=matrix_n,
                opName=op_name,
                producerWeightShape=weight_shape,
            )
        )
        if layer_index is not None and op_name in {"q_proj", "k_proj", "v_proj"}:
            layer_state[op_name[0]] = output
            if matrix_n is not None:
                layer_state[f"{op_name[0]}_cols"] = matrix_n
        elif layer_index is not None and op_name == "o_proj":
            layer_state["attention_projected"] = output
            set_current(output)
        elif layer_index is not None and op_name == "gate_proj":
            layer_state["gate_proj"] = output
            set_current(output)
        elif layer_index is not None and op_name == "up_proj":
            layer_state["up_proj"] = output
            set_current(output)
        elif is_lm_head:
            phase_state["last_logits"] = output
        else:
            set_current(output)
    elif kernel_name == "rope":
        source_key = "q" if op_name == "rope_q" else "k"
        source = str(layer_state.get(source_key) or current_buffer())
        source_cols = layer_state.get(f"{source_key}_cols")
        output = next_buffer(op_name)
        inputs.append(
            binding(
                symbol="input",
                buffer=source,
                role="activation",
                access="read",
                source="activation_router",
                matrixCols=source_cols,
            )
        )
        inputs.append(
            binding(
                symbol="cos_table",
                buffer="state:rope_cos_table",
                role="position_encoding",
                access="read",
                source="runtime_constant",
            )
        )
        inputs.append(
            binding(
                symbol="sin_table",
                buffer="state:rope_sin_table",
                role="position_encoding",
                access="read",
                source="runtime_constant",
            )
        )
        outputs.append(
            binding(
                symbol="input",
                buffer=output,
                role="activation",
                access="write",
                source="rope.output",
                matrixCols=source_cols,
            )
        )
        if layer_index is not None:
            layer_state[source_key] = output
            if source_cols is not None:
                layer_state[f"{source_key}_cols"] = source_cols
        set_current(output)
    elif kernel_name in ATTENTION_KERNELS:
        query = str(layer_state.get("q") or current_buffer())
        key = str(layer_state.get("k") or "state:kv_cache:key")
        val = str(layer_state.get("v") or "state:kv_cache:value")
        output = next_buffer(op_name)
        inputs.extend(
            [
                binding(
                    symbol="query",
                    buffer=query,
                    role="activation",
                    access="read",
                    source="activation_router",
                ),
                binding(
                    symbol="key",
                    buffer="state:kv_cache:key",
                    role="kv_cache",
                    access="read",
                    source="kv_cache_schedule",
                    fallbackBuffer=key,
                ),
                binding(
                    symbol="val",
                    buffer="state:kv_cache:value",
                    role="kv_cache",
                    access="read",
                    source="kv_cache_schedule",
                    fallbackBuffer=val,
                ),
            ]
        )
        if kernel_name == "attn_decode":
            inputs.append(
                binding(
                    symbol="position",
                    buffer="state:decode_position",
                    role="position",
                    access="read",
                    source="runtime_state",
                    status="declared" if "decode_position" in states else "missing",
                )
            )
            inputs.append(
                binding(
                    symbol="sliding_window",
                    buffer="state:sliding_window",
                    role="position",
                    access="read",
                    source="runtime_state",
                    status="declared" if "sliding_window" in states else "missing",
                )
            )
        outputs.append(
            binding(
                symbol="output",
                buffer=output,
                role="activation",
                access="write",
                source=f"{kernel_name}.output",
            )
        )
        if layer_index is not None:
            layer_state["attention_output"] = output
        set_current(output)
    elif kernel_name in {"residual", "gelu"}:
        source = current_buffer()
        output = next_buffer(op_name)
        if kernel_name == "gelu":
            up = str(layer_state.get("up_proj") or source)
            inputs.append(
                binding(
                    symbol="input",
                    buffer=up,
                    role="activation",
                    access="read",
                    source="activation_router",
                )
            )
        else:
            base_key = (
                "residual_base"
                if op_name == "attn_residual"
                else "ffn_residual_base"
            )
            residual_source = str(layer_state.get(base_key) or "")
            if not residual_source:
                blockers.append(f"{base_key}_activation_missing:{op_name}")
                residual_source = f"activation:missing:{base_key}"
            inputs.append(
                binding(
                    symbol="input",
                    buffer=source,
                    role="activation",
                    access="read",
                    source="activation_router",
                )
            )
            inputs.append(
                binding(
                    symbol="residual",
                    buffer=residual_source,
                    role="activation",
                    access="read",
                    source="activation_router",
                    status=(
                        "missing"
                        if residual_source.startswith("activation:missing:")
                        else None
                    ),
                )
            )
        outputs.append(
            binding(
                symbol="output",
                buffer=output,
                role="activation",
                access="write",
                source=f"{kernel_name}.output",
            )
        )
        set_current(output)
    elif kernel_name == "sample":
        logits = str(phase_state.get("last_logits") or "state:output_logits")
        inputs.append(
            binding(
                symbol="logits",
                buffer=logits,
                role="logits",
                access="read",
                source="transcript_capture",
            )
        )
        outputs.append(
            binding(
                symbol="tokens",
                buffer=f"tokens:{phase}:{launch_index:04d}",
                role="generated_tokens",
                access="write",
                source="sample.output",
            )
        )
    else:
        source = current_buffer()
        output = next_buffer(op_name)
        inputs.append(
            binding(
                symbol="input",
                buffer=source,
                role="activation",
                access="read",
                source="activation_router",
            )
        )
        outputs.append(
            binding(
                symbol="output",
                buffer=output,
                role="activation",
                access="write",
                source=f"{kernel_name}.output",
            )
        )
        set_current(output)

    inputs = dedupe_bindings(inputs)
    outputs = dedupe_bindings(outputs)
    symbols = {
        item["symbol"]: {
            "buffer": item["buffer"],
            "role": item["role"],
            "access": item["access"],
        }
        for item in inputs + outputs
    }
    return {
        "operationName": op_name,
        "operation": op,
        "layerIndex": layer_index,
        "weightKey": normalized_step.get("weightsKey"),
        "inputs": inputs,
        "outputs": outputs,
        "symbols": symbols,
    }, blockers


def activation_lifetime_summary(
    schedule_records: list[dict[str, Any]],
) -> dict[str, Any]:
    lifetimes: dict[str, dict[str, Any]] = {}

    def ensure(buffer: str, role: str) -> dict[str, Any]:
        return lifetimes.setdefault(
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

    for record in schedule_records:
        launch_index = int(record["launchIndex"])
        for item in record.get("outputs") or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", ""))
            buffer = str(item.get("buffer", ""))
            if role not in {"activation", "logits", "generated_tokens"}:
                continue
            lifetime = ensure(buffer, role)
            if lifetime["producerLaunchIndex"] is None:
                lifetime["producerLaunchIndex"] = launch_index
        for item in record.get("inputs") or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", ""))
            buffer = str(item.get("buffer", ""))
            if role not in {"activation", "logits", "generated_tokens"}:
                continue
            lifetime = ensure(buffer, role)
            if lifetime["firstConsumerLaunchIndex"] is None:
                lifetime["firstConsumerLaunchIndex"] = launch_index
            lifetime["lastConsumerLaunchIndex"] = launch_index
            lifetime["consumerCount"] += 1
    records = sorted(lifetimes.values(), key=lambda item: item["buffer"])
    routed = [
        item
        for item in records
        if item["producerLaunchIndex"] is not None or item["consumerCount"] > 0
    ]
    return {
        "status": "bound" if routed else "blocked_missing_activation_lifetimes",
        "bufferCount": len(records),
        "routedBufferCount": len(routed),
        "lifetimes": records,
    }


def kv_cache_schedule(
    schedule_records: list[dict[str, Any]],
    model_config: dict[str, Any],
) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    covered_layers: set[int] = set()
    for record in schedule_records:
        kernel_name = str(record.get("kernelName") or "")
        if kernel_name not in ATTENTION_KERNELS:
            continue
        layer_index = record.get("layerIndex")
        if not isinstance(layer_index, int):
            continue
        covered_layers.add(layer_index)
        key_input = next(
            (
                item
                for item in record.get("inputs") or []
                if isinstance(item, dict) and item.get("symbol") == "key"
            ),
            {},
        )
        val_input = next(
            (
                item
                for item in record.get("inputs") or []
                if isinstance(item, dict) and item.get("symbol") == "val"
            ),
            {},
        )
        operations.append(
            {
                "launchIndex": record["launchIndex"],
                "hostPlanLaunchIndex": record.get("hostPlanLaunchIndex"),
                "runtimeLaunchIndex": record.get("runtimeLaunchIndex"),
                "phase": record["phase"],
                "decodeStepIndex": record.get("decodeStepIndex"),
                "layerIndex": layer_index,
                "attentionKernel": kernel_name,
                "write": {
                    "keyBuffer": key_input.get("fallbackBuffer") or key_input.get("buffer"),
                    "valueBuffer": val_input.get("fallbackBuffer") or val_input.get("buffer"),
                    "cacheBuffer": "state:kv_cache",
                    "positionSource": (
                        "decode_position"
                        if record["phase"] == "decode"
                        else "prompt_span"
                    ),
                },
                "read": {
                    "keyBuffer": key_input.get("buffer", "state:kv_cache:key"),
                    "valueBuffer": val_input.get("buffer", "state:kv_cache:value"),
                    "cacheBuffer": "state:kv_cache",
                    "slidingWindowSource": (
                        "sliding_window"
                        if kernel_name == "attn_decode"
                        else "prefill_full_context"
                    ),
                },
            }
        )
    layer_count = int(model_config.get("numLayers") or len(covered_layers))
    status = (
        "bound"
        if operations and (layer_count == 0 or len(covered_layers) == layer_count)
        else "blocked_missing_kv_layer_coverage"
    )
    return {
        "status": status,
        "cacheWriteCount": len(operations),
        "cacheReadCount": len(operations),
        "layerCoverage": {
            "layerCount": layer_count,
            "coveredLayerCount": len(covered_layers),
            "coveredLayers": sorted(covered_layers),
        },
        "operations": operations,
    }


def transcript_capture_schedule(
    schedule_records: list[dict[str, Any]],
    reference: dict[str, Any],
) -> dict[str, Any]:
    emitters: list[dict[str, Any]] = []
    decode_step = 0
    pending_logits: str | None = None
    pending_logits_launch: int | None = None
    for record in schedule_records:
        phase = str(record.get("phase") or "")
        kernel_name = str(record.get("kernelName") or "")
        operation_name = str(record.get("operationName") or "")
        if phase in {"prefill", "decode"} and (
            kernel_name in {"lm_head_gemv", "lm_head_gemv_stable", "lm_head_prefill_stable"}
            or operation_name in {"lm_head", "lm_head_prefill"}
        ):
            record_decode_step = record.get("decodeStepIndex")
            if isinstance(record_decode_step, int):
                decode_step = record_decode_step
            for item in record.get("outputs") or []:
                if isinstance(item, dict) and item.get("role") == "logits":
                    pending_logits = str(item.get("buffer"))
                    pending_logits_launch = int(record["launchIndex"])
                    emitters.append(
                        {
                            "kind": "logits_digest",
                            "stepIndex": decode_step,
                            "launchIndex": record["launchIndex"],
                            "hostPlanLaunchIndex": record.get("hostPlanLaunchIndex"),
                            "runtimeLaunchIndex": record.get("runtimeLaunchIndex"),
                            "symbol": item.get("symbol", "output"),
                            "buffer": pending_logits,
                            "expectedSha256": None,
                        }
                    )
                    break
        if phase in {"prefill", "decode"} and kernel_name == "sample":
            record_decode_step = record.get("decodeStepIndex")
            if isinstance(record_decode_step, int):
                decode_step = record_decode_step
            token_buffer = next(
                (
                    item.get("buffer")
                    for item in record.get("outputs") or []
                    if isinstance(item, dict)
                    and item.get("role") == "generated_tokens"
                ),
                "tokens:decode:pending",
            )
            emitters.append(
                {
                    "kind": "generated_token",
                    "stepIndex": decode_step,
                    "launchIndex": record["launchIndex"],
                    "hostPlanLaunchIndex": record.get("hostPlanLaunchIndex"),
                    "runtimeLaunchIndex": record.get("runtimeLaunchIndex"),
                    "symbol": "tokens",
                    "buffer": token_buffer,
                    "logitsBuffer": pending_logits,
                    "logitsLaunchIndex": pending_logits_launch,
                }
            )
            decode_step += 1
    expected_steps = int(reference.get("actualDecodeSteps") or 0)
    logits_emitters = [item for item in emitters if item["kind"] == "logits_digest"]
    token_emitters = [item for item in emitters if item["kind"] == "generated_token"]
    status = (
        "bound"
        if expected_steps > 0
        and len(logits_emitters) == expected_steps
        and len(token_emitters) == expected_steps
        else "blocked_missing_decode_emitters"
    )
    return {
        "status": status,
        "expectedActualDecodeSteps": expected_steps,
        "logitsEmitterCount": len(logits_emitters),
        "tokenEmitterCount": len(token_emitters),
        "emitters": emitters,
    }


def synthesize_runtime_scheduler(
    *,
    launches: list[dict[str, Any]],
    runtime_config: dict[str, Any] | None,
    normalized_execution: dict[str, Any] | None,
    reference: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = normalized_execution or {"present": False, "steps": []}
    if runtime_config is None:
        return {
            "status": "blocked_missing_runtime_config",
            "blockers": ["runtime_config_not_loaded"],
            "launches": [],
        }
    if not normalized.get("present"):
        return {
            "status": "blocked_missing_normalized_execution",
            "blockers": ["normalized_execution_v1_missing"],
            "normalizedExecution": {
                "present": False,
                "path": normalized.get("path", "pending"),
            },
            "launches": [],
        }
    steps = [
        item for item in normalized.get("steps") or [] if isinstance(item, dict)
    ]
    by_phase: dict[str, list[dict[str, Any]]] = {
        "prefill": [item for item in steps if item.get("phase") == "prefill"],
        "decode": [item for item in steps if item.get("phase") == "decode"],
    }
    expanded_launches = expand_runtime_launches(launches, reference)
    expected_decode_steps = max(1, reference_decode_steps(reference))
    expected_phase_launch_counts = {
        "prefill": len(by_phase["prefill"]),
        "decode": len(by_phase["decode"]) * expected_decode_steps,
    }
    phase_launch_counts = count_by(expanded_launches, "_phase")
    count_blockers = [
        f"{phase}_launch_count_mismatch:"
        f"{phase_launch_counts.get(phase, 0)}!={expected_count}"
        for phase, expected_count in expected_phase_launch_counts.items()
        if phase_launch_counts.get(phase, 0) != expected_count
    ]
    weights = weight_index(runtime_config)
    states = state_buffer_names(runtime_config)
    scheduler_state: dict[str, Any] = {}
    bound_records: list[dict[str, Any]] = []
    blockers: list[str] = list(count_blockers)
    for record in expanded_launches:
        phase = str(record["_phase"])
        phase_index = int(record["_phaseIndex"])
        phase_steps = by_phase.get(phase, [])
        normalized_step = (
            phase_steps[phase_index] if phase_index < len(phase_steps) else {}
        )
        layer_index = (
            infer_step_layer_index(phase_steps, phase_index)
            if normalized_step
            else None
        )
        bindings, binding_blockers = bind_launch_dataflow(
            record=record,
            normalized_step=normalized_step,
            layer_index=layer_index,
            weights=weights,
            states=states,
            scheduler_state=scheduler_state,
        )
        blockers.extend(
            f"launch[{record['launchIndex']}]:{blocker}"
            for blocker in binding_blockers
        )
        bound = {**record, **bindings}
        bound["symbolDataflowPresent"] = bool(
            bound.get("inputs") or bound.get("outputs") or bound.get("symbols")
        )
        bound["inputSymbolCount"] = len(bound.get("inputs") or [])
        bound["outputSymbolCount"] = len(bound.get("outputs") or [])
        bound["symbolTablePresent"] = isinstance(bound.get("symbols"), dict)
        bound_records.append(bound)
    activation = activation_lifetime_summary(bound_records)
    kv_schedule = kv_cache_schedule(
        bound_records,
        runtime_config.get("modelConfig") or normalized.get("modelConfig") or {},
    )
    transcript = transcript_capture_schedule(bound_records, reference or {})
    if activation["status"] != "bound":
        blockers.append(activation["status"])
    if kv_schedule["status"] != "bound":
        blockers.append(kv_schedule["status"])
    if transcript["status"] != "bound":
        blockers.append(transcript["status"])
    status = "bound" if not blockers else "blocked"
    return {
        "status": status,
        "blockers": blockers,
        "normalizedExecution": {
            "present": True,
            "path": normalized["path"],
            "sha256": normalized["sha256"],
            "stepCount": len(steps),
            "phaseStepCounts": {key: len(value) for key, value in by_phase.items()},
        },
        "runtimeExpansion": {
            "decodeIterationCount": expected_decode_steps,
            "hostPlanLaunchCount": len(launches),
            "runtimeLaunchCount": len(expanded_launches),
            "phaseLaunchCounts": phase_launch_counts,
        },
        "activationRouting": activation,
        "kvCacheSchedule": kv_schedule,
        "transcriptCaptureSchedule": transcript,
        "launches": bound_records,
    }
