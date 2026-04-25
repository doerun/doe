from __future__ import annotations

from typing import Any

COMPILE_DISTINCT_PE_WARNING_THRESHOLD = 10_000
Q4K_BLOCK_SIZE = 256
TARGET_MATMUL_TILE = 16
ATTENTION_PREFILL_BLOCK_SIZE = 32
DEFAULT_GEMV_INPUT_PER_PE = 512
DEFAULT_DECODE_KV_CHUNK = 1
SUMMA_PE_DATA_BUDGET_BYTES = 32 * 1024

# embed chunked-dispatch per-PE budget. Measured against `.blocked_ut_ival`
# at 0xFC04 (~63 KiB) on WSE-3 SDK 2.10; half that (~31 KiB) leaves headroom
# for stack, PE program code, and memcpy framework overhead. The chunked
# dispatch solver below picks (hiddenPerPe, tokensPerChunk) such that
# (rowsPerPe + tokensPerChunk) * hiddenPerPe * 4 ≤ EMBED_PE_DATA_BUDGET_BYTES.
EMBED_PE_DATA_BUDGET_BYTES = 32 * 1024
EMBED_DEFAULT_TOKENS_PER_CHUNK = 16

# attn_head{256,512} streaming-KV per-PE budget. Measured empirically from
# bench/out/cslc-attn-streaming-probe/probe-result.json against WSE-3 SDK
# 2.10's `.blocked_ut_ival` ceiling (~63 KiB). The probe's failing/working
# bracket put the real `.data.hi` overflow point for attention between
# 20 and 24 KiB once you account for the m_state/l_state arrays, stack,
# memcpy framework overhead, and intermediate registers that 32-KiB-budget
# solvers do not see. 20 KiB is under the empirical bracket with margin
# and matches every (block_size, q_len_per_pe) pair the probe reported as
# compiling clean. The streaming solver picks (qLenPerPe, blockSize) such
# that (qLenPerPe + blockSize) * head_dim * 4 ≤ ATTN_PE_DATA_BUDGET_BYTES.
ATTN_PE_DATA_BUDGET_BYTES = 20 * 1024
# Candidate block sizes the solver considers, in preference order
# (larger block = fewer host dispatches per kv_len).
ATTN_BLOCK_SIZE_CANDIDATES = (16, 8, 4, 2, 1)

# lm_head fused-GEMV 2-D sharding budget. Same WSE-3 `.blocked_ut_ival`
# ceiling; held at half to leave headroom for the per-PE scratch_in /
# scratch_out DSD reduce buffers (each sized `out_dim_per_pe` floats),
# partial[out_dim_per_pe], plus PE program code, stack, memcpy framework.
# (out_dim_per_pe * num_blocks_per_row * Q4K_BLOCK_BYTES) is the weight
# footprint per PE; we bound that plus 4× out_dim_per_pe floats for
# output/partial/scratch_in/scratch_out.
LMHEAD_PE_DATA_BUDGET_BYTES = 32 * 1024
Q4K_BLOCK_BYTES = 144


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


