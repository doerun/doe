from __future__ import annotations

from typing import Any

COMPILE_DISTINCT_PE_WARNING_THRESHOLD = 10_000
Q4K_BLOCK_SIZE = 256
TARGET_MATMUL_TILE = 16
ATTENTION_PREFILL_BLOCK_SIZE = 32
DEFAULT_GEMV_INPUT_PER_PE = 512
DEFAULT_DECODE_KV_CHUNK = 1

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


def solve_embed_chunked_dispatch(
    *,
    grid_width: int,
    hidden_size: int,
    vocab_size: int,
    num_tokens: int,
    budget_bytes: int = EMBED_PE_DATA_BUDGET_BYTES,
) -> dict[str, int] | None:
    """Jointly pick (rowsPerPe, hiddenPerPe, hiddenShardCount, tokensPerChunk)
    that makes the chunked-dispatch embed kernel fit per-PE memory while
    still covering the full vocabulary at the given grid width.

    Constraints:
      * rowsPerPe * grid_width >= vocab_size   (every row is held somewhere)
      * (rowsPerPe + tokensPerChunk) * hiddenPerPe * 4 <= budget_bytes
      * hiddenPerPe * hiddenShardCount == hidden_size (clean partition)

    Strategy: given grid_width, rowsPerPe = ceil(vocab_size / grid_width) is
    fixed by the coverage constraint. Then for each divisor of hidden_size
    (largest first), check whether the budget constraint holds at the
    default tokensPerChunk. Shrink tokensPerChunk only as a fallback.

    Returns None only when no tokensPerChunk >= 1 and no divisor of
    hidden_size can satisfy the budget — a truly unrescueable shape. The
    caller must then accept that the pre-chunked compile will overflow.
    """
    if (
        grid_width <= 0
        or hidden_size <= 0
        or vocab_size <= 0
        or num_tokens <= 0
        or budget_bytes <= 0
    ):
        return None
    rows_per_pe = ceil_div(vocab_size, grid_width)
    default_tokens = max(1, min(num_tokens, EMBED_DEFAULT_TOKENS_PER_CHUNK))
    divisors_desc = sorted(divisors_ascending(hidden_size), reverse=True)
    # Outer loop: tokens_per_chunk from default down to 1.
    # Inner loop: hiddenPerPe from largest divisor down to 1.
    # First tuple to fit wins (prefers larger chunks + larger hiddenPerPe
    # for fewer host dispatches and larger per-PE working sets).
    candidate_tokens = sorted({default_tokens, *range(default_tokens, 0, -1)}, reverse=True)
    for tokens_per_chunk in candidate_tokens:
        for hidden_per_pe in divisors_desc:
            footprint = (rows_per_pe + tokens_per_chunk) * hidden_per_pe * 4
            if footprint <= budget_bytes:
                return {
                    "rowsPerPe": rows_per_pe,
                    "hiddenPerPe": hidden_per_pe,
                    "hiddenShardCount": hidden_size // hidden_per_pe,
                    "tokensPerChunk": tokens_per_chunk,
                    "perPeFootprintBytes": footprint,
                    "budgetBytes": budget_bytes,
                    "gridWidth": grid_width,
                }
    return None


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
    # The legacy projection computed rows_per_pe across the full grid
    # (width * height PEs). That assumed a 1-D kernel holding full hidden
    # per PE. Chunked dispatch lowers width to grid_width and uses a
    # separate hidden-shard axis: every PE only needs to cover its own
    # row shard at grid_width, not grid_width × grid_height.
    tuple_ = solve_embed_chunked_dispatch(
        grid_width=grid_width,
        hidden_size=hidden_dim,
        vocab_size=vocab_size,
        num_tokens=max_seq_len,
    )
    params: dict[str, int] = {
        "hidden_size": hidden_dim,
        "num_tokens": max_seq_len,
    }
    if tuple_ is not None:
        # Embed's per-kernel grid is grid_width × hiddenShardCount. The
        # `height` param is the hidden-shard count, not the global
        # memory-plan grid_height which sizes other kernels' rectangles.
        params["rows_per_pe"] = tuple_["rowsPerPe"]
        params["height"] = tuple_["hiddenShardCount"]
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
        "lm_head_gemv_stable": {
            "out_dim": lm_head_out_dim,
            "in_dim_per_pe": gemv_input_per_pe,
            "num_blocks_per_row": gemv_blocks,
        },
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
        "attn_head512": attention_compile_params(
            grid_width=grid_width,
            head_dim=global_head_dim,
            q_len=attention_tokens,
            kv_len=attention_tokens,
        ),
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
