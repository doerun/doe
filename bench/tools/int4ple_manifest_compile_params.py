from __future__ import annotations

from typing import Any

COMPILE_DISTINCT_PE_WARNING_THRESHOLD = 10_000
Q4K_BLOCK_SIZE = 256
TARGET_MATMUL_TILE = 16
ATTENTION_PREFILL_BLOCK_SIZE = 32
DEFAULT_GEMV_INPUT_PER_PE = 512
DEFAULT_DECODE_KV_CHUNK = 1


def ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return (numerator + denominator - 1) // denominator


def runtime_grid(runtime_config: dict[str, Any]) -> dict[str, int]:
    memory_plan = runtime_config.get("memoryPlan") or {}
    grid = memory_plan.get("grid") if isinstance(memory_plan, dict) else {}
    if not isinstance(grid, dict):
        grid = {}
    return {
        "width": int(grid.get("width") or 0),
        "height": int(grid.get("height") or 0),
    }


def reference_prompt_token_count(reference: dict[str, Any]) -> int:
    prompt_tokens = reference.get("promptTokenCount")
    if prompt_tokens is not None:
        return int(prompt_tokens)
    input_components = reference.get("inputSetComponents") or {}
    if isinstance(input_components, dict):
        token_count = input_components.get("tokenCount")
        if token_count is not None:
            return int(token_count)
    return 0


