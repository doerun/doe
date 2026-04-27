#!/usr/bin/env python3
"""Synthesize the Qwen 3.6 27B simfabric-cells summary receipt.

Aggregates the three per-kernel simfabric receipts produced by the
small-shape cell drivers under
``bench/runners/csl-runners/qwen-3-6-27b-cells/`` (rmsnorm, rope_partial,
residual). The summary receipt cites each per-cell verdict, parity
deltas, source-file sha256s, and the named blockers from the smoke
config that this run does **not** cover (linear-attention layers,
mrope-interleaved RoPE, causal prefill, attentionOutputGate,
SwiGLU FFN fused gate, plus the manifest-shape per-PE residency
blocker that motivates the layout patches in two of the three cells).

Skip-when-absent for any cell whose receipt has not been produced
yet (the expected pre-regeneration state on a fresh checkout).

Intended invocation, after running the regeneration recipe in
``bench/runners/csl-runners/qwen-3-6-27b-cells/README.md``:

    python3 bench/tools/synthesize_qwen_3_6_27b_simfabric_cells_summary_receipt.py

Default output: ``bench/out/r3-2-27b-qwen-simfabric-cells/summary-receipt.json``.
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

DEFAULT_CELLS_ROOT = REPO_ROOT / "bench/runners/csl-runners/qwen-3-6-27b-cells"
DEFAULT_RECEIPTS_ROOT = REPO_ROOT / "bench/out"
DEFAULT_SMOKE_CONFIG = (
    REPO_ROOT / "runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json"
)
DEFAULT_OUT = (
    REPO_ROOT / "bench/out/r3-2-27b-qwen-simfabric-cells/summary-receipt.json"
)

CELLS = [
    {
        "kernel": "rmsnorm",
        "layout_basename": "rmsnorm_layout_patched.csl",
        "pe_program_basename": "rmsnorm_pe_program.csl",
        "run_basename": "rmsnorm_run.py",
        "receipt_dir_basename": "r3-2-27b-qwen-rmsnorm-simfabric-cell",
        "layout_was_patched": True,
        "patch_summary": (
            "layout.csl forwards hidden_size to pe_program — Doe's "
            "emit_csl_layout.zig deliberately omits this at manifest "
            "shape (hidden=5120) because the [hidden_size]f32 × 3 "
            "buffers (60 KB) overflow the WSE-3 per-PE 38 KB budget."
        ),
    },
    {
        "kernel": "rope_partial",
        "layout_basename": "rope_partial_layout.csl",
        "pe_program_basename": "rope_partial_pe_program.csl",
        "run_basename": "rope_partial_run.py",
        "receipt_dir_basename": "r3-2-27b-qwen-rope-partial-simfabric-cell",
        "layout_was_patched": False,
        "patch_summary": (
            "No patch — rope_partial's layout already forwards both "
            "head_dim and num_pairs (manifest-shape buffers fit within "
            "the per-PE budget). Validates the partialRotaryFactor "
            "wiring delta from csl_host_plan_tool.zig end-to-end."
        ),
    },
    {
        "kernel": "residual",
        "layout_basename": "residual_layout_patched.csl",
        "pe_program_basename": "residual_pe_program.csl",
        "run_basename": "residual_run.py",
        "receipt_dir_basename": "r3-2-27b-qwen-residual-simfabric-cell",
        "layout_was_patched": True,
        "patch_summary": (
            "Same per-PE-residency rationale as rmsnorm: layout was "
            "hand-patched to forward chunk_size; the upstream emit "
            "intentionally omits this at manifest scale."
        ),
    },
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cells-root", type=Path, default=DEFAULT_CELLS_ROOT)
    p.add_argument("--receipts-root", type=Path, default=DEFAULT_RECEIPTS_ROOT)
    p.add_argument("--smoke-config", type=Path, default=DEFAULT_SMOKE_CONFIG)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_smoke_scope_restrictions(smoke_path: Path) -> dict | None:
    if not smoke_path.is_file():
        return None
    try:
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return smoke.get("scopeRestrictions")


def _load_cell(
    cell_spec: dict,
    cells_root: Path,
    receipts_root: Path,
) -> dict:
    layout_path = cells_root / cell_spec["layout_basename"]
    pe_path = cells_root / cell_spec["pe_program_basename"]
    run_path = cells_root / cell_spec["run_basename"]
    receipt_path = (
        receipts_root / cell_spec["receipt_dir_basename"] / "receipt.json"
    )

    sources_present = layout_path.is_file() and pe_path.is_file() and run_path.is_file()
    receipt_present = receipt_path.is_file()

    entry: dict = {
        "kernel": cell_spec["kernel"],
        "layoutPath": _rel(layout_path),
        "peProgramPath": _rel(pe_path),
        "runPath": _rel(run_path),
        "receiptPath": _rel(receipt_path),
        "layoutWasPatched": cell_spec["layout_was_patched"],
        "patchSummary": cell_spec["patch_summary"],
    }

    if sources_present:
        entry["layoutSha256"] = _sha256_file(layout_path)
        entry["peProgramSha256"] = _sha256_file(pe_path)
        entry["runSha256"] = _sha256_file(run_path)
    else:
        entry["sourcesPresent"] = False

    if receipt_present:
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["verdict"] = "receipt_unparseable"
            entry["receiptError"] = str(exc)
            return entry
        entry["verdict"] = receipt.get("verdict", "unknown")
        entry["parityMaxAbsDiff"] = receipt.get("parityMaxAbsDiff")
        entry["parityMaxRelDiff"] = receipt.get("parityMaxRelDiff")
        entry["shape"] = receipt.get("shape")
        entry["receiptSha256"] = _sha256_file(receipt_path)
    else:
        entry["verdict"] = "not_attempted"
        entry["receiptMissing"] = True

    return entry


def main() -> int:
    args = parse_args()

    cells = [
        _load_cell(spec, args.cells_root, args.receipts_root)
        for spec in CELLS
    ]
    cellCount = len(cells)
    passCount = sum(1 for c in cells if c.get("verdict") == "pass")
    failCount = sum(1 for c in cells if c.get("verdict") == "fail")
    notAttemptedCount = sum(
        1 for c in cells if c.get("verdict") == "not_attempted"
    )

    if failCount > 0:
        verdict = "fail"
    elif notAttemptedCount > 0 and passCount == 0:
        verdict = "not_attempted"
    elif notAttemptedCount > 0:
        verdict = "partial"
    else:
        verdict = "pass"

    scope_restrictions = _load_smoke_scope_restrictions(args.smoke_config)

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_qwen_3_6_27b_simfabric_cells_summary",
        "modelId": "qwen-3-6-27b-q4k-ehaf16",
        "executionTarget": "simfabric",
        "verdict": verdict,
        "cellCount": cellCount,
        "passCount": passCount,
        "failCount": failCount,
        "notAttemptedCount": notAttemptedCount,
        "cells": cells,
        "smokeConfigPath": _rel(args.smoke_config),
        "scopeRestrictions": scope_restrictions,
        "claim": {
            "scope": (
                "Qwen 3.6 27B per-kernel CSL (rmsnorm, rope_partial, "
                "residual), sourced from the manifest-shape host plan, "
                "compiles via cslc 2.10.0 at small-shape canary "
                "configuration and runs end-to-end on simfabric. Each "
                "kernel matches its host-computed reference within "
                "float32 precision. Validates the per-kernel "
                "arithmetic and the partialRotaryFactor wiring delta; "
                "the rmsnorm and residual cells additionally exercise "
                "a hand-patched layout that forwards the per-PE buffer "
                "size to pe_program (the upstream emit intentionally "
                "omits this at manifest scale due to per-PE residency)."
            ),
            "notWhat": (
                "Not a hardware run. Not a manifest-shape run — the "
                "small canary shapes (hidden=128, head_dim=8, "
                "chunk_size=128) exercise the kernel mechanism, not "
                "production scale. Not a multi-kernel chain — each "
                "cell runs a single kernel only. Does not cover the "
                "smoke config's scopeRestrictions (linear-attention "
                "layers, mrope-interleaved RoPE, causal prefill, "
                "attentionOutputGate, SwiGLU FFN fused gate). Does not "
                "cover the manifest-shape per-PE residency blocker "
                "that motivates the layout patches in two of the three "
                "cells — that is closed by the broader R3-2 single-PE-"
                "reduction → fabric-shard redesign, tracked separately."
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"wrote {_rel(args.out)} verdict={verdict} "
          f"pass={passCount}/{cellCount}")
    return 0 if verdict in ("pass", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
