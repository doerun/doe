#!/usr/bin/env python3
"""Synthesize a bounded multi-token decode receipt at the same scale as the
existing single-step bounded chain.

Mitigates "Bounded integrated KV decode+sample receipt extension" from
docs/cerebras-evidence-ledger-gemma.md (Remaining no-hardware evidence gaps).

The single-step chain already proves:
  kv_write -> attention_decode -> sample
on simfabric at width=4, head_dim=32 with token id 1913 emitted
(`bench/out/r3-1-31b-bounded-decode-integrated/receipt.json`).

A real multi-token decode requires a stateful runner that:
  - preserves K/V cache state across iterations (currently each
    runner zero-initializes its caches),
  - bumps target_position each step (currently hardcoded to 7 in
    bench/runners/csl-runners/kv_write_sim_runner.py),
  - threads sampled token IDs back into the next prefill step,
  - emits per-step logits digests and a token-id sequence.

That runner does not exist; producing one requires simfabric execution
per iteration plus host-side state management. This tool synthesizes a
typed-blocker receipt that records:
  - the single-step chain that DOES exist (with hashes),
  - the contract a multi-token runner would emit,
  - the named blocker (`stateful_multi_token_runner_absent`) so the
    receipt does not invent a sequence.

The receipt is consumed by reviewers who want to know "where does
multi-token decode evidence stand?" without inventing fake tokens.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._receipt_hash_guard import (  # noqa: E402
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
)
DEFAULT_SOURCE_RECEIPT = (
    REPO_ROOT / "bench/out/r3-1-31b-bounded-decode-integrated/receipt.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-bounded-multi-token-decode/receipt.json"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source-receipt",
        type=Path,
        default=DEFAULT_SOURCE_RECEIPT,
        help=(
            "Path to the existing single-step bounded decode receipt "
            "(doe_bounded_decode_integrated_receipt)."
        ),
    )
    p.add_argument(
        "--decode-steps",
        type=int,
        default=8,
        help=(
            "Number of decode steps the receipt's multi-token contract "
            "would emit. The synthesized receipt records this as the "
            "target step count; the actual sequence stays empty until a "
            "stateful runner produces it."
        ),
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.source_receipt.is_file():
        sys.stderr.write(
            f"synthesize_bounded_multi_token_decode_receipt: source "
            f"receipt {args.source_receipt} not found. Run the bounded "
            f"single-step chain first.\n"
        )
        return 2

    source = json.loads(args.source_receipt.read_text(encoding="utf-8"))
    chain = source.get("chain") or []
    decode_chain = source.get("decodeChain") or {}

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_bounded_multi_token_decode_receipt",
        "target": "wse3",
        "executionTarget": "simfabric",
        "purpose": (
            "Bounded multi-token decode receipt at the same simfabric "
            "scale as the single-step chain. Records the multi-token "
            "contract and binds to the existing single-step traces. "
            "Carries a typed blocker until a stateful runner produces "
            "real per-iteration K/V state and token IDs."
        ),
        "sourceSingleStepReceipt": {
            "path": str(
                args.source_receipt.relative_to(REPO_ROOT)
                if args.source_receipt.is_absolute()
                and str(args.source_receipt).startswith(str(REPO_ROOT))
                else args.source_receipt
            ),
            "stages": [
                {
                    "stage": s.get("stage"),
                    "kernel": s.get("kernel"),
                    "trace": s.get("trace"),
                    "traceSha256": s.get("traceSha256"),
                    "runtimePassed": s.get("runtimePassed"),
                }
                for s in chain
            ],
            "singleStepDecodeChain": decode_chain,
        },
        "multiTokenContract": {
            "targetDecodeSteps": args.decode_steps,
            "boundedShape": (
                "width=4, head_dim=32, max_seq_len=64, vocab_chunk=1024"
            ),
            "perStepFields": [
                "kv_write at target_position=step",
                "attention_decode against cached K/V[0..step+1]",
                "sample over vocab chunk -> token_id[step]",
                "per-step logits digest",
            ],
            "stateInvariants": [
                "K/V cache preserved across steps (no zero-init between iterations)",
                "target_position monotonically advances by 1 each step",
                "stop_reason is max_tokens (greedy, fixed-length budget)",
            ],
        },
        "blocker": {
            "class": "stateful_multi_token_runner_absent",
            "detail": (
                "Each existing simfabric runner (kv_write_sim_runner, "
                "attention_decode_sim_runner, sample) zero-initializes "
                "its caches on entry and runs a single launch. A real "
                "multi-token decode receipt needs an orchestrator that "
                "loads a single SdkRuntime, preserves K/V symbols across "
                "calls, advances `position` per step, and threads sampled "
                "token IDs back as the next attention input. That runner "
                "is ~hundreds of lines of new code plus the manifest "
                "decoupling between the kernels' compile-time width and "
                "the runtime cache slot count."
            ),
            "namedRunnerExtensions": [
                "bench/runners/csl-runners/kv_write_sim_runner.py: "
                "parameterize target_position via CLI; do not zero-init "
                "the cache when --resume-from-prev-position is set.",
                "bench/runners/csl-runners/attention_decode_sim_runner.py: "
                "accept K/V cache state from a prior step and bind it as "
                "input rather than re-projecting.",
                "bench/runners/csl-runners/(new)multi_token_decode_orchestrator.py: "
                "drive the chain N times, persist a token-id sequence and "
                "per-step logits digest array, emit "
                "doe_bounded_multi_token_decode_trace.",
            ],
        },
        "tokenSequence": [],
        "perStepLogitsDigests": [],
        "stopReason": "blocked_runner_absent",
        "claim": {
            "scope": (
                "Single-step bounded decode chain is in-hand and "
                "hash-pinned at width=4 head_dim=32. The multi-token "
                "extension contract is named, the named blocker is "
                "explicit, and the receipt does not invent a token "
                "sequence."
            ),
            "notWhat": (
                "Not a multi-token decode evidence claim — tokenSequence "
                "is empty by design. Not a hardware receipt. Not 31B "
                "shape. The single-step chain it binds to is bounded "
                "synthetic inputs, not real weights."
            ),
            "summary": (
                "Single-step decode chain pinned (token id 1913); "
                "multi-token extension blocked on stateful runner."
            ),
        },
    }

    try:
        enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    except ReceiptHashSpineError as err:
        sys.stderr.write(
            "synthesize_bounded_multi_token_decode_receipt: receipt hash "
            f"spine rejected emit:\n  {err}\n"
        )
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.out} (typed blocker, "
        f"sourceStages={len(chain)}, targetSteps={args.decode_steps})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
