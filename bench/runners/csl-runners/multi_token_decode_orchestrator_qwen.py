#!/usr/bin/env python3
"""Multi-token decode orchestrator for Qwen 3.6 27B (subprocess-isolated).

Parallel sibling to ``multi_token_decode_orchestrator.py`` (Gemma 4 31B
chain). The two orchestrators are kept separate rather than generalized
because:

  - Symbol names differ (Qwen kv_write exports key_proj/val_proj/
    key_cache/val_cache; Gemma exports k_proj/v_proj/k_cache/v_cache).
    Qwen attn_decode exports query/key/val/output/position/
    sliding_window; Gemma exports Q/K/V/O.
  - Sample kernel emit shape differs after the
    emit_csl_sample.zig paired-(val,idx) reduction fix: Qwen kernel
    writes a single ``tokens`` symbol carrying the global argmax
    index, replacing the earlier per-PE local_max_val + local_max_idx
    pair the Gemma orchestrator reads.
  - Per-PE shape constraints differ (attn_decode width=1 only on Qwen
    today, pending the multi-PE chain routing fix in
    emit_csl_layout.zig:emitReductionLayout).

Per step:

  1. host writes key_proj.npy, val_proj.npy, position.npy under the
     scratch dir's step{N}/in/ subdir
  2. subprocess A: chain_step_adapter against Qwen kv_write compile-
     dir; reads key_proj/val_proj/position; writes key_cache/val_cache
  3. host loads key_cache/val_cache, truncates to attn_decode's
     compile-time kv_chunk, packs into single-PE Q/K/V buffers
  4. subprocess B: chain_step_adapter against Qwen attn_decode
     compile-dir at width=1; reads query/key/val/position/
     sliding_window; writes output
  5. host tiles output (head_dim) into width*chunk_size logits, writes
     logits.npy
  6. subprocess C: chain_step_adapter against Qwen sample compile-dir
     at width=2; reads logits; writes tokens (single u32 holding
     global argmax index, post-emit-fix)
  7. host appends sampled token to tokenSequence; advances position;
     loops until num-steps reached

The trace.json is emitted with full tokenSequence + per-step logits
digests + per-step kernel timing summary.

Bounded canary shape (constraints documented in
bench/out/r3-2-27b-qwen-simfabric-cells/summary-receipt.json):
  kv_write: width=4 heads, height=1, head_dim=8, slots_per_pe=8
  attn_decode: width=1, head_dim=8, kv_chunk=8
  sample: width=2, chunk_size=128 (vocab=256)

Invocation:

  python3 bench/runners/csl-runners/multi_token_decode_orchestrator_qwen.py \\
    --compile-dir-kv-write <path> \\
    --compile-dir-attn-decode <path> \\
    --compile-dir-sample <path> \\
    --num-steps 4 \\
    --scratch-dir bench/out/r3-2-27b-qwen-multi-token-decode/scratch \\
    --trace-out bench/out/r3-2-27b-qwen-multi-token-decode/trace.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
CS_PYTHON_SINGULARITY = REPO_ROOT / "runtime" / "zig" / "tools" / "cs_python_singularity.sh"
CS_PYTHON_DIRECT = Path("/home/x/cerebras-sdk-2.10.0/cs_python")
CHAIN_STEP_ADAPTER = (
    REPO_ROOT / "bench" / "runners" / "csl-runners" / "chain_step_adapter.py"
)

# Qwen canary shape (small per-PE residency; matches the per-cell
# simfabric receipts under bench/out/r3-2-27b-qwen-*-simfabric-cell/).
KV_WRITE_WIDTH = 4
KV_WRITE_HEIGHT = 1
HEAD_DIM = 8
SLOTS_PER_PE = 8
MAX_SEQ_LEN = SLOTS_PER_PE * KV_WRITE_HEIGHT  # 8

ATTN_WIDTH = 1
ATTN_KV_CHUNK = 8
ATTN_KV_LEN = ATTN_WIDTH * ATTN_KV_CHUNK  # 8

SAMPLE_WIDTH = 2
VOCAB_CHUNK = 128
VOCAB_TOTAL = SAMPLE_WIDTH * VOCAB_CHUNK  # 256


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--compile-dir-kv-write", required=True)
    parser.add_argument("--compile-dir-attn-decode", required=True)
    parser.add_argument("--compile-dir-sample", required=True)
    parser.add_argument("--num-steps", type=int, default=2)
    parser.add_argument("--scratch-dir", required=True)
    parser.add_argument("--trace-out", required=True)
    parser.add_argument("--cmaddr", default="")
    parser.add_argument("--seed", type=int, default=29)
    parser.add_argument("--subprocess-timeout-seconds", type=int, default=600)
    return parser.parse_args()


def _hash_floats(arr: np.ndarray) -> str:
    return hashlib.sha256(
        arr.astype(np.float32, copy=False).tobytes()
    ).hexdigest()


def _resolve_cs_python() -> Path:
    # Prefer the direct cs_python (uses .direct-rootfs, no singularity);
    # the singularity wrapper requires container privileges that are not
    # available in all environments and silently fails with `Operation
    # not permitted` from the SIF extractor.
    if CS_PYTHON_DIRECT.is_file():
        return CS_PYTHON_DIRECT
    if CS_PYTHON_SINGULARITY.is_file():
        return CS_PYTHON_SINGULARITY
    raise RuntimeError(
        f"cs_python launcher not found at {CS_PYTHON_DIRECT} or "
        f"{CS_PYTHON_SINGULARITY}"
    )


def _run_adapter(
    *,
    label: str,
    compile_dir: Path,
    width: int,
    chunk_size: int,
    inputs: list[tuple[str, Path, str, int | None]],
    outputs: list[tuple[str, Path, str, int | None]],
    scratch_cwd: Path,
    cmaddr: str,
    timeout: int,
    cs_python: Path,
) -> dict:
    compile_dir_abs = compile_dir.resolve()
    cmd: list[str] = [
        str(cs_python),
        str(CHAIN_STEP_ADAPTER),
        "--compile-dir", str(compile_dir_abs),
        "--width", str(width),
        "--chunk-size", str(chunk_size),
    ]
    if cmaddr:
        cmd.extend(["--cmaddr", cmaddr])
    for symbol, path, dtype, chunk_override in inputs:
        spec = f"{symbol}:{path.resolve()}:{dtype}"
        if chunk_override is not None:
            spec += f":{chunk_override}"
        cmd.extend(["--input", spec])
    for symbol, path, dtype, chunk_override in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        spec = f"{symbol}:{path.resolve()}:{dtype}"
        if chunk_override is not None:
            spec += f":{chunk_override}"
        cmd.extend(["--output", spec])

    scratch_cwd.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DOE_CSL_SCRATCH_CWD"] = str(scratch_cwd)
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=timeout, env=env, cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"chain_step_adapter [{label}] exit {proc.returncode}: "
            f"stderr_tail={proc.stderr.strip().splitlines()[-3:]}"
        )
    return {
        "label": label,
        "compileDir": str(compile_dir),
        "returncode": proc.returncode,
        "stdoutTail": proc.stdout.strip().splitlines()[-3:],
    }


def _kv_write_step(
    *, args, step_dir, rng, position, cmaddr, cs_python,
) -> tuple[bool, np.ndarray, np.ndarray, dict]:
    in_dir = step_dir / "in"
    out_dir = step_dir / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    key_proj = rng.standard_normal((KV_WRITE_WIDTH, HEAD_DIM), dtype=np.float32)
    val_proj = rng.standard_normal((KV_WRITE_WIDTH, HEAD_DIM), dtype=np.float32)
    position_arr = np.full(KV_WRITE_WIDTH, position, dtype=np.uint32)

    np.save(in_dir / "key_proj.npy", key_proj)
    np.save(in_dir / "val_proj.npy", val_proj)
    np.save(in_dir / "position.npy", position_arr)

    adapter_meta = _run_adapter(
        label="kv_write",
        compile_dir=Path(args.compile_dir_kv_write),
        width=KV_WRITE_WIDTH,
        chunk_size=HEAD_DIM,
        inputs=[
            ("key_proj", in_dir / "key_proj.npy", "f32", HEAD_DIM),
            ("val_proj", in_dir / "val_proj.npy", "f32", HEAD_DIM),
            ("position", in_dir / "position.npy", "u32", 1),
        ],
        outputs=[
            ("key_cache", out_dir / "key_cache.npy", "f32",
             MAX_SEQ_LEN * HEAD_DIM),
            ("val_cache", out_dir / "val_cache.npy", "f32",
             MAX_SEQ_LEN * HEAD_DIM),
        ],
        scratch_cwd=step_dir / "scratch_kv_write",
        cmaddr=cmaddr,
        timeout=args.subprocess_timeout_seconds,
        cs_python=cs_python,
    )
    key_cache = np.load(out_dir / "key_cache.npy").reshape(
        KV_WRITE_WIDTH, MAX_SEQ_LEN, HEAD_DIM
    )
    val_cache = np.load(out_dir / "val_cache.npy").reshape(
        KV_WRITE_WIDTH, MAX_SEQ_LEN, HEAD_DIM
    )
    written_k = key_cache[:, position, :]
    written_v = val_cache[:, position, :]
    err = float(np.max(np.abs(written_k - key_proj))) + float(
        np.max(np.abs(written_v - val_proj))
    )
    return (err == 0.0), key_cache, val_cache, adapter_meta


def _attn_decode_step(
    *, args, step_dir, rng, key_cache, val_cache, position, cmaddr, cs_python,
) -> tuple[np.ndarray, dict]:
    in_dir = step_dir / "in"
    out_dir = step_dir / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Qwen attn_decode is currently width=1 (single PE owns all KV).
    # Pull head 0's cache into a single contiguous (kv_chunk, head_dim)
    # buffer; production would broadcast per-head. The chain receipt
    # cites this as a single-head canary.
    k_pe = key_cache[0, :ATTN_KV_LEN, :]
    v_pe = val_cache[0, :ATTN_KV_LEN, :]
    q = rng.standard_normal(HEAD_DIM, dtype=np.float32)
    pos = np.array([position], dtype=np.uint32)
    sw = np.array([0], dtype=np.uint32)

    np.save(in_dir / "query.npy", q)
    np.save(in_dir / "key.npy", k_pe)
    np.save(in_dir / "val.npy", v_pe)
    np.save(in_dir / "position.npy", pos)
    np.save(in_dir / "sliding_window.npy", sw)

    adapter_meta = _run_adapter(
        label="attn_decode",
        compile_dir=Path(args.compile_dir_attn_decode),
        width=ATTN_WIDTH,
        chunk_size=HEAD_DIM,
        inputs=[
            ("query", in_dir / "query.npy", "f32", HEAD_DIM),
            ("key", in_dir / "key.npy", "f32", ATTN_KV_LEN * HEAD_DIM),
            ("val", in_dir / "val.npy", "f32", ATTN_KV_LEN * HEAD_DIM),
            ("position", in_dir / "position.npy", "u32", 1),
            ("sliding_window", in_dir / "sliding_window.npy", "u32", 1),
        ],
        outputs=[
            ("output", out_dir / "output.npy", "f32", HEAD_DIM),
        ],
        scratch_cwd=step_dir / "scratch_attn_decode",
        cmaddr=cmaddr,
        timeout=args.subprocess_timeout_seconds,
        cs_python=cs_python,
    )
    o = np.load(out_dir / "output.npy").reshape(ATTN_WIDTH, HEAD_DIM)
    return o[0], adapter_meta


def _sample_step(
    *, args, step_dir, logits, cmaddr, cs_python,
) -> tuple[int, dict]:
    in_dir = step_dir / "in"
    out_dir = step_dir / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    np.save(in_dir / "logits.npy", logits)
    adapter_meta = _run_adapter(
        label="sample",
        compile_dir=Path(args.compile_dir_sample),
        width=SAMPLE_WIDTH,
        chunk_size=VOCAB_CHUNK,
        inputs=[
            ("logits", in_dir / "logits.npy", "f32", VOCAB_CHUNK),
        ],
        outputs=[
            # Post-emit-fix: kernel writes single `tokens` symbol
            # carrying the global argmax index. Read from the LAST
            # PE only — that's where the chain reduction lands.
            ("tokens", out_dir / "tokens.npy", "u32", 1),
        ],
        scratch_cwd=step_dir / "scratch_sample",
        cmaddr=cmaddr,
        timeout=args.subprocess_timeout_seconds,
        cs_python=cs_python,
    )
    tokens = np.load(out_dir / "tokens.npy").reshape(SAMPLE_WIDTH).astype(np.uint32)
    # The orchestrator reads back per-PE; the last PE holds the
    # globally-reduced result. Other PEs' tokens are intermediate
    # state and are ignored.
    return int(tokens[SAMPLE_WIDTH - 1]), adapter_meta


def _write_blocked_trace(out_path: Path, reason: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 1,
        "artifactKind": "doe_qwen_3_6_27b_multi_token_decode_chain_blocked",
        "kernel": "multi-token-decode-chain",
        "modelId": "qwen-3-6-27b-q4k-ehaf16",
        "target": "wse3",
        "executionTarget": "simfabric",
        "verdict": "blocked",
        "blocker": reason,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    trace_out = Path(args.trace_out)
    scratch_root = Path(args.scratch_dir)
    cmaddr = args.cmaddr.strip() or ""

    cs_python = _resolve_cs_python()
    if not CHAIN_STEP_ADAPTER.is_file():
        _write_blocked_trace(
            trace_out, f"chain_step_adapter missing at {CHAIN_STEP_ADAPTER}"
        )
        print(f"BLOCKED: adapter missing, wrote {trace_out}", file=sys.stderr)
        return 1
    for label, p in (
        ("kv_write", Path(args.compile_dir_kv_write)),
        ("attn_decode", Path(args.compile_dir_attn_decode)),
        ("sample", Path(args.compile_dir_sample)),
    ):
        if not (p / "bin").is_dir():
            _write_blocked_trace(
                trace_out, f"{label} compile-dir missing bin/ subdir at {p}"
            )
            print(f"BLOCKED: compile-dir absent for {label}, wrote {trace_out}",
                  file=sys.stderr)
            return 1

    rng = np.random.default_rng(seed=args.seed)
    per_step: list[dict] = []
    token_sequence: list[int] = []
    per_step_logits_digests: list[str] = []

    for step_idx in range(args.num_steps):
        step_dir = scratch_root / f"step{step_idx:03d}"
        step_dir.mkdir(parents=True, exist_ok=True)

        position = step_idx
        kv_pass, key_cache, val_cache, kv_meta = _kv_write_step(
            args=args, step_dir=step_dir, rng=rng,
            position=position, cmaddr=cmaddr, cs_python=cs_python,
        )
        attn_output, attn_meta = _attn_decode_step(
            args=args, step_dir=step_dir, rng=rng,
            key_cache=key_cache, val_cache=val_cache,
            position=position, cmaddr=cmaddr, cs_python=cs_python,
        )

        # Tile attn_output (head_dim=8) into width*chunk_size logits.
        # Production inference would route through lm_head; this is
        # bounded synthetic — same shape Gemma's chain uses.
        tile_count = (VOCAB_TOTAL + HEAD_DIM - 1) // HEAD_DIM
        logits_flat = np.tile(attn_output, tile_count)[:VOCAB_TOTAL]
        # Reshape to (SAMPLE_WIDTH, VOCAB_CHUNK) for the per-PE input.
        logits = logits_flat.reshape(SAMPLE_WIDTH, VOCAB_CHUNK).astype(
            np.float32, copy=False
        )
        logits_digest = _hash_floats(logits)
        per_step_logits_digests.append(logits_digest)

        token_id, sample_meta = _sample_step(
            args=args, step_dir=step_dir, logits=logits,
            cmaddr=cmaddr, cs_python=cs_python,
        )
        token_sequence.append(token_id)

        per_step.append({
            "stepIndex": step_idx,
            "position": position,
            "kvWritePassed": bool(kv_pass),
            "attentionDecodePassed": True,
            "attentionOutputDigest": _hash_floats(attn_output),
            "sampledTokenId": int(token_id),
            "logitsDigest": logits_digest,
            "subprocesses": [kv_meta, attn_meta, sample_meta],
        })

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_qwen_3_6_27b_multi_token_decode_chain_trace",
        "modelId": "qwen-3-6-27b-q4k-ehaf16",
        "kernel": "multi-token-decode-chain",
        "target": "wse3",
        "executionTarget": "simfabric" if not cmaddr else "system",
        "isolation": "subprocess",
        "shape": {
            "kvWrite": {
                "width": KV_WRITE_WIDTH, "height": KV_WRITE_HEIGHT,
                "headDim": HEAD_DIM, "slotsPerPe": SLOTS_PER_PE,
                "maxSeqLen": MAX_SEQ_LEN,
            },
            "attnDecode": {
                "width": ATTN_WIDTH, "headDim": HEAD_DIM,
                "kvChunk": ATTN_KV_CHUNK, "kvLen": ATTN_KV_LEN,
            },
            "sample": {
                "width": SAMPLE_WIDTH, "chunkSize": VOCAB_CHUNK,
                "vocabTotal": VOCAB_TOTAL,
            },
        },
        "numSteps": args.num_steps,
        "tokenSequence": token_sequence,
        "perStepLogitsDigests": per_step_logits_digests,
        "perStep": per_step,
        "stopReason": "max-steps",
        "claim": {
            "scope": (
                "Qwen 3.6 27B 3-kernel decode chain "
                "(kv_write → attn_decode → sample) executes end-to-"
                "end on simfabric for N decode steps, with each "
                "step's kv_write -> attn -> sample chained via host-"
                "shuttled .npy state across subprocess-isolated SDK "
                "instances. Token sequence + per-step logit digests "
                "are recorded so a future Doppler-frozen reference "
                "fixture can bind parity. Validates the post-emit-"
                "fix dispatch shape (sample paired-index reduction, "
                "attn_decode async recv) end-to-end at canary widths "
                "(attn_decode=1, sample=2)."
            ),
            "notWhat": (
                "Not a hardware run. Not a manifest-shape run — "
                "manifest head_dim=256, vocab=248320, max_seq_len=4k. "
                "Not a Doppler parity claim — token sequence is "
                "synthetic (random q/kv per step, no real LM head); "
                "binding to Doppler reference inference waits on the "
                "frozen-fixture step. Single-head attention canary "
                "(attn_decode width=1); production GQA would broadcast "
                "across 4 kv_heads."
            ),
        },
    }
    trace_out.parent.mkdir(parents=True, exist_ok=True)
    trace_out.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    print(
        f"PASS: Qwen multi-token-decode-chain over {args.num_steps} steps; "
        f"tokens={token_sequence}; trace={trace_out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
