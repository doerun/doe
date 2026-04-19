#!/usr/bin/env python3
"""Run every CSL-plan evidence gate in one pass.

Exercises the full ladder this repo has built for the shared Doe
WGSL → CSL/Vulkan/Metal/D3D12 plan:

  1. schema_gate                   — every schema-target entry validates
  2. csl_runtime_fixture_gate      — 12 runtime-ready CSL fixtures
  3. wgsl_backend_matrix_gate      — cross-backend matrix at N/N, SDK-optional
  4. model_runtime_receipt_gate    — E2B + 31B structural + chain-parity coverage
  5. kernel_chain_parity_gate      — every chain-parity receipt (bit_exact / bit_close)
  6. verify_cmaddr_propagation.py  — hardware-endpoint plumbing smoke

Exits 0 iff every gate passes. Prints per-gate PASS/FAIL and a summary
footer so /loop iterations can spot regressions at a glance.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CHAIN_RECEIPTS = [
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

DEFAULT_MODEL_RECEIPTS = [
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--min-csl-runtime-ready",
        type=int,
        default=12,
        help="wgsl_backend_matrix_gate --min-csl-runtime-ready threshold.",
    )
    p.add_argument(
        "--min-chain-parity-patterns",
        type=int,
        default=10,
        help="model_runtime_receipt_gate --min-chain-parity-patterns threshold.",
    )
    p.add_argument(
        "--require-chain-bit-exact",
        action="store_true",
        help="Upgrade kernel_chain_parity_gate to --require-bit-exact instead of --require-bit-close.",
    )
    p.add_argument(
        "--out-json",
        default="bench/out/csl-plan-sweep.json",
        help="Write a structured result summary here.",
    )
    p.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact pass/fail table at the end.",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p.resolve())


def run_gate(label: str, cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    passed = proc.returncode == 0
    tail = (proc.stdout or "").strip().splitlines()[-1:] + (proc.stderr or "").strip().splitlines()[-1:]
    summary = " ".join(tail)[:240] if tail else ""
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {label}: {summary}")
    return passed, summary


def main() -> int:
    args = parse_args()

    results: list[dict] = []

    # 0. Regenerate the ELF fingerprint artifact so schema_gate validates
    # a current snapshot rather than a stale one. Cheap — just sha256 over
    # on-disk ELFs that already compiled.
    passed, note = run_gate(
        "csl-kernel-fingerprints-regen",
        [sys.executable, str(REPO_ROOT / "bench/tools/fingerprint_kernel_compiles.py")],
    )
    results.append({"gate": "csl-kernel-fingerprints-regen", "passed": passed, "note": note})

    # 0b. Regenerate the E2B-vs-31B dry-run trace diff so the cross-model
    # comparison artifact tracks the latest lane outputs.
    passed, note = run_gate(
        "dry-run-trace-diff-regen",
        [sys.executable, str(REPO_ROOT / "bench/tools/diff_dry_run_traces.py"),
         "--left", "bench/out/e2b-full-graph/gemma-4-e2b-dry-run-trace.json",
         "--right", "bench/out/31b-full-graph/gemma-4-31b-dry-run-trace.json",
         "--label-left", "gemma-4-e2b",
         "--label-right", "gemma-4-31b",
         "--out-json", "bench/out/e2b-vs-31b-dry-run-diff.json"],
    )
    results.append({"gate": "dry-run-trace-diff-regen", "passed": passed, "note": note})

    # 0c. Regenerate the E2B lookahead-sensitivity sweep (4 dry-runs, 3
    # diffs against lookahead=2 baseline).
    passed, note = run_gate(
        "lookahead-sensitivity-regen:e2b",
        [sys.executable, str(REPO_ROOT / "bench/tools/sweep_lookahead_sensitivity.py")],
    )
    results.append({"gate": "lookahead-sensitivity-regen:e2b", "passed": passed, "note": note})

    # 0d. 31B lookahead-sensitivity — same shape at larger scale.
    passed, note = run_gate(
        "lookahead-sensitivity-regen:31b",
        [sys.executable, str(REPO_ROOT / "bench/tools/sweep_lookahead_sensitivity.py"),
         "--execution-manifest", "runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json",
         "--memory-plan", "bench/out/31b-full-graph/memory-plan.json",
         "--model-receipt", "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json",
         "--work-dir", "bench/out/lookahead-sensitivity/31b",
         "--out-json", "bench/out/lookahead-sensitivity/31b-lookahead-sensitivity.json"],
    )
    results.append({"gate": "lookahead-sensitivity-regen:31b", "passed": passed, "note": note})

    # 1. schema_gate
    passed, note = run_gate(
        "schema",
        [sys.executable, str(REPO_ROOT / "bench/gates/schema_gate.py")],
    )
    results.append({"gate": "schema", "passed": passed, "note": note})

    # 2. csl_runtime_fixture_gate
    passed, note = run_gate(
        "csl-runtime-fixture",
        [sys.executable, str(REPO_ROOT / "bench/gates/csl_runtime_fixture_gate.py"),
         "--require-ready-receipts"],
    )
    results.append({"gate": "csl-runtime-fixture", "passed": passed, "note": note})

    # 3. wgsl_backend_matrix_gate
    passed, note = run_gate(
        "wgsl-backend-matrix",
        [sys.executable, str(REPO_ROOT / "bench/gates/wgsl_backend_matrix_gate.py"),
         "--require-vulkan-ready", "--require-metal-ready", "--require-d3d12-ready",
         "--sdk-optional", "--min-csl-runtime-ready", str(args.min_csl_runtime_ready)],
    )
    results.append({"gate": "wgsl-backend-matrix", "passed": passed, "note": note})

    # 4. model_runtime_receipt_gate × N
    for receipt_path in DEFAULT_MODEL_RECEIPTS:
        stem = Path(receipt_path).stem
        label = f"model-runtime-receipt:{stem}"
        passed, note = run_gate(
            label,
            [sys.executable, str(REPO_ROOT / "bench/gates/model_runtime_receipt_gate.py"),
             "--receipt", receipt_path,
             "--require-fits", "--require-structural-full-coverage",
             "--min-kernel-coverage-pct", "100",
             "--min-chain-parity-patterns", str(args.min_chain_parity_patterns)],
        )
        results.append({"gate": label, "passed": passed, "note": note})

    # 5. kernel_chain_parity_gate × N
    for receipt_path in DEFAULT_CHAIN_RECEIPTS:
        stem = Path(receipt_path).stem
        label = f"kernel-chain-parity:{Path(receipt_path).parent.name}"
        chain_cmd = [sys.executable, str(REPO_ROOT / "bench/gates/kernel_chain_parity_gate.py"),
                     "--receipt", receipt_path]
        if args.require_chain_bit_exact:
            chain_cmd.append("--require-bit-exact")
        else:
            chain_cmd.append("--require-bit-close")
        passed, note = run_gate(label, chain_cmd)
        results.append({"gate": label, "passed": passed, "note": note})

    # 6. cmaddr propagation
    passed, note = run_gate(
        "cmaddr-propagation",
        [sys.executable, str(REPO_ROOT / "bench/tools/verify_cmaddr_propagation.py")],
    )
    results.append({"gate": "cmaddr-propagation", "passed": passed, "note": note})

    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    all_passed = passed_count == total

    summary = {
        "schemaVersion": 1,
        "artifactKind": "csl_plan_sweep_report",
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "allPassed": all_passed,
        "results": results,
    }
    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print()
    if args.summary:
        # Compact pass/fail column for quick scanning.
        max_label = max((len(r["gate"]) for r in results), default=10)
        print(f"{'gate':<{max_label}}  status")
        print(f"{'-' * max_label}  ------")
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"{r['gate']:<{max_label}}  {status}")
        print()
    print(f"csl-plan sweep: {passed_count}/{total} gates passed "
          f"→ {rel(out_path)}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
