#!/usr/bin/env python3
"""Aggregate the Qwen 3.6 27B multi-token decode trace into a hash-bound receipt.

Companion to ``bench/runners/csl-runners/multi_token_decode_orchestrator_qwen.py``
(the simfabric chain runner) and ``bench/tools/_receipt_hash_guard.py``
(the rung-1 hash-spine guard).

The orchestrator emits a `doe_qwen_3_6_27b_multi_token_decode_chain_trace`
artifact that captures token sequence, per-step logits digests, and
attention-output digests. This tool walks that trace plus the per-kernel
compile dirs and the smoke config + host plan it was driven from, then
emits a typed receipt that:

  - cites smokeConfigPath + smokeConfigHash;
  - cites hostPlanPath + hostPlanHash (when a host-plan bundle is
    materialized; the chain orchestrator can run against ad-hoc compile
    dirs so this is optional);
  - records per-kernel compile-dir digests (sha256 of layout.csl,
    pe_program.csl, pe_program.metadata.json — same triple the byte-
    identity verifier uses);
  - hash-chains every cited path through the receipt-hash-guard so
    downstream readers can re-derive identity.

Pipeline:

  1. Read the trace.
  2. Hash the smoke config + (optional) host plan.
  3. For each declared kernel (kv_write / attn_decode / sample), read
     its compile-dir's per-kernel triple and compute sha256s.
  4. Emit the typed receipt at ``--out`` with the rung-1 hash spine
     enforced.

Usage::

  python3 bench/tools/aggregate_qwen_3_6_27b_multi_token_decode_receipt.py \\
    --trace bench/out/r3-2-27b-qwen-multi-token-decode/trace.json \\
    --smoke-config runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json \\
    --kv-write-compile-dir <path> \\
    --attn-decode-compile-dir <path> \\
    --sample-compile-dir <path> \\
    --out bench/out/r3-2-27b-qwen-multi-token-decode/receipt.json
"""

from __future__ import annotations

import argparse
import hashlib
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

DEFAULT_TRACE = (
    REPO_ROOT / "bench/out/r3-2-27b-qwen-multi-token-decode/trace.json"
)
DEFAULT_SMOKE_CONFIG = (
    REPO_ROOT
    / "runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json"
)
DEFAULT_OUT = (
    REPO_ROOT / "bench/out/r3-2-27b-qwen-multi-token-decode/receipt.json"
)
PER_KERNEL_FILES = (
    "layout.csl",
    "pe_program.csl",
    "pe_program.metadata.json",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    p.add_argument(
        "--smoke-config", type=Path, default=DEFAULT_SMOKE_CONFIG
    )
    p.add_argument("--host-plan", type=Path, default=None)
    p.add_argument("--kv-write-compile-dir", type=Path, default=None)
    p.add_argument("--attn-decode-compile-dir", type=Path, default=None)
    p.add_argument("--sample-compile-dir", type=Path, default=None)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _kernel_digest(kernel: str, compile_dir: Path | None) -> dict:
    if compile_dir is None:
        return {
            "kernel": kernel,
            "compileDirPath": None,
            "perFile": {name: None for name in PER_KERNEL_FILES},
            "bound": False,
        }
    artifacts: dict[str, str | None] = {}
    bound = True
    for name in PER_KERNEL_FILES:
        h = _sha256_file(compile_dir / name)
        artifacts[name] = h
        if h is None:
            bound = False
    return {
        "kernel": kernel,
        "compileDirPath": _rel(compile_dir),
        "perFile": artifacts,
        "bound": bound,
    }


def main() -> int:
    args = parse_args()
    if not args.trace.is_file():
        sys.stderr.write(
            f"aggregate_qwen_3_6_27b_multi_token_decode_receipt: "
            f"trace not found at {args.trace}\n"
        )
        return 2
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    if trace.get("artifactKind") != \
            "doe_qwen_3_6_27b_multi_token_decode_chain_trace":
        sys.stderr.write(
            f"unexpected artifactKind: {trace.get('artifactKind')!r}\n"
        )
        return 2

    smoke_hash = _sha256_file(args.smoke_config)
    host_plan_hash = (
        _sha256_file(args.host_plan) if args.host_plan is not None else None
    )

    kernel_records = [
        _kernel_digest("kv_write", args.kv_write_compile_dir),
        _kernel_digest("attn_decode", args.attn_decode_compile_dir),
        _kernel_digest("sample", args.sample_compile_dir),
    ]
    bound_kernels = sum(1 for r in kernel_records if r["bound"])

    receipt: dict = {
        "schemaVersion": 1,
        "artifactKind": "doe_qwen_3_6_27b_multi_token_decode_chain_receipt",
        "modelId": trace.get("modelId", "qwen-3-6-27b-q4k-ehaf16"),
        "modelFamily": "qwen3",
        "target": trace.get("target", "wse3"),
        "executionTarget": trace.get("executionTarget", "simfabric"),
        "isolation": trace.get("isolation", "subprocess"),
        "shape": trace.get("shape", {}),
        "numSteps": trace.get("numSteps", 0),
        "tokenSequence": trace.get("tokenSequence", []),
        "perStepLogitsDigests": trace.get("perStepLogitsDigests", []),
        "perStep": trace.get("perStep", []),
        "stopReason": trace.get("stopReason"),
        "tracePath": _rel(args.trace),
        "traceHash": _sha256_file(args.trace),
        "smokeConfigPath": _rel(args.smoke_config),
        "smokeConfigHash": smoke_hash,
        "kernelCompileDirs": kernel_records,
        "boundKernelCount": bound_kernels,
        "claim": {
            "scope": (
                "Qwen 3.6 27B 3-kernel decode chain "
                "(kv_write → attn_decode → sample) executes end-to-end "
                "on simfabric for N decode steps. Token sequence, "
                "per-step logits digest, and attention-output digest "
                "are bound to (smoke config, per-kernel compile-dir "
                "triples). Each per-kernel digest hashes the same "
                "(layout.csl, pe_program.csl, pe_program.metadata.json) "
                "triple the rung-6 byte-identity verifier uses."
            ),
            "notWhat": (
                "Not a hardware run. Not a manifest-shape run — manifest "
                "head_dim=256, vocab=248320, max_seq_len=4k; the chain "
                "runs at canary widths (kv_write width=4, attn_decode "
                "width=1, sample width=2). Not a Doppler parity claim — "
                "token sequence is synthetic; binding to Doppler "
                "reference inference waits on the frozen-fixture rung."
            ),
        },
    }
    if args.host_plan is not None:
        receipt["hostPlanPath"] = _rel(args.host_plan)
        receipt["hostPlanHash"] = host_plan_hash

    try:
        enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    except ReceiptHashSpineError as err:
        sys.stderr.write(
            "aggregate_qwen_3_6_27b_multi_token_decode_receipt: "
            f"receipt hash spine rejected emit:\n  {err}\n"
        )
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {_rel(args.out)} steps={receipt['numSteps']} "
        f"tokens={receipt['tokenSequence']} "
        f"boundKernels={bound_kernels}/{len(kernel_records)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
