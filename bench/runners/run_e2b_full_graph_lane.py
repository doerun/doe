#!/usr/bin/env python3
"""E2B full-graph lane driver.

Runs the end-to-end Doe pipeline for Gemma 4 E2B:
  WGSL kernels → classifier → HostPlan → memory-plan → runtime-config →
  simulator-plan → model-level runtime receipt.

Produces artifacts under bench/out/e2b-full-graph/:
  - host-plan.json
  - memory-plan.json
  - runtime-config.json
  - simulator-plan.json
  - launch-simulator.sh
  - gemma-4-e2b-runtime-receipt.json   (the model-level receipt)
  - gemma-4-e2b-runtime-receipt.md

The 17,433-PE E2B topology is too large to cslc-compile + sim-run as a
single governed lane today — this driver produces structural evidence
(host-plan, memory-plan fits=true, per-kernel runtime-readiness) so the
model can be compared against 31B later when streaming-runtime lands.
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
        default="runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json",
    )
    p.add_argument(
        "--host-plan-tool",
        default="runtime/zig/zig-out/bin/doe-csl-host-plan-tool",
    )
    p.add_argument(
        "--bundle-root",
        default="bench/out/e2b-full-graph",
    )
    p.add_argument(
        "--registry",
        default="config/csl-runtime-fixtures.json",
    )
    p.add_argument(
        "--receipt-json",
        default="bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    )
    p.add_argument(
        "--receipt-md",
        default="bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.md",
    )
    return p.parse_args()


def run(cmd: list[str]) -> None:
    print("[e2b-lane]", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    if proc.returncode != 0:
        sys.exit(proc.returncode)


def main() -> int:
    args = parse_args()
    bundle_root = REPO_ROOT / args.bundle_root
    bundle_root.mkdir(parents=True, exist_ok=True)

    # Step 1: lower the execution manifest into HostPlan + memory-plan +
    # runtime-config + simulator-plan. The `steps` mode accepts the rich
    # model-config shape (modelConfig + placementPolicy + layerPattern).
    run([
        str(REPO_ROOT / args.host_plan_tool),
        "--input", str(REPO_ROOT / args.execution_manifest),
        "--bundle-root", str(bundle_root),
        "--mode", "steps",
    ])

    # Step 2: bind the artifacts into a model-level runtime receipt. Chain
    # parity receipts that intersect this model's host-plan kernel
    # patterns are bound as chainParityEvidence so the receipt carries
    # end-to-end composition evidence, not just per-kernel parity.
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

    # Step 3: derive the stream-graph from the memory plan + manifest. The
    # receipt's streamingMigration.runtimePath enum decides whether this
    # artifact is load-bearing (sdk_layout_streaming) or informational
    # (memcpy_rpc). We emit it unconditionally so downstream tooling can
    # reason about the orchestration shape before the streaming runtime
    # lands.
    run([
        sys.executable,
        str(REPO_ROOT / "bench" / "tools" / "build_stream_graph.py"),
        "--execution-manifest", str(REPO_ROOT / args.execution_manifest),
        "--memory-plan", str(bundle_root / "memory-plan.json"),
        "--out-json", str(bundle_root / "gemma-4-e2b-stream-graph.json"),
    ])

    # Step 4: validate the stream-graph and emit the concrete per-layer
    # stream-execution-plan. This plan is the artifact the SdkLayout
    # streaming executor (priority #6, not yet implemented) will consume
    # when it lands — a shovel-ready hand-off.
    run([
        sys.executable,
        str(REPO_ROOT / "bench" / "tools" / "validate_stream_graph.py"),
        "--stream-graph", str(bundle_root / "gemma-4-e2b-stream-graph.json"),
        "--out-json", str(bundle_root / "gemma-4-e2b-stream-execution-plan.json"),
    ])

    # Step 5: run the Python dry-run streaming executor against the plan +
    # receipt. Emits a predicted-runtime trace that future hardware runs
    # can be diff'd against.
    run([
        sys.executable,
        str(REPO_ROOT / "bench" / "tools" / "dry_run_streaming_executor.py"),
        "--execution-plan", str(bundle_root / "gemma-4-e2b-stream-execution-plan.json"),
        "--model-receipt", str(REPO_ROOT / args.receipt_json),
        "--out-json", str(bundle_root / "gemma-4-e2b-dry-run-trace.json"),
    ])

    print(f"[e2b-lane] done: {args.receipt_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
