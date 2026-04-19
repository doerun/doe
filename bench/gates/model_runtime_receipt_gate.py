#!/usr/bin/env python3
"""Validate a doe model runtime receipt artifact against its schema.

Required usage shape:
  python3 bench/gates/model_runtime_receipt_gate.py \\
    --receipt bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json \\
    [--require-fits] [--require-full-coverage] [--min-kernel-coverage-pct N]

Schema validation is always performed. The optional flags lift assertions
from 'structural' to 'claim' quality: require-fits fails when the memory
plan cannot fit the model in SRAM; require-full-coverage fails when any
host-plan kernel lacks a registered runtime-ready fixture; and the
coverage-pct floor lets lanes accept a tolerable per-model kernel gap
while still gating against regression.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", required=True)
    p.add_argument("--schema", default="config/doe-model-runtime-receipt.schema.json")
    p.add_argument("--require-fits", action="store_true")
    p.add_argument("--require-full-coverage", action="store_true")
    p.add_argument("--min-kernel-coverage-pct", type=int, default=0)
    p.add_argument(
        "--require-structural-full-coverage",
        action="store_true",
        help="Fail unless laneStatus is structural_full_coverage (new taxonomy).",
    )
    p.add_argument(
        "--require-execution",
        action="store_true",
        help="Fail unless executionStatus is simulator_success or hardware_success. "
             "This is the strict 'model ran end-to-end' assertion distinct from structural coverage.",
    )
    p.add_argument(
        "--min-chain-parity-patterns",
        type=int,
        default=0,
        help=(
            "Minimum number of host-plan kernel patterns that must appear in at "
            "least one passing chain-parity receipt. Enforces partial model-level "
            "parity coverage (user review item #4) without demanding every pattern."
        ),
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def main() -> int:
    args = parse_args()
    receipt_path = resolve(args.receipt)
    schema_path = resolve(args.schema)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: model runtime receipt gate: {exc}")
        return 1

    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(receipt),
        key=lambda e: tuple(str(p) for p in e.absolute_path),
    )
    failures = [
        f"{'.'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in errors
    ]

    if args.require_fits and not receipt.get("fits", False):
        failures.append(f"fits={receipt.get('fits')!r}, expected true")

    total = receipt.get("kernelCoverage", {}).get("total", 0)
    ready = receipt.get("kernelCoverage", {}).get("byStatus", {}).get("runtime_ready", 0)
    missing = receipt.get("kernelCoverage", {}).get("byStatus", {}).get("missing", 0)

    if args.require_full_coverage and missing != 0:
        failures.append(
            f"kernelCoverage.byStatus.missing={missing}, expected 0 "
            f"(missing patterns: {receipt['kernelCoverage'].get('patternsMissing', [])})"
        )

    if args.min_kernel_coverage_pct > 0 and total > 0:
        pct = int(round(ready * 100 / total))
        if pct < args.min_kernel_coverage_pct:
            failures.append(
                f"kernel coverage {ready}/{total} = {pct}%, expected >= {args.min_kernel_coverage_pct}%"
            )

    if args.require_structural_full_coverage:
        if receipt.get("laneStatus") != "structural_full_coverage":
            failures.append(
                f"laneStatus={receipt.get('laneStatus')!r}, expected 'structural_full_coverage'"
            )

    if args.require_execution:
        exec_status = receipt.get("executionStatus", "not_attempted")
        if exec_status not in ("simulator_success", "hardware_success"):
            failures.append(
                f"executionStatus={exec_status!r}, expected 'simulator_success' or 'hardware_success' "
                f"(blocker: {receipt.get('executionBlocker', 'unknown')!r})"
            )

    if args.min_chain_parity_patterns > 0:
        chain_evidence = receipt.get("chainParityEvidence", {})
        proven = chain_evidence.get("chainCoverageCount", 0)
        if proven < args.min_chain_parity_patterns:
            failures.append(
                f"chainParityEvidence.chainCoverageCount={proven}, expected >= "
                f"{args.min_chain_parity_patterns} "
                f"(proven: {chain_evidence.get('kernelPatternsChainProven', [])}, "
                f"unproven: {chain_evidence.get('kernelPatternsChainUnproven', [])})"
            )

    if failures:
        print("FAIL: model runtime receipt gate")
        for f in failures:
            print(f"  {f}")
        return 1

    coverage_pct = int(round(ready * 100 / total)) if total else 0
    exec_status = receipt.get("executionStatus", "unknown")
    blocker = receipt.get("executionBlocker", "unknown")
    exec_suffix = f", executionStatus={exec_status!r}"
    if exec_status == "not_attempted" and blocker != "none":
        exec_suffix += f" (blocker: {blocker!r})"
    chain_suffix = ""
    chain_evidence = receipt.get("chainParityEvidence")
    if isinstance(chain_evidence, dict):
        chain_suffix = (
            f", chainCoverage={chain_evidence.get('chainCoverageCount', 0)}"
            f"/{chain_evidence.get('chainCoverageTotal', 0)}"
        )
    print(
        f"PASS: model runtime receipt gate "
        f"({receipt.get('modelId', '?')}, coverage={ready}/{total} = {coverage_pct}%, "
        f"fits={receipt.get('fits')}, laneStatus={receipt.get('laneStatus')!r}{exec_suffix}{chain_suffix})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