def divisors_ascending(n: int) -> list[int]:
    if n <= 0:
        return []
    out: list[int] = []
    d = 1
    while d * d <= n:
        if n % d == 0:
            out.append(d)
            if d != n // d:
                out.append(n // d)
        d += 1
    out.sort()
    return out


def summa_tile_footprint_bytes(*, mt: int, kt: int, nt: int) -> int:
    if mt <= 0 or kt <= 0 or nt <= 0:
        return 0
    # emit_csl_matmul's PE program allocates A_tile/B_tile/C_tile plus
    # double-buffers for A and B.
    element_count = (2 * mt * kt) + (2 * kt * nt) + (mt * nt)
    return element_count * 4


def solve_summa_tiled_matmul(
    *,
    grid_width: int,
    grid_height: int,
    hidden_dim: int,
    target_tile: int = TARGET_MATMUL_TILE,
    budget_bytes: int = SUMMA_PE_DATA_BUDGET_BYTES,
) -> dict[str, int]:
    max_p = max(1, min(grid_width, grid_height))
    preferred_p = min(
        max_p,
        int(COMPILE_DISTINCT_PE_WARNING_THRESHOLD**0.5),
        max(1, ceil_div(hidden_dim, target_tile)),
    )
    for p in range(preferred_p, max_p + 1):
        tile = ceil_div(hidden_dim, p)
        if summa_tile_footprint_bytes(mt=tile, kt=tile, nt=tile) <= budget_bytes:
            return {
                "P": p,
                "Mt": tile,
                "Kt": tile,
                "Nt": tile,
                "perPeFootprintBytes": summa_tile_footprint_bytes(
                    mt=tile,
                    kt=tile,
                    nt=tile,
                ),
                "budgetBytes": budget_bytes,
            }
    tile = ceil_div(hidden_dim, max_p)
    return {
        "P": max_p,
        "Mt": tile,
        "Kt": tile,
        "Nt": tile,
        "perPeFootprintBytes": summa_tile_footprint_bytes(
            mt=tile,
            kt=tile,
            nt=tile,
        ),
        "budgetBytes": budget_bytes,
    }


def solve_embed_chunked_dispatch(
    *,
    grid_width: int,
    grid_height: int,
    hidden_size: int,
    vocab_size: int,
    num_tokens: int,
    budget_bytes: int = EMBED_PE_DATA_BUDGET_BYTES,
) -> dict[str, int] | None:
    """Jointly pick (rowsPerPe, hiddenPerPe, hiddenShardCount, tokensPerChunk)
    that makes the chunked-dispatch embed kernel fit per-PE memory while
    still covering the full vocabulary at the given grid width.

    Constraints:
      * rowsPerPe * grid_width * grid_height >= vocab_size
        (every row is held somewhere)
      * (rowsPerPe + tokensPerChunk) * hiddenPerPe * 4 <= budget_bytes
      * hiddenPerPe * hiddenShardCount == hidden_size (clean partition)

    Strategy: given the HostPlan grid, rowsPerPe =
    ceil(vocab_size / (grid_width * grid_height)) is fixed by the coverage
    constraint. The PE program reads its X/Y coordinate from CSL's layout
    module, so row coverage can use the full 2-D grid without producing one
    distinct PE program per tile. Then for each divisor of hidden_size
    (largest first), check whether the budget constraint holds at the default
    tokensPerChunk. Shrink tokensPerChunk only as a fallback.

    Returns None only when no tokensPerChunk >= 1 and no divisor of
    hidden_size can satisfy the budget — a truly unrescueable shape. The
    caller must then accept that the pre-chunked compile will overflow.
    """
    if (
        grid_width <= 0
        or grid_height <= 0
        or hidden_size <= 0
        or vocab_size <= 0
        or num_tokens <= 0
        or budget_bytes <= 0
    ):
        return None
    pe_count = grid_width * grid_height
    rows_per_pe = ceil_div(vocab_size, pe_count)
    default_tokens = max(1, min(num_tokens, EMBED_DEFAULT_TOKENS_PER_CHUNK))
    divisors_desc = sorted(divisors_ascending(hidden_size), reverse=True)
    # Outer loop: tokens_per_chunk from default down to 1.
    # Inner loop: hiddenPerPe from largest divisor down to 1.
    # First tuple to fit wins (prefers larger chunks + larger hiddenPerPe
    # for fewer host dispatches and larger per-PE working sets).
    candidate_tokens = sorted({default_tokens, *range(default_tokens, 0, -1)}, reverse=True)
    for tokens_per_chunk in candidate_tokens:
        for hidden_per_pe in divisors_desc:
            hidden_shard_count = hidden_size // hidden_per_pe
            footprint = (rows_per_pe + tokens_per_chunk) * hidden_per_pe * 4
            if footprint <= budget_bytes:
                return {
                    "rowsPerPe": rows_per_pe,
                    "hiddenPerPe": hidden_per_pe,
                    "hiddenShardCount": hidden_shard_count,
                    "tokensPerChunk": tokens_per_chunk,
                    "perPeFootprintBytes": footprint,
                    "budgetBytes": budget_bytes,
                    "gridWidth": grid_width,
                    "gridHeight": grid_height,
                }
    return None


def solve_lmhead_gemv_2d(
    *,
    grid_width: int,
    grid_height: int,
    out_dim_total: int,
    num_blocks_per_row: int,
    budget_bytes: int = LMHEAD_PE_DATA_BUDGET_BYTES,
) -> dict[str, int] | None:
    """Pick (outDimPerPe, height) for the 2-D fused-GEMV lm_head kernel.

    Constraints:
      * out_dim_per_pe * height >= out_dim_total      (every logit covered)
      * out_dim_per_pe * num_blocks_per_row * Q4K_BLOCK_BYTES
        + 4 * out_dim_per_pe * 4   (output+partial+scratch_in+scratch_out)
        ≤ budget_bytes
      * height ≤ grid_height
      * width * height fits the PE grid (caller guarantees grid_height)

    Strategy: iterate candidate heights from grid_height down to 1. At each
    height, pick out_dim_per_pe = ceil(out_dim_total / height), then check
    whether the budget constraint holds. First feasible (height,
    out_dim_per_pe) pair wins — larger heights mean smaller per-PE shards
    and smaller reduce-DSD extents, so preferring larger height is the
    compile-safest choice.
    """
    if (
        grid_width <= 0
        or grid_height <= 0
        or out_dim_total <= 0
        or num_blocks_per_row <= 0
        or budget_bytes <= 0
    ):
        return None
    for height in range(grid_height, 0, -1):
        out_dim_per_pe = ceil_div(out_dim_total, height)
        if out_dim_per_pe <= 0:
            continue
        weight_bytes = out_dim_per_pe * num_blocks_per_row * Q4K_BLOCK_BYTES
        scratch_bytes = 4 * out_dim_per_pe * 4
        footprint = weight_bytes + scratch_bytes
        if footprint <= budget_bytes:
            return {
                "outDimPerPe": out_dim_per_pe,
                "height": height,
                "width": grid_width,
                "perPeFootprintBytes": footprint,
                "budgetBytes": budget_bytes,
                "outDimTotal": out_dim_total,
            }
    return None


def lmhead_gemv_compile_params(
    *,
    grid_width: int,
    grid_height: int,
    out_dim_total: int,
    in_dim_per_pe: int,
    num_blocks_per_row: int,
) -> dict[str, int]:
    """Build the compileParams dict for the `lm_head_gemv_stable` kernel.

    Emits the four legacy knobs (`out_dim`, `in_dim_per_pe`,
    `num_blocks_per_row` — plus `height=1` when the pre-shard shape
    survives). When the 2-D solver finds a feasible (outDimPerPe, height)
    pair, also emits `out_dim_per_pe` and `height` for the cslc tile-code
    to pick up the sharded buffers. If no pair fits, falls back to the
    legacy knobs; the compile will then fail with the pre-shard i16
    overflow signature so the unrescueable shape is visible rather than
    silently patched.
    """
    tuple_ = solve_lmhead_gemv_2d(
        grid_width=grid_width,
        grid_height=grid_height,
        out_dim_total=out_dim_total,
        num_blocks_per_row=num_blocks_per_row,
    )
    params: dict[str, int] = {
        "out_dim": out_dim_total,
        "in_dim_per_pe": in_dim_per_pe,
        "num_blocks_per_row": num_blocks_per_row,
    }
    if tuple_ is not None:
        params["height"] = tuple_["height"]
        params["out_dim_per_pe"] = tuple_["outDimPerPe"]
        params["width"] = tuple_["width"]
    else:
        params["height"] = 1
    return params


def solve_attention_streaming(
    *,
    grid_width: int,
    head_dim: int,
    q_len: int,
    kv_len: int,
    budget_bytes: int = ATTN_PE_DATA_BUDGET_BYTES,
) -> dict[str, int] | None:
    """Pick (qLenPerPe, blockSize) for the streaming-KV tiled attention kernel
    such that the per-PE footprint fits.

    Constraints:
      * qLenPerPe = ceil(q_len / grid_width)         (cover full query)
      * blockSize ≤ kv_len                            (block fits inside the KV)
      * (qLenPerPe + blockSize) * head_dim * 4 ≤ budget_bytes

    Strategy: qLenPerPe is fixed by the coverage constraint. Pick the largest
    blockSize from ATTN_BLOCK_SIZE_CANDIDATES that fits the budget; this
    minimizes host dispatch count (`ceil(kv_len / blockSize)`). If even
    blockSize=1 overflows, returns None — the pre-streaming shape is
    genuinely unrescueable at this grid and head_dim.
    """
    if (
        grid_width <= 0
        or head_dim <= 0
        or q_len <= 0
        or kv_len <= 0
        or budget_bytes <= 0
    ):
        return None
    q_len_per_pe = max(1, ceil_div(q_len, grid_width))
    max_block = (budget_bytes // (head_dim * 4)) - q_len_per_pe
    if max_block < 1:
        return None
    block_candidates = [
        bs for bs in ATTN_BLOCK_SIZE_CANDIDATES
        if bs <= max_block and bs <= kv_len
    ]
    if not block_candidates:
        return None
    block_size = block_candidates[0]
    tile_count = ceil_div(kv_len, block_size)
    footprint = (q_len_per_pe + block_size) * head_dim * 4
    return {
        "blockSize": block_size,
        "qLenPerPe": q_len_per_pe,
        "width": grid_width,
        "tileCount": tile_count,
        "perPeFootprintBytes": footprint,
        "budgetBytes": budget_bytes,
    }


def attention_compile_params(
    *,
    grid_width: int,
    head_dim: int,
    q_len: int,
    kv_len: int,
) -> dict[str, Any]:
    """Build the compileParams dict for an `attn_head{256,512}` prefill kernel.

    Emits the legacy `(block_size, head_dim, kv_len, q_len)` knobs so the
    cslc contract stays stable, and — when the streaming solver finds a
    feasible `(qLenPerPe, blockSize)` — also emits the streaming knobs the
    emitter now needs (`q_len_per_pe`, `block_size` bound below the legacy
    default, plus `width`). When the solver fails, falls back to the legacy
    knobs only; the compile will then fail with the pre-streaming
    `.bss`/`.data.hi` overflow signature and the host Python runner's
    streaming contract will report the unrescueable shape.
    """
    tuple_ = solve_attention_streaming(
        grid_width=grid_width,
        head_dim=head_dim,
        q_len=q_len,
        kv_len=kv_len,
    )
    params: dict[str, Any] = {
        "head_dim": head_dim,
        "kv_len": kv_len,
        "q_len": q_len,
    }
    if tuple_ is not None:
        params["block_size"] = tuple_["blockSize"]
        params["q_len_per_pe"] = tuple_["qLenPerPe"]
        params["width"] = tuple_["width"]
    else:
        params["block_size"] = min(ATTENTION_PREFILL_BLOCK_SIZE, q_len)
    return params


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


def embed_compile_params(
    *,
    grid_width: int,
    grid_height: int,
    hidden_dim: int,
    vocab_size: int,
    max_seq_len: int,
) -> dict[str, int]:
    """Build the compileParams dict for the `embed` kernel.

    Always emits the four legacy 1-D knobs (`height`, `hidden_size`,
    `num_tokens`, `rows_per_pe`). When the chunked-dispatch solver finds a
    tuple that fits the per-PE budget, also emits `hidden_per_pe` and
    `tokens_per_chunk`; cslc uses those to size the per-PE output buffer.
    If no tuple fits (e.g., budget too small for rowsPerPe≥1 and any
    divisor of hidden_size), emits only the legacy knobs and the compile
    will still fail with the pre-chunked overflow — that is the honest
    state, not a silently patched one.
    """
    # The gather PE program uses CSL layout coordinates to flatten the 2-D
    # grid into row shards, while hidden/tokens are chunked by host launches.
    tuple_ = solve_embed_chunked_dispatch(
        grid_width=grid_width,
        grid_height=grid_height,
        hidden_size=hidden_dim,
        vocab_size=vocab_size,
        num_tokens=max_seq_len,
    )
    params: dict[str, int] = {
        "hidden_size": hidden_dim,
        "num_tokens": max_seq_len,
    }
    if tuple_ is not None:
        params["rows_per_pe"] = tuple_["rowsPerPe"]
        params["height"] = grid_height
        params["hidden_per_pe"] = tuple_["hiddenPerPe"]
        params["tokens_per_chunk"] = tuple_["tokensPerChunk"]
    else:
        # No feasible chunked-dispatch tuple found. Emit legacy 1-D
        # params so the compile fails with the pre-chunked overflow
        # signature rather than a silently patched one.
        pe_count = max(1, grid_width * grid_height)
        params["rows_per_pe"] = ceil_div(vocab_size, pe_count)
        params["height"] = grid_height
    return params


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
    raw_global_head_dim = model.get("globalHeadDim")
    global_head_dim = (
        int(raw_global_head_dim)
        if raw_global_head_dim is not None
        else head_dim
    )
    max_seq_len = int(
        model.get("maxSeqLen") or reference_prompt_token_count(reference) or 0
    )
    prompt_tokens = int(reference_prompt_token_count(reference) or max_seq_len or 0)
    pe_count = grid_width * grid_height
    matmul_params = solve_summa_tiled_matmul(
        grid_width=grid_width,
        grid_height=grid_height,
        hidden_dim=hidden_dim,
    )
    matmul_p = matmul_params["P"]
    matmul_tile = matmul_params["Mt"]
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
        "rmsnorm": {
            "width": attention_tokens,
            "hidden_size": hidden_dim,
        },
        "rmsnorm_prefill": {
            "width": attention_tokens,
            "hidden_size": hidden_dim,
        },
        "rmsnorm_decode": {
            "width": 1,
            "hidden_size": hidden_dim,
        },
        "residual": {
            "width": attention_tokens,
            "height": 1,
            "chunk_size": hidden_dim,
        },
        "residual_prefill": {
            "width": attention_tokens,
            "height": 1,
            "chunk_size": hidden_dim,
        },
        "residual_decode": {
            "width": 1,
            "height": 1,
            "chunk_size": hidden_dim,
        },
        "gelu": {
            "width": attention_tokens,
            "height": 1,
            "chunk_size": hidden_dim,
        },
        "gelu_prefill": {
            "width": attention_tokens,
            "height": 1,
            "chunk_size": hidden_dim,
        },
        "gelu_decode": {
            "width": 1,
            "height": 1,
            "chunk_size": hidden_dim,
        },
        "embed": embed_compile_params(
            grid_width=grid_width,
            grid_height=grid_height,
            hidden_dim=hidden_dim,
            vocab_size=vocab_size,
            max_seq_len=max_seq_len,
        ),
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
        "lm_head_gemv_stable": lmhead_gemv_compile_params(
            grid_width=grid_width,
            grid_height=grid_height,
            out_dim_total=lm_head_out_dim,
            in_dim_per_pe=gemv_input_per_pe,
            num_blocks_per_row=gemv_blocks,
        ),
        "lm_head_gemv": lmhead_gemv_compile_params(
            grid_width=grid_width,
            grid_height=grid_height,
            out_dim_total=lm_head_out_dim,
            in_dim_per_pe=gemv_input_per_pe,
            num_blocks_per_row=gemv_blocks,
        ),
        "attn_decode": {
            "head_dim": head_dim,
            "kv_chunk": DEFAULT_DECODE_KV_CHUNK,
        },
        "attn_head256": attention_compile_params(
            grid_width=grid_width,
            head_dim=head_dim,
            q_len=attention_tokens,
            kv_len=attention_tokens,
        ),
    }
    # Program Bundle v1 emits specific target names for the same CSL bodies.
    # Keep these aliases explicit so drift shows up in the projection report
    # instead of falling through to width/height-only cslc invocations.
    params["lm_head_prefill_stable"] = dict(params["tiled"])
    params["q4_widetile"] = dict(params["gemv"])
    params["q4_decode_gemv"] = dict(params["gemv"])
    if global_head_dim > 0:
        params["attn_head512"] = attention_compile_params(
            grid_width=grid_width,
            head_dim=global_head_dim,
            q_len=attention_tokens,
            kv_len=attention_tokens,
        )
    compile_scale = {
        "embedDistinctPeProgramCount": grid_width,
        "tiledDistinctPeProgramCount": matmul_p * matmul_p,
        "tiledPerPeFootprintBytes": matmul_params["perPeFootprintBytes"],
        "tiledBudgetBytes": matmul_params["budgetBytes"],
        "warningThreshold": COMPILE_DISTINCT_PE_WARNING_THRESHOLD,
    }
    warnings = [
        f"{key}:{value}>{COMPILE_DISTINCT_PE_WARNING_THRESHOLD}"
        for key, value in compile_scale.items()
        if key.endswith("Count") and value > COMPILE_DISTINCT_PE_WARNING_THRESHOLD
    ]
    target_blockers: dict[str, str] = {}
    if "hidden_per_pe" not in params["embed"]:
        target_blockers["embed"] = (
            "csl_compile_params_infeasible_embed_grid_budget"
        )
    if "q_len_per_pe" not in params["attn_head256"]:
        target_blockers["attn_head256"] = (
            "csl_compile_params_infeasible_attention_grid_budget"
        )
    if "attn_head512" in params and "q_len_per_pe" not in params["attn_head512"]:
        target_blockers["attn_head512"] = (
            "csl_compile_params_infeasible_attention_grid_budget"
        )
    if "out_dim_per_pe" not in params["lm_head_gemv_stable"]:
        target_blockers["lm_head_gemv_stable"] = (
            "csl_compile_params_infeasible_lmhead_grid_budget"
        )
    if "out_dim_per_pe" not in params["lm_head_gemv"]:
        target_blockers["lm_head_gemv"] = (
            "csl_compile_params_infeasible_lmhead_grid_budget"
        )
    return {
        "status": "projected",
        "source": "runtime_config_model_and_grid",
        "grid": grid,
        "params": params,
        "targetBlockers": target_blockers,
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

    unsafe = {
        **(projection.get("targetBlockers") or {}),
        **(manifest_unsafe_targets or {}),
    }
    patched_targets: list[dict[str, Any]] = []
    held_diagnostic: list[dict[str, Any]] = []
    blocked_targets: list[dict[str, Any]] = []
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
            target["compileParams"] = dict(params)
            target["compileBlockedReason"] = unsafe[name]
            blocked_targets.append(
                {
                    "name": name,
                    "reason": unsafe[name],
                    "projected": dict(params),
                    "retained": retained if isinstance(retained, dict) else None,
                }
            )
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
        "status": (
            "applied" if patched_targets or blocked_targets else "not_applied"
        ),
        "reason": (
            "matched_targets"
            if patched_targets or blocked_targets
            else "no_matching_compile_targets"
        ),
        "manifestCompileParamProjection": projection,
        "patchedTargetCount": len(patched_targets),
        "blockedTargetCount": len(blocked_targets),
        "missingProjectedTargetNames": sorted(set(expected_params) - present_names),
        "unprojectedTargetNames": sorted(set(unprojected_target_names)),
        "blockedTargets": blocked_targets,
        "heldDiagnosticTargets": held_diagnostic,
        "targets": patched_targets,
    }
