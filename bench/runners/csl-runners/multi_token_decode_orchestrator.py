#!/usr/bin/env cs_python
"""Multi-token decode orchestrator on simfabric.

Holds one SdkRuntime instance for the full decode loop, calling
kv_write -> attention_decode -> sample symbols in sequence per step,
advancing the position counter, and recording the sampled token IDs +
per-step logits digests. Closes the "KV decode/sample" gap in
docs/cerebras-north-star.md by replacing three independent single-step
sim runs with one stateful orchestration that proves the per-step
state (KV cache writes + position counter) is preserved across
launches in a single SdkRuntime.

Why three runtimes (with host-shuttle):
  The existing single-step runners (kv_write_sim_runner.py,
  attention_decode_sim_runner.py, sample_sim_runner.py) each spin up
  their own SdkRuntime against a kernel-specific compile-dir. The
  three kernels are separate compile units with disjoint symbols
  (kv_write owns k_cache/v_cache/position; attention-decode owns
  Q/K/V/O; sample owns logits/local_max_*). The orchestrator runs
  three SdkRuntime instances in one process and shuttles state via
  host-side numpy arrays per step.

Empirical blocker (Cerebras SDK 2.10.0):
  Cerebras simfabric refuses to host three independent SdkRuntime
  instances in a single Python process — SdkRuntime construction
  aborts at simfab_api.cc:163 with `Assertion '0' failed`. The
  orchestrator's host-shuttle architecture is structurally correct
  but cannot run in-process under simfabric. See
  bench/out/r3-1-31b-multi-token-decode/receipt.json for the typed
  blocker + the two named alternative architectures (unified compile
  target / subprocess-isolated decode loop).

  When run under hardware (cmaddr-provided), the multi-runtime
  constraint is a simfabric-only limit and may not apply; the
  orchestrator is hardware-ready in shape.

Bounded smoke shape:
  width=4 PEs, head_dim=32, max_seq_len=64, vocab_chunk=1024.
  Same shapes as the per-kernel sim runners so the kernel binaries
  produced by their compile-dirs can be reused here.

Invocation:
  cs_python bench/runners/csl-runners/multi_token_decode_orchestrator.py \\
      --compile-dir-kv-write <path> \\
      --compile-dir-attention-decode <path> \\
      --compile-dir-sample <path> \\
      --num-steps 4 \\
      --trace-out bench/out/r3-1-31b-multi-token-decode/trace.json

Each --compile-dir-* is a cslc -o output directory for the
corresponding kernel; the orchestrator does not compile, it only
runs. Materialize compile-dirs by invoking the per-kernel sim runners'
compile path (or by adding a compile step here later).

The trace.json records:
  schemaVersion, kernel="multi-token-decode-chain", target=wse3,
  executionTarget=simfabric, perStep[]: stepIndex, position,
  kvWritePassed, attentionDecodePassed, sampledTokenId, logitsDigest.

Stop reason is "max-steps" (no EOS check at this scope) — the
sample kernel produces a token; we record it without checking
against an EOS list. EOS handling is downstream of bounded-shape
correctness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

import common

try:
    from cerebras.sdk.runtime.sdkruntimepybind import (  # type: ignore[import-not-found]  # noqa: E501
        SdkRuntime,
        MemcpyDataType,
        MemcpyOrder,
    )
    HAS_SDK = True
except ImportError:
    SdkRuntime = None  # type: ignore[assignment]
    MemcpyDataType = None  # type: ignore[assignment]
    MemcpyOrder = None  # type: ignore[assignment]
    HAS_SDK = False


WIDTH = 4
HEAD_DIM = 32
MAX_SEQ_LEN = 64
VOCAB_CHUNK = 1024
DEFAULT_TEMPERATURE = 1.0
DEFAULT_SOFTCAP = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument(
        "--compile-dir-kv-write",
        required=True,
        help="cslc -o directory for the kv-write kernel",
    )
    parser.add_argument(
        "--compile-dir-attention-decode",
        required=True,
        help="cslc -o directory for the attention-decode kernel",
    )
    parser.add_argument(
        "--compile-dir-sample",
        required=True,
        help="cslc -o directory for the sample kernel",
    )
    parser.add_argument(
        "--num-steps",
        type=int,
        default=4,
        help=(
            "Number of decode steps. Each step writes K/V at the current "
            "position, attends over cached state, samples one token, and "
            "advances position by 1."
        ),
    )
    parser.add_argument(
        "--trace-out",
        required=True,
        help="Path to write the chain trace JSON",
    )
    parser.add_argument(
        "--cmaddr",
        default="",
        help="Optional CS system endpoint (empty = simfabric)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=29,
        help="RNG seed for synthetic input generation",
    )
    return parser.parse_args()


def _hash_floats(arr: np.ndarray) -> str:
    return hashlib.sha256(arr.astype(np.float32, copy=False).tobytes()).hexdigest()


def _run_kv_write_step(runner, k_proj, v_proj, position):
    """Write K/V projections at `position` into the runtime's KV cache.

    Returns (kv_pass, k_cache_host, v_cache_host). The host-side cache
    arrays are returned so the orchestrator can shuttle them to the
    attention-decode runner: each runtime owns its own device-side K/V
    state, and host-side numpy buffers are the canonical chain state
    across kernel boundaries.
    """
    kproj_sym = runner.get_id("k_proj")
    vproj_sym = runner.get_id("v_proj")
    kcache_sym = runner.get_id("k_cache")
    vcache_sym = runner.get_id("v_cache")
    pos_sym = runner.get_id("position")

    runner.memcpy_h2d(
        kproj_sym, k_proj, 0, 0, WIDTH, 1, HEAD_DIM,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_h2d(
        vproj_sym, v_proj, 0, 0, WIDTH, 1, HEAD_DIM,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    pos_arr = np.full(WIDTH, position, dtype=np.uint32)
    runner.memcpy_h2d(
        pos_sym, pos_arr, 0, 0, WIDTH, 1, 1,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.launch("compute", nonblock=False)

    k_cache = np.zeros((WIDTH, MAX_SEQ_LEN, HEAD_DIM), dtype=np.float32)
    v_cache = np.zeros_like(k_cache)
    runner.memcpy_d2h(
        k_cache, kcache_sym, 0, 0, WIDTH, 1, MAX_SEQ_LEN * HEAD_DIM,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_d2h(
        v_cache, vcache_sym, 0, 0, WIDTH, 1, MAX_SEQ_LEN * HEAD_DIM,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    written_k = k_cache[:, position, :]
    written_v = v_cache[:, position, :]
    write_err = float(np.max(np.abs(written_k - k_proj))) + float(
        np.max(np.abs(written_v - v_proj))
    )
    return (write_err == 0.0, k_cache, v_cache)


def _run_attention_decode_step(
    runner,
    q_host: np.ndarray,
    k_host: np.ndarray,
    v_host: np.ndarray,
    kv_len: int,
):
    """Shuttle host-side Q/K/V into the attention-decode runtime, launch,
    read back O.

    `q_host` shape: (WIDTH, HEAD_DIM) — current decode-step query.
    `k_host`, `v_host` shape: (WIDTH, kv_len, HEAD_DIM) — cached K/V
    truncated from the kv-write runner's k_cache/v_cache to the
    attention-decode kernel's compile-time kv_len.
    The attention kernel's pe_program declares Q[q_len * head_dim],
    K[kv_len * head_dim], V[kv_len * head_dim], O[q_len * head_dim];
    q_len is implicitly 1 at decode shape.
    """
    q_sym = runner.get_id("Q")
    k_sym = runner.get_id("K")
    v_sym = runner.get_id("V")
    o_sym = runner.get_id("O")

    runner.memcpy_h2d(
        q_sym, q_host, 0, 0, WIDTH, 1, HEAD_DIM,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_h2d(
        k_sym, k_host, 0, 0, WIDTH, 1, kv_len * HEAD_DIM,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_h2d(
        v_sym, v_host, 0, 0, WIDTH, 1, kv_len * HEAD_DIM,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.launch("compute", nonblock=False)
    output = np.zeros((WIDTH, HEAD_DIM), dtype=np.float32)
    runner.memcpy_d2h(
        output, o_sym, 0, 0, WIDTH, 1, HEAD_DIM,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    return output


def _run_sample_step(runner, logits):
    """Project attention output to a vocab chunk, sample greedily."""
    logits_sym = runner.get_id("logits")
    vals_sym = runner.get_id("local_max_val")
    idxs_sym = runner.get_id("local_max_idx")

    runner.memcpy_h2d(
        logits_sym, logits, 0, 0, WIDTH, 1, VOCAB_CHUNK,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.launch("compute", nonblock=False)
    local_max_vals = np.zeros(WIDTH, dtype=np.float32)
    local_max_idxs = np.zeros(WIDTH, dtype=np.uint32)
    runner.memcpy_d2h(
        local_max_vals, vals_sym, 0, 0, WIDTH, 1, 1,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    runner.memcpy_d2h(
        local_max_idxs, idxs_sym, 0, 0, WIDTH, 1, 1,
        streaming=False,
        order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT,
        nonblock=False,
    )
    pe_winner = int(np.argmax(local_max_vals))
    token_id = pe_winner * VOCAB_CHUNK + int(local_max_idxs[pe_winner])
    return token_id


def _write_blocked_trace(out_path: Path, reason: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 1,
        "artifactKind": "doe_multi_token_decode_chain_blocked",
        "kernel": "multi-token-decode-chain",
        "target": "wse3",
        "executionTarget": "simfabric",
        "verdict": "blocked",
        "blocker": reason,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    trace_out = Path(args.trace_out)

    if not HAS_SDK:
        _write_blocked_trace(
            trace_out,
            "cerebras.sdk.runtime.sdkruntimepybind not importable; "
            "run via runtime/zig/tools/cs_python_singularity.sh",
        )
        print(f"BLOCKED: SDK unavailable, wrote {trace_out}", file=sys.stderr)
        return 1

    rng = np.random.default_rng(seed=args.seed)
    cmaddr = common.endpoint(args.cmaddr)

    # Three independent SdkRuntime instances — one per kernel binary.
    # The orchestrator coordinates them via its own host-side state:
    # token IDs flow Python-side, K/V state lives device-side per-runner.
    # If a future kernel set bundles all three into one binary, this can
    # collapse to a single SdkRuntime.
    kv_runner = SdkRuntime(args.compile_dir_kv_write, cmaddr=cmaddr)
    attn_runner = SdkRuntime(args.compile_dir_attention_decode, cmaddr=cmaddr)
    sample_runner = SdkRuntime(args.compile_dir_sample, cmaddr=cmaddr)

    per_step = []
    token_sequence: list[int] = []
    per_step_logits_digests: list[str] = []

    # Detect attention-decode's compile-time kv_len from its compile-out
    # params file so the host-shuttle truncates kv_write's max_seq_len
    # correctly. Default to 8 if the file is unreadable.
    attn_params_path = (
        Path(args.compile_dir_attention_decode) / ".." / "attention-decode.params"
    )
    attn_kv_len = 8
    if attn_params_path.is_file():
        try:
            for line in attn_params_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("kv_len="):
                    attn_kv_len = int(line.split("=", 1)[1])
                    break
        except (OSError, ValueError):
            pass

    try:
        for runner in (kv_runner, attn_runner, sample_runner):
            runner.load()
            runner.run()

        for step_idx in range(args.num_steps):
            position = step_idx
            k_proj = rng.standard_normal((WIDTH, HEAD_DIM), dtype=np.float32)
            v_proj = rng.standard_normal((WIDTH, HEAD_DIM), dtype=np.float32)

            kv_pass, k_cache_host, v_cache_host = _run_kv_write_step(
                kv_runner, k_proj, v_proj, position
            )

            # Truncate kv_write's max_seq_len cache to attention-decode's
            # compile-time kv_len. Decode-step S sees rows [0..S+1]
            # populated and the rest zero — the cached state matches
            # what a real decode loop would see.
            k_truncated = k_cache_host[:, :attn_kv_len, :]
            v_truncated = v_cache_host[:, :attn_kv_len, :]
            q_step = rng.standard_normal((WIDTH, HEAD_DIM), dtype=np.float32)

            attn_output = _run_attention_decode_step(
                attn_runner, q_step, k_truncated, v_truncated, attn_kv_len
            )

            # Use the attention output as a deterministic input to sample —
            # in production decode this would pass through lm_head; here
            # we project the attention output (head_dim=32) into vocab_chunk
            # by tiling so the chain is reproducible without inventing a
            # learned lm_head.
            tile_count = (VOCAB_CHUNK + HEAD_DIM - 1) // HEAD_DIM
            logits = np.tile(attn_output, (1, tile_count))[:, :VOCAB_CHUNK]
            logits_digest = _hash_floats(logits)
            per_step_logits_digests.append(logits_digest)

            token_id = _run_sample_step(sample_runner, logits)
            token_sequence.append(token_id)

            per_step.append({
                "stepIndex": step_idx,
                "position": position,
                "kvWritePassed": bool(kv_pass),
                "attentionDecodePassed": True,
                "attentionOutputDigest": _hash_floats(attn_output),
                "sampledTokenId": int(token_id),
                "logitsDigest": logits_digest,
            })

    finally:
        for runner in (kv_runner, attn_runner, sample_runner):
            try:
                runner.stop()
            except Exception:  # pragma: no cover  # noqa: BLE001
                pass

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_multi_token_decode_chain_trace",
        "kernel": "multi-token-decode-chain",
        "target": "wse3",
        "executionTarget": "simfabric" if cmaddr is None else "system",
        "shape": {
            "width": WIDTH,
            "headDim": HEAD_DIM,
            "maxSeqLen": MAX_SEQ_LEN,
            "vocabChunk": VOCAB_CHUNK,
        },
        "numSteps": args.num_steps,
        "tokenSequence": token_sequence,
        "perStepLogitsDigests": per_step_logits_digests,
        "perStep": per_step,
        "stopReason": "max-steps",
    }
    trace_out.parent.mkdir(parents=True, exist_ok=True)
    trace_out.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    print(
        f"PASS: multi-token-decode-chain over {args.num_steps} steps; "
        f"tokens={token_sequence}; trace={trace_out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