def manifest_compile_param_projection(
    *,
    runtime_config: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    model = runtime_config.get("modelConfig") or {}
    if not isinstance(model, dict) or not model:
        return {"status": "not_evaluated", "reason": "model_config_missing"}
    grid = runtime_grid(runtime_config)
    grid_width = grid["width"]
    grid_height = grid["height"]
    if grid_width <= 0 or grid_height <= 0:
        return {"status": "not_evaluated", "reason": "runtime_grid_missing"}

    vocab_size = int(model.get("vocabSize") or model.get("pleVocabSize") or 0)
    hidden_dim = int(model.get("hiddenDim") or 0)
    head_dim = int(model.get("headDim") or 0)
    global_head_dim = int(model.get("globalHeadDim") or head_dim)
    max_seq_len = int(
        model.get("maxSeqLen") or reference_prompt_token_count(reference) or 0
    )
    prompt_tokens = int(reference_prompt_token_count(reference) or max_seq_len or 0)
    pe_count = grid_width * grid_height
    matmul_p = min(
        grid_width,
        grid_height,
        int(COMPILE_DISTINCT_PE_WARNING_THRESHOLD**0.5),
        max(1, ceil_div(hidden_dim, TARGET_MATMUL_TILE)),
    )
    matmul_tile = ceil_div(hidden_dim, matmul_p)
    gemv_input_per_pe = max(
        DEFAULT_GEMV_INPUT_PER_PE,
        ceil_div(hidden_dim, max(1, grid_width)),
    )
    gemv_blocks = ceil_div(gemv_input_per_pe, Q4K_BLOCK_SIZE)
    lm_head_out_dim = ceil_div(vocab_size, max(1, grid_width))
    sample_chunk = ceil_div(vocab_size, max(1, grid_width))
    attention_tokens = max(1, prompt_tokens)

    params = {
        "sample": {
            "chunk_size": sample_chunk,
        },
        "embed": {
            "height": grid_height,
            "hidden_size": hidden_dim,
            "num_tokens": max_seq_len,
            "rows_per_pe": ceil_div(vocab_size, max(1, pe_count)),
        },
        "rope": {
            "head_dim": head_dim,
            "num_pairs": ceil_div(head_dim, 2),
        },
        "tiled": {
            "P": matmul_p,
            "Mt": matmul_tile,
            "Kt": matmul_tile,
            "Nt": matmul_tile,
        },
        "gemv": {
            "out_dim": max(
                TARGET_MATMUL_TILE,
                ceil_div(hidden_dim, max(1, grid_width)),
            ),
            "in_dim_per_pe": gemv_input_per_pe,
            "num_blocks_per_row": gemv_blocks,
        },
        "lm_head_gemv_stable": {
            "out_dim": lm_head_out_dim,
            "in_dim_per_pe": gemv_input_per_pe,
            "num_blocks_per_row": gemv_blocks,
        },
        "attn_decode": {
            "head_dim": head_dim,
            "kv_chunk": DEFAULT_DECODE_KV_CHUNK,
        },
        "attn_head256": {
            "block_size": min(ATTENTION_PREFILL_BLOCK_SIZE, attention_tokens),
            "head_dim": head_dim,
            "kv_len": attention_tokens,
            "q_len": attention_tokens,
        },
        "attn_head512": {
            "block_size": min(ATTENTION_PREFILL_BLOCK_SIZE, attention_tokens),
            "head_dim": global_head_dim,
            "kv_len": attention_tokens,
            "q_len": attention_tokens,
        },
    }
    compile_scale = {
        "embedDistinctPeProgramCount": pe_count,
        "tiledDistinctPeProgramCount": matmul_p * matmul_p,
        "warningThreshold": COMPILE_DISTINCT_PE_WARNING_THRESHOLD,
    }
    warnings = [
        f"{key}:{value}>{COMPILE_DISTINCT_PE_WARNING_THRESHOLD}"
        for key, value in compile_scale.items()
        if key.endswith("Count") and value > COMPILE_DISTINCT_PE_WARNING_THRESHOLD
    ]
    return {
        "status": "projected",
        "source": "runtime_config_model_and_grid",
        "grid": grid,
        "params": params,
        "coverage": {
            "embedRows": pe_count * int(params["embed"]["rows_per_pe"]),
            "tiledM": matmul_p * matmul_tile,
            "tiledN": matmul_p * matmul_tile,
            "lmHeadLogits": grid_width * lm_head_out_dim,
            "sampleLogits": grid_width * sample_chunk,
        },
        "compileScale": compile_scale,
        "warnings": warnings,
    }


def apply_manifest_compile_params(
    *,
    simulator_plan: dict[str, Any],
    runtime_config: dict[str, Any],
    reference: dict[str, Any],
    manifest_unsafe_targets: dict[str, str] | None = None,
) -> dict[str, Any]:
    projection = manifest_compile_param_projection(
        runtime_config=runtime_config,
        reference=reference,
    )
    if projection.get("status") != "projected":
        return {
            "status": "not_applied",
            "reason": projection.get("reason", "projection_not_available"),
            "manifestCompileParamProjection": projection,
            "targets": [],
        }

    expected_params = projection["params"]
    inputs = simulator_plan.get("inputs") or {}
    compile_targets = inputs.get("compileTargets") or []
    if not isinstance(compile_targets, list):
        return {
            "status": "not_applied",
            "reason": "compile_targets_missing",
            "manifestCompileParamProjection": projection,
            "targets": [],
        }

    unsafe = manifest_unsafe_targets or {}
    patched_targets: list[dict[str, Any]] = []
    held_diagnostic: list[dict[str, Any]] = []
    present_names: set[str] = set()
    unprojected_target_names: list[str] = []
    for target in compile_targets:
        if not isinstance(target, dict):
            continue
        name = str(target.get("name") or "")
        present_names.add(name)
        params = expected_params.get(name)
        if params is None:
            if name:
                unprojected_target_names.append(name)
            continue
        if name in unsafe:
            retained = target.get("compileParams")
            held_diagnostic.append(
                {
                    "name": name,
                    "reason": unsafe[name],
                    "projected": dict(params),
                    "retained": retained if isinstance(retained, dict) else None,
                }
            )
            continue
        previous = target.get("compileParams")
        target["compileParams"] = dict(params)
        patched_targets.append(
            {
                "name": name,
                "previous": previous if isinstance(previous, dict) else None,
                "applied": target["compileParams"],
            }
        )

    return {
        "status": "applied" if patched_targets else "not_applied",
        "reason": "matched_targets" if patched_targets else "no_matching_compile_targets",
        "manifestCompileParamProjection": projection,
        "patchedTargetCount": len(patched_targets),
        "missingProjectedTargetNames": sorted(set(expected_params) - present_names),
        "unprojectedTargetNames": sorted(set(unprojected_target_names)),
        "heldDiagnosticTargets": held_diagnostic,
        "targets": patched_targets,
    }
