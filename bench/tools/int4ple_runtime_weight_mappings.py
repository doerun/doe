"""Weight-key inference helpers for the INT4 PLE runtime weight mapping.

Pure functions that translate Doppler ``weightsKey`` strings into Hugging Face
tensor-name candidates, infer the layer index for layer-scoped steps, and
derive the inferred RMSNorm weight key for steps whose normalized execution
entry omits ``weightsKey`` outright.

Extracted from ``bench/tools/run_doe_csl_int4ple_transcript.py`` per the
sharding follow-up tracked in ``docs/status/cerebras-csl.md`` (late+16).
The transcript module re-exports these symbols for backward compatibility
with existing importers.
"""

from __future__ import annotations

from typing import Any


def tensor_name_candidates_for_weight_key(weight_key: str) -> list[str]:
    """Return all Hugging Face tensor-name candidates for a HostPlan weight key."""
    if weight_key == "norm":
        return [
            "model.language_model.norm.weight",
            "model.norm.weight",
            "norm.weight",
        ]
    if weight_key == "embed_tokens":
        return [
            "model.language_model.embed_tokens_per_layer.weight",
            "model.language_model.embed_tokens.weight",
            "model.embed_tokens.weight",
        ]
    if weight_key == "lm_head":
        return [
            "model.language_model.lm_head.weight",
            "language_model.lm_head.weight",
            "model.lm_head.weight",
            "lm_head.weight",
            "model.language_model.embed_tokens.weight",
            "language_model.model.embed_tokens.weight",
            "model.embed_tokens.weight",
            "embed_tokens.weight",
        ]
    if weight_key.startswith("layer."):
        parts = weight_key.split(".")
        if len(parts) >= 3 and parts[2] in {
            "input_layernorm",
            "post_attention_layernorm",
            "pre_feedforward_layernorm",
            "post_feedforward_layernorm",
        }:
            return [
                "model.language_model.layers." f"{parts[1]}.{parts[2]}.weight",
                f"model.layers.{parts[1]}.{parts[2]}.weight",
            ]
        if len(parts) >= 4 and parts[2] == "self_attn":
            return [
                (
                    "model.language_model.layers."
                    f"{parts[1]}.self_attn.{parts[3]}.weight"
                ),
                f"model.layers.{parts[1]}.self_attn.{parts[3]}.weight",
            ]
        if len(parts) >= 4 and parts[2] == "linear_attn":
            suffix = ".".join(parts[3:])
            if suffix == "conv1d":
                suffix = "conv1d.weight"
            return [
                (
                    "model.language_model.layers."
                    f"{parts[1]}.linear_attn.{suffix}"
                ),
                f"model.layers.{parts[1]}.linear_attn.{suffix}",
            ]
        if len(parts) >= 4 and parts[2] == "mlp":
            return [
                (
                    "model.language_model.layers."
                    f"{parts[1]}.mlp.{parts[3]}.weight"
                ),
                f"model.layers.{parts[1]}.mlp.{parts[3]}.weight",
            ]
    raise ValueError(f"unsupported HostPlan weight key: {weight_key}")


def tensor_name_for_weight_key(weight_key: str) -> str:
    """Return the first (canonical) tensor name candidate for a weight key."""
    return tensor_name_candidates_for_weight_key(weight_key)[0]


def layer_index_from_step_weight_key(weight_key: Any) -> int | None:
    """Extract the layer index from a layer-scoped ``weightsKey`` string."""
    if not isinstance(weight_key, str):
        return None
    parts = weight_key.split(".")
    if len(parts) < 2 or parts[0] != "layer":
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def infer_layer_index_from_steps(steps: list[dict[str, Any]], index: int) -> int | None:
    """Infer the layer index for a step that lacks an explicit layer-scoped key.

    Walks up to eight steps backward and forward looking for a neighboring
    step whose ``weightsKey`` carries a ``layer.<N>`` prefix; ignores
    forward-direction steps whose name marks them as model-level rather than
    layer-scoped (``final_norm``, ``lm_head``, ``lm_head_prefill``, ``sample``).
    """
    current = steps[index]
    direct = layer_index_from_step_weight_key(current.get("weightsKey"))
    if direct is not None:
        return direct
    for offset in range(1, 9):
        prev_index = index - offset
        if prev_index >= 0:
            candidate = layer_index_from_step_weight_key(steps[prev_index].get("weightsKey"))
            if candidate is not None:
                return candidate
        next_index = index + offset
        if next_index < len(steps):
            name = str(steps[next_index].get("name") or "")
            if name in {"final_norm", "lm_head", "lm_head_prefill", "sample"}:
                continue
            candidate = layer_index_from_step_weight_key(steps[next_index].get("weightsKey"))
            if candidate is not None:
                return candidate
    return None


def inferred_rmsnorm_weight_key(step_name: str, layer_index: int | None) -> str | None:
    """Map a Doppler RMSNorm step name + layer index to its weight key, if known."""
    if step_name == "final_norm":
        return "norm"
    if layer_index is None:
        return None
    suffix_by_step = {
        "input_norm": "input_layernorm",
        "post_attn_norm": "post_attention_layernorm",
        "pre_ffn_norm": "pre_feedforward_layernorm",
        "post_ffn_norm": "post_feedforward_layernorm",
    }
    suffix = suffix_by_step.get(step_name)
    if suffix is None:
        return None
    return f"layer.{layer_index}.{suffix}"


def required_weight_keys(normalized_execution: dict[str, Any]) -> list[str]:
    """Collect the weight keys required by the normalized execution graph.

    Steps that declare ``weightsKey`` contribute it directly. Steps that omit
    ``weightsKey`` but identify as RMSNorm contribute an inferred key derived
    from the step name and surrounding layer context.
    """
    steps = [
        step
        for step in normalized_execution.get("steps") or []
        if isinstance(step, dict)
    ]
    keys: set[str] = set()
    for index, step in enumerate(steps):
        raw_key = step.get("weightsKey")
        if isinstance(raw_key, str) and raw_key:
            keys.add(raw_key)
            continue
        kernel_key = str(step.get("kernelKey") or "")
        op = str(step.get("op") or "")
        if kernel_key == "rmsnorm" or op == "rmsnorm":
            inferred = inferred_rmsnorm_weight_key(
                str(step.get("name") or ""),
                infer_layer_index_from_steps(steps, index),
            )
            if inferred:
                keys.add(inferred)
    return sorted(keys)
