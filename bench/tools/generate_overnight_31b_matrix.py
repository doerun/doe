#!/usr/bin/env python3
"""Emit a matrix.json for the standard Gemma 4 31B overnight evidence sweep.

Composes lane-aware cells against the orchestrator at
`bench/runners/overnight_evidence_matrix.py`. Each cell:

  - has a stable, zero-padded ID so lexicographic sort matches numeric sort
  - declares `expectSuccessReceiptPath` pointing at a per-cell trace.json
    under the orchestrator's `cells/<cell-id>/` directory, so the resume
    gate composes cleanly with the runner's trace output
  - passes the matching `--trace-out` (and `--compile-out`) into the
    runner so the trace lands at the declared path
  - has a timeout sized to the cell's expected wallclock

Lane A pair sequencing relies on the orchestrator running cells in
submission order within a lane's pool, with `--max-webgpu-heavy 1`
serializing the Doppler reference/bundle export -> truncated CSL
prefill+decode chain.
No explicit dependency mechanism is needed.

Usage:
    python3 bench/tools/generate_overnight_31b_matrix.py \\
        --batch-dir bench/out/overnight/<utc> \\
        --out bench/out/overnight/<utc>/matrix.json

Then run the orchestrator against the emitted matrix and the same batch dir:
    python3 bench/runners/overnight_evidence_matrix.py \\
        --matrix bench/out/overnight/<utc>/matrix.json \\
        --out bench/out/overnight/<utc>

Inspect without committing:
    python3 bench/runners/overnight_evidence_matrix.py \\
        --matrix bench/out/overnight/<utc>/matrix.json \\
        --out bench/out/overnight/<utc> --dry-run
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOPPLER_ROOT = Path("/home/x/deco/doppler")
SDK_WRAPPER = REPO_ROOT / "runtime" / "zig" / "tools" / "cs_python_singularity.sh"
GEMMA_31B_MODEL_DIR = DOPPLER_ROOT / "models" / "local" / "gemma-4-31b-it-text-q4k-ehf16-af32"
GEMMA_31B_MANIFEST = GEMMA_31B_MODEL_DIR / "manifest.json"
GEMMA_31B_CONVERSION_CONFIG = (
    DOPPLER_ROOT / "src" / "config" / "conversion" / "gemma4"
    / "gemma-4-31b-it-text-q4k-ehf16-af32.json"
)
GEMMA_3_1B_BUNDLE = (
    DOPPLER_ROOT / "examples" / "program-bundles"
    / "gemma-3-1b-it-q4k-ehf16-af32.program-bundle.json"
)
GEMMA_31B_REFERENCE_RUNTIME_CONFIG = {
    "loading": {
        "memoryManagement": {
            "flushIntervalLayers": 1,
            "flushThresholdBytes": 134217728,
            "budget": {
                "enabled": True,
                "systemMemoryFraction": 0.5,
                "reserveBytes": 4294967296,
                "minimumBudgetBytes": 2147483648,
            },
        },
    },
    "inference": {
        # Replace the manifest's forced embedding residency. The 31B embedding
        # exceeds common WebGPU maxStorageBufferBindingSize limits and must use
        # the normal large-weight streaming path for local reference capture.
        "largeWeights": {
            "gpuResidentOverrides": [],
        },
        "batching": {
            "batchSize": 1,
            "readbackInterval": 1,
            "stopCheckMode": "per-token",
        },
        "generation": {
            "maxTokens": 8,
        },
        "kvcache": {
            "maxSeqLen": 2048,
            "layout": "contiguous",
            "kvDtype": "f16",
            "pageSize": 256,
            "tiering": {
                "mode": "off",
            },
        },
        "session": {
            "kvcache": {
                "maxSeqLen": 2048,
                "layout": "contiguous",
                "kvDtype": "f16",
                "pageSize": 256,
                "tiering": {
                    "mode": "off",
                },
            },
            "decodeLoop": {
                "batchSize": 1,
                "readbackInterval": 1,
                "stopCheckMode": "per-token",
                "readbackMode": "sequential",
                "ringTokens": 1,
                "ringStop": 1,
                "ringStaging": 1,
            },
        },
    },
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--batch-dir",
        default="",
        help=(
            "Orchestrator batch directory. Cell trace paths are templated as "
            "<batch-dir>/cells/<cell-id>/trace.json. Defaults to "
            "bench/out/overnight/<utc>; pass the same value to "
            "overnight_evidence_matrix.py --out."
        ),
    )
    p.add_argument("--out", default="", help="Where to write matrix.json.")
    p.add_argument(
        "--smoke-depths",
        default="1,2,4,8,16,32,61",
        help="Comma-separated layer counts for the 31B smoke ladder.",
    )
    p.add_argument(
        "--smoke-size",
        type=int,
        default=1024,
        help="--size for the 31B smoke runner.",
    )
    p.add_argument(
        "--include-lane-a",
        action="store_true",
        help=(
            "Include Lane A (Doppler 31B WebGPU reference + Program Bundle "
            "export, then Doe CSL truncated prefill+decode over that bundle). "
            "Default off so existing B+C smoke sweeps do not start a 31B "
            "WebGPU model load unless explicitly requested."
        ),
    )
    return p.parse_args()


def now_utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def cell_paths(batch_dir: Path, cell_id: str) -> tuple[Path, Path, Path]:
    cell_dir = batch_dir / "cells" / cell_id
    return cell_dir, cell_dir / "trace.json", cell_dir / "compile"


def lane_a_cells(batch_dir: Path) -> list[dict]:
    """Lane A (webgpu_heavy, cap 1): 31B Doppler WebGPU reference +
    Program Bundle -> CSL truncated prefill+decode. Sequential by
    submission order."""
    a1_id = "wg-31b-doppler-reference-bundle"
    a1_dir, _, _ = cell_paths(batch_dir, a1_id)
    doppler_bundle_dir = (
        DOPPLER_ROOT / "reports" / "program-bundles" / "doe-overnight"
        / batch_dir.name / a1_id
    )
    bundle_out = doppler_bundle_dir / "gemma-4-31b-program-bundle.json"
    reference_report = a1_dir / "reference.json"
    a1 = {
        "id": a1_id,
        "lane": "webgpu_heavy",
        "cwd": str(DOPPLER_ROOT),
        "cmd": [
            "node",
            "tools/run-program-bundle-reference.js",
            "--manifest", str(GEMMA_31B_MANIFEST),
            "--model-dir", str(GEMMA_31B_MODEL_DIR),
            "--conversion-config", str(GEMMA_31B_CONVERSION_CONFIG),
            "--runtime-config", json.dumps(
                GEMMA_31B_REFERENCE_RUNTIME_CONFIG,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "--surface", "node",
            "--prompt", "The color of the sky is",
            "--max-tokens", "8",
            "--report-out", str(reference_report),
            "--out", str(bundle_out),
        ],
        "timeoutSeconds": 21600,
        "expectSuccessReceiptPath": str(bundle_out),
    }

    a2_id = "csl-31b-L001-decode-truncated-size1024"
    a2_dir, _, _ = cell_paths(batch_dir, a2_id)
    a2_transcript = a2_dir / "transcript.json"
    a2_hostplan_root = a2_dir / "hostplan"
    a2 = {
        "id": a2_id,
        "lane": "webgpu_heavy",
        "cwd": str(REPO_ROOT),
        "dependsOn": [a1_id],
        "cmd": [
            "python3",
            str(REPO_ROOT / "bench" / "tools" / "run_doe_csl_int4ple_transcript.py"),
            "--program-bundle", str(bundle_out),
            "--max-layers", "1",
            "--hostplan-bundle-root", str(a2_hostplan_root),
            "--out", str(a2_transcript),
        ],
        "timeoutSeconds": 10800,
        "expectSuccessReceiptPath": str(a2_transcript),
        "expectJson": [{"path": "status", "equals": "output_ready"}],
    }
    return [a1, a2]


def lane_b_cells(batch_dir: Path, smoke_depths: list[int], smoke_size: int) -> list[dict]:
    """Lane B (csl_heavy, cap 2): 31B smoke ladder + 3 1B truncated
    prefill+decode."""
    cells: list[dict] = []
    for depth in sorted(smoke_depths):
        cell_id = f"csl-31b-L{depth:03d}-size{smoke_size}"
        cell_dir, trace, compile_dir = cell_paths(batch_dir, cell_id)
        cells.append({
            "id": cell_id,
            "lane": "csl_heavy",
            "cmd": [
                str(SDK_WRAPPER),
                str(REPO_ROOT / "bench" / "runners" / "csl-runners"
                    / "gemma_4_31b_layer_block_smoke.py"),
                "--num-layers", str(depth),
                "--size", str(smoke_size),
                "--compile-out", str(compile_dir),
                "--trace-out", str(trace),
            ],
            "timeoutSeconds": 5400,
            "expectSuccessReceiptPath": str(trace),
        })

    # 3 1B truncated prefill+decode at L1 — first kv_write/kv_read exercise
    # in any Doe receipt. Uses the existing 3 1B bundle (no Doppler export
    # dependency), so this is the smallest most-likely-to-pass piece of
    # actual prefill+decode evidence we can produce tonight.
    truncated_id = "csl-3-1b-L001-decode-truncated-size1024"
    truncated_dir, truncated_trace, _ = cell_paths(batch_dir, truncated_id)
    truncated_hostplan_root = truncated_dir / "hostplan"
    cells.append({
        "id": truncated_id,
        "lane": "csl_heavy",
        "cmd": [
            "python3",
            str(REPO_ROOT / "bench" / "tools" / "run_doe_csl_int4ple_transcript.py"),
            "--program-bundle", str(GEMMA_3_1B_BUNDLE),
            "--max-layers", "1",
            "--hostplan-bundle-root", str(truncated_hostplan_root),
            "--out", str(truncated_trace),
        ],
        "timeoutSeconds": 7200,
        "expectSuccessReceiptPath": str(truncated_trace),
        "expectJson": [{"path": "status", "equals": "output_ready"}],
    })
    return cells


def lane_c_cells(batch_dir: Path) -> list[dict]:
    """Lane C (light, cap 8): preflight, gate runs, hash jobs."""
    runtime_receipt_refresh = (
        REPO_ROOT / "bench" / "tools" / "refresh_gemma4_31b_runtime_receipt.py"
    )
    preflight_id = "light-doe-csl-int4ple-hardware-preflight"
    preflight_dir, _, _ = cell_paths(batch_dir, preflight_id)
    preflight_out = preflight_dir / "preflight.json"
    cells = [
        {
            "id": preflight_id,
            "lane": "light",
            "cmd": [
                "python3",
                str(REPO_ROOT / "bench" / "tools"
                    / "prepare_doe_csl_int4ple_hardware_receipt.py"),
                "--out", str(preflight_out),
            ],
            "timeoutSeconds": 600,
            "expectSuccessReceiptPath": str(preflight_out),
        },
        {
            "id": "light-validate-e2b-receipt-links",
            "lane": "light",
            "cmd": ["python3",
                    str(REPO_ROOT / "bench" / "tools" / "validate_e2b_receipt_links.py")],
            "timeoutSeconds": 600,
        },
        {
            "id": "light-claim-discipline-gate",
            "lane": "light",
            "cmd": ["python3",
                    str(REPO_ROOT / "bench" / "gates" / "claim_discipline_gate.py")],
            "timeoutSeconds": 1800,
        },
    ]
    if runtime_receipt_refresh.is_file():
        cells.append({
            "id": "light-31b-runtime-receipt-refresh",
            "lane": "light",
            "cmd": ["python3", str(runtime_receipt_refresh)],
            "timeoutSeconds": 900,
        })
    return cells


def main() -> int:
    args = parse_args()
    batch_dir_str = args.batch_dir or str(REPO_ROOT / "bench" / "out" / "overnight" / now_utc_compact())
    batch_dir = Path(batch_dir_str).resolve()

    smoke_depths = sorted({int(s.strip()) for s in args.smoke_depths.split(",") if s.strip()})

    cells: list[dict] = []
    if args.include_lane_a:
        cells.extend(lane_a_cells(batch_dir))
    cells.extend(lane_b_cells(batch_dir, smoke_depths, args.smoke_size))
    cells.extend(lane_c_cells(batch_dir))

    matrix = {"cells": cells}
    out_path = Path(args.out) if args.out else (batch_dir / "matrix.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"  batch_dir = {batch_dir}")
    print(f"  cells: {len(cells)} "
          f"(A={len([c for c in cells if c['lane']=='webgpu_heavy'])}, "
          f"B={len([c for c in cells if c['lane']=='csl_heavy'])}, "
          f"C={len([c for c in cells if c['lane']=='light'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
