#!/usr/bin/env python3
"""Gemma 4 31B full-graph lane driver.

Same shape as run_e2b_full_graph_lane.py but pointed at the 31B smoke
manifest. The result is a model-level runtime receipt whose
streamingMigration section flags whether the simple memcpy RPC runtime
is sufficient or the SdkLayout streaming runtime (priority #6) must be
adopted.

A 58,056-PE 31B topology is not practical to cslc-compile + sim-run as
a single governed lane, so this driver produces structural evidence
(HostPlan, memory-plan with fits check, per-layer compile artifact reuse
factor, double-buffered working-set feasibility) rather than runtime
parity at full scale.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--execution-manifest",
        default="runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json",
    )
    p.add_argument(
        "--host-plan-tool",
        default="runtime/zig/zig-out/bin/doe-csl-host-plan-tool",
    )
    p.add_argument(
        "--bundle-root",
        default="bench/out/31b-full-graph",
    )
    p.add_argument(
        "--registry",
        default="config/csl-runtime-fixtures.json",
    )
    p.add_argument(
        "--receipt-json",
        default="bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json",
    )
    p.add_argument(
        "--receipt-md",
        default="bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.md",
    )
    return p.parse_args()


def run(cmd: list[str]) -> None:
    print("[31b-lane]", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    if proc.returncode != 0:
        sys.exit(proc.returncode)


def main() -> int:
    args = parse_args()
    bundle_root = REPO_ROOT / args.bundle_root
    bundle_root.mkdir(parents=True, exist_ok=True)

    run([
        str(REPO_ROOT / args.host_plan_tool),
        "--input", str(REPO_ROOT / args.execution_manifest),
        "--bundle-root", str(bundle_root),
        "--mode", "steps",
    ])

    chain_receipts = [
        "bench/out/kernel-chain-evidence/elementwise-double-x2/chain-parity.json",
        "bench/out/kernel-chain-evidence/elementwise-subprocess/chain-parity.json",
        "bench/out/kernel-chain-evidence/gather-then-double/chain-parity.json",
        "bench/out/kernel-chain-evidence/rope-then-attention/chain-parity.json",
        "bench/out/kernel-chain-evidence/gather-rope-attention/chain-parity.json",
        "bench/out/kernel-chain-evidence/reduce-then-double/chain-parity.json",
        "bench/out/kernel-chain-evidence/rope-then-decode/chain-parity.json",
        "bench/out/kernel-chain-evidence/gemv-then-double/chain-parity.json",
        "bench/out/kernel-chain-evidence/attention-then-sample/chain-parity.json",
        "bench/out/kernel-chain-evidence/rope-then-kv-write/chain-parity.json",
        "bench/out/kernel-chain-evidence/tiled-matmul-chain/chain-parity.json",
        "bench/out/kernel-chain-evidence/gather-rope-attention-sample/chain-parity.json",
    ]
    chain_flags: list[str] = []
    for rel_path in chain_receipts:
        chain_flags += ["--chain-parity-receipt", str(REPO_ROOT / rel_path)]
    run([
        sys.executable,
        str(REPO_ROOT / "bench" / "tools" / "build_model_runtime_receipt.py"),
        "--execution-manifest", str(REPO_ROOT / args.execution_manifest),
        "--host-plan", str(bundle_root / "host-plan.json"),
        "--memory-plan", str(bundle_root / "memory-plan.json"),
        "--runtime-config", str(bundle_root / "runtime-config.json"),
        "--simulator-plan", str(bundle_root / "simulator-plan.json"),
        "--registry", str(REPO_ROOT / args.registry),
        *chain_flags,
        "--out-json", str(REPO_ROOT / args.receipt_json),
        "--out-md", str(REPO_ROOT / args.receipt_md),
    ])

    run([
        sys.executable,
        str(REPO_ROOT / "bench" / "tools" / "build_stream_graph.py"),
        "--execution-manifest", str(REPO_ROOT / args.execution_manifest),
        "--memory-plan", str(bundle_root / "memory-plan.json"),
        "--out-json", str(bundle_root / "gemma-4-31b-stream-graph.json"),
    ])

    run([
        sys.executable,
        str(REPO_ROOT / "bench" / "tools" / "validate_stream_graph.py"),
        "--stream-graph", str(bundle_root / "gemma-4-31b-stream-graph.json"),
        "--out-json", str(bundle_root / "gemma-4-31b-stream-execution-plan.json"),
    ])

    run([
        sys.executable,
        str(REPO_ROOT / "bench" / "tools" / "dry_run_streaming_executor.py"),
        "--execution-plan", str(bundle_root / "gemma-4-31b-stream-execution-plan.json"),
        "--model-receipt", str(REPO_ROOT / args.receipt_json),
        "--out-json", str(bundle_root / "gemma-4-31b-dry-run-trace.json"),
    ])

    print(f"[31b-lane] done: {args.receipt_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
