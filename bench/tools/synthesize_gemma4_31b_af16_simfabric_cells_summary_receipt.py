#!/usr/bin/env python3
"""Synthesize the Gemma 4 31B AF16 simfabric-cells summary receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CELLS_ROOT = (
    REPO_ROOT / "bench/runners/csl-runners/gemma-4-31b-af16-cells"
)
DEFAULT_RECEIPTS_ROOT = REPO_ROOT / "bench/out"
DEFAULT_SMOKE_CONFIG = (
    REPO_ROOT / "runtime/zig/examples/execution-v1/gemma-4-31b-af16-smoke.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-gemma-af16-simfabric-cells/summary-receipt.json"
)

CELLS: tuple[dict[str, Any], ...] = (
    {
        "kernel": "lm_head_prefill",
        "layout_basename": "lm_head_prefill_layout.csl",
        "pe_program_basename": "lm_head_prefill_pe_program.csl",
        "run_basename": "lm_head_prefill_run.py",
        "receipt_dir_basename": (
            "r3-1-31b-gemma-af16-lm-head-prefill-simfabric-cell"
        ),
        "layout_was_patched": False,
        "patch_summary": (
            "No patch. The cell source keeps the production "
            "lm_head_prefill kernel stem and forwards the same "
            "width/height/out_dim/out_dim_per_pe/in_dim_per_pe params as "
            "the manifest HostPlan, with bounded values for local simfabric."
        ),
    },
)

PENDING_KERNEL_FAMILIES = (
    "embed",
    "rmsnorm",
    "rope",
    "attn_small",
    "residual",
    "gelu_gated",
    "gemv",
    "kv_write",
    "sample",
    "attn_decode_sliding",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells-root", type=Path, default=DEFAULT_CELLS_ROOT)
    parser.add_argument("--receipts-root", type=Path, default=DEFAULT_RECEIPTS_ROOT)
    parser.add_argument("--smoke-config", type=Path, default=DEFAULT_SMOKE_CONFIG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


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


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _load_cell(
    cell_spec: dict[str, Any],
    cells_root: Path,
    receipts_root: Path,
) -> dict[str, Any]:
    layout_path = cells_root / str(cell_spec["layout_basename"])
    pe_path = cells_root / str(cell_spec["pe_program_basename"])
    run_path = cells_root / str(cell_spec["run_basename"])
    receipt_path = (
        receipts_root / str(cell_spec["receipt_dir_basename"]) / "receipt.json"
    )

    sources_present = (
        layout_path.is_file() and pe_path.is_file() and run_path.is_file()
    )
    entry: dict[str, Any] = {
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

    receipt = _load_json(receipt_path)
    if receipt is None:
        entry["verdict"] = "not_attempted"
        entry["receiptMissing"] = True
        return entry

    entry["verdict"] = receipt.get("verdict", "unknown")
    entry["parityMaxAbsDiff"] = receipt.get("parityMaxAbsDiff")
    entry["parityMaxRelDiff"] = receipt.get("parityMaxRelDiff")
    entry["shape"] = receipt.get("shape")
    entry["executionTarget"] = receipt.get("executionTarget")
    entry["receiptSha256"] = _sha256_file(receipt_path)
    return entry


def _verdict(cells: list[dict[str, Any]]) -> str:
    pass_count = sum(1 for cell in cells if cell.get("verdict") == "pass")
    fail_count = sum(1 for cell in cells if cell.get("verdict") == "fail")
    missing_count = sum(
        1 for cell in cells if cell.get("verdict") == "not_attempted"
    )
    if fail_count:
        return "fail"
    if missing_count and not pass_count:
        return "not_attempted"
    if missing_count:
        return "partial"
    return "pass_with_documented_canary_constraints"


def main() -> int:
    args = parse_args()
    cells = [
        _load_cell(spec, args.cells_root, args.receipts_root)
        for spec in CELLS
    ]
    pass_count = sum(1 for cell in cells if cell.get("verdict") == "pass")
    fail_count = sum(1 for cell in cells if cell.get("verdict") == "fail")
    not_attempted_count = sum(
        1 for cell in cells if cell.get("verdict") == "not_attempted"
    )
    verdict = _verdict(cells)
    smoke = _load_json(args.smoke_config)

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_31b_af16_simfabric_cells_summary",
        "modelId": (
            (smoke or {}).get("modelId")
            or "gemma-4-31b-it-text-q4k-ehf16-af16"
        ),
        "executionTarget": "simfabric",
        "verdict": verdict,
        "cellCount": len(cells),
        "passCount": pass_count,
        "failCount": fail_count,
        "notAttemptedCount": not_attempted_count,
        "cells": cells,
        "pendingKernelFamilies": list(PENDING_KERNEL_FAMILIES),
        "smokeConfigPath": _rel(args.smoke_config),
        "smokeConfigSha256": (
            _sha256_file(args.smoke_config) if args.smoke_config.is_file() else None
        ),
        "claim": {
            "scope": (
                "Gemma 4 31B AF16 per-kernel CSL canary evidence for "
                "the production-named lm_head_prefill dense-GEMV "
                "kernel. The cell compiles at bounded shape, runs on "
                "simfabric, stages f16 activation and weight payloads, "
                "reduces f32 partials across the row chain, and compares "
                "the sink output against a host f32 reference."
            ),
            "notWhat": (
                "Not a hardware run. Not a manifest-shape run. Not full "
                "31B token-output evidence. Not coverage for every Gemma "
                "compile target; pendingKernelFamilies names the remaining "
                "cell families that need their own receipts. The full-fabric "
                "lm-head path remains blocked on the documented simfabric "
                "D2H ceiling and is closed by hardware endpoint evidence, "
                "not by this bounded cell."
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {_rel(args.out)} verdict={verdict} "
        f"pass={pass_count}/{len(cells)}"
    )
    passing_verdicts = (
        "pass",
        "partial",
        "pass_with_documented_canary_constraints",
    )
    return 0 if verdict in passing_verdicts else 1


if __name__ == "__main__":
    sys.exit(main())
