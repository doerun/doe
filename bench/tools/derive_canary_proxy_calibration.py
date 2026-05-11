"""Derive a per-kernel manifest-shape-class throughput calibration from canary sim_stats.

Mitigates the per-kernel manifest-shape calibration gap in
``docs/cerebras-model-ledgers.md`` (Manifest-shape simfabric proof plan):
the predicted-wallclock wallclock predictor needs a ``bytesPerCycle`` calibration
constant, and the full-graph-dispatch launch gate denies until
``config/manifest-simfabric-budget.json``'s ``calibrationStatus``
flips off ``<bootstrap-pending-rung-3>``.

The intended source is a real per-kernel manifest-shape per-kernel manifest-shape
dispatch, but cs_python simfabric simulation at the manifest WSE-3
fabric (246x236, ~58k PEs) does not finish in tractable wall time on
local hosts. Until hardware execution lands (R3-1 / R3-3), this tool
derives a *canary-proxy* calibration from the per-kernel
``bench/out/csl-real-canary-compile/<kernel>/scratch/sim_stats.json``
files that the bootstrap canary already produces. Those receipts run
at 8x3 fabric, ~14 simulated tiles, and finish in <1s wall.

Output: ``bench/out/r3-1-31b-manifest-simfabric-canary-proxy-calibration/receipt.json``
with ``artifactKind=doe_simfabric_throughput_calibration`` and
``calibrationSource=canary_proxy``. Downstream consumers cite this
receipt's sha256 in ``config/manifest-simfabric-budget.json``'s
``calibrationStatus`` field. The budget schema's sha256 form already
accepts this; no schema change is needed.

Usage::

    python3 bench/tools/derive_canary_proxy_calibration.py \
        --canary-compile-root bench/out/csl-real-canary-compile \
        --out-dir bench/out/r3-1-31b-manifest-simfabric-canary-proxy-calibration

The receipt records per-canary-kernel cycle/byte data, the derived
``perPatternCyclesPerCall`` map keyed by host-plan pattern names, and
the median ``bytesPerCycle`` for unknown patterns. The ``notWhat``
block names exactly what this is not (manifest-shape evidence) so
reviewers cannot mistake it for a real per-kernel manifest-shape receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# Canary kernel inventory: pattern (matching host-plan kernel.pattern
# in bench/out/.../host-plan.json) and output bytes per call at canary
# shape. Output bytes are computed from bench/out/csl-real-canary-source/
# layouts (single-PE; output sizes pinned in the layout.csl
# `@export_name(..., [*]f32, true)` declarations and probe transcripts).
CANARY_INVENTORY: dict[str, dict[str, Any]] = {
    "embed": {
        "pattern": "gather",
        "output_bytes": 256 * 4,
    },
    "rms_norm": {
        "pattern": "rms_norm",
        "output_bytes": 4 * 4,
    },
    "fused_gemv": {
        "pattern": "fused_gemv",
        "output_bytes": 4 * 4,
    },
    "lm_head_gemv": {
        "pattern": "lm_head_gemv",
        "output_bytes": 4 * 4,
    },
    "gather": {
        "pattern": "gather",
        "output_bytes": 4 * 4,
    },
    "attention_head256_f16kv": {
        "pattern": "attention_decode",
        "output_bytes": 256 * 4,
    },
    "attention_head512_f16kv": {
        "pattern": "attention_decode",
        "output_bytes": 512 * 4,
    },
}

# Auxiliary calibration sources from the bounded multi-token decode
# orchestrator (`bench/out/r3-1-31b-multi-token-decode/scratch-subprocess/`).
# These cover host-plan patterns (`kv_write`, `sample`) that the canary
# inventory above doesn't reach. Bounded shape: width=4, head_dim=32,
# kv_len=64, vocab_chunk=1024 — runs on an 11x3 fabric with ~17
# simulated tiles. Output bytes per call are derived from
# multi_token_decode_orchestrator's per-step contract:
#   - kv_write: writes one [head_dim] f32 row into K and V cache
#     (max_seq_len=64 rows, but per-call writes one row at the
#     current target_position) -> 32 * 4 = 128 bytes per buffer
#     per call; the full kernel writes both K and V -> 256 bytes
#   - attention_decode: writes [head_dim] f32 -> 32 * 4 = 128
#   - sample: writes one i32 token id (PE-winner argmax over
#     vocab_chunk) -> 4 bytes
EXTRA_DECODE_INVENTORY: dict[str, dict[str, Any]] = {
    "kv_write": {
        "pattern": "kv_write",
        "output_bytes": 32 * 4 * 2,
        "scratch_subdir": "scratch_kv_write",
    },
    "sample": {
        "pattern": "sample",
        "output_bytes": 4,
        "scratch_subdir": "scratch_sample",
    },
}


def _try_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_canonical(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sample_from_stats(
    *,
    kernel: str,
    pattern: str,
    sim_stats_path: Path,
    output_bytes: int,
    sample_source: str,
) -> dict[str, Any] | None:
    if not sim_stats_path.is_file():
        return None
    stats = json.loads(sim_stats_path.read_text(encoding="utf-8"))
    cycle_count = int(stats.get("cycle_count") or 0)
    if cycle_count <= 0:
        return None
    return {
        "kernel": kernel,
        "pattern": pattern,
        "sampleSource": sample_source,
        "simStatsPath": _try_relative(sim_stats_path),
        "simStatsSha256": _sha256_file(sim_stats_path),
        "cycleCount": cycle_count,
        "totalTimeSec": float(stats.get("total_time") or 0.0),
        "outputBytes": output_bytes,
        "bytesPerCycle": output_bytes / cycle_count,
        "fabricX": int(stats.get("fabric_x") or 0),
        "fabricY": int(stats.get("fabric_y") or 0),
        "simulatedTileCount": int(stats.get("simulated_tile_count") or 0),
    }


def collect_samples(
    canary_compile_root: Path,
    multi_token_decode_root: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Walk calibration roots and build per-kernel sample records.

    Pulls from two sources:
    1. The bootstrap canary compile root (`bench/out/csl-real-canary-compile/`),
       one sim_stats.json per kernel under `<kernel>/scratch/sim_stats.json`.
    2. Optional bounded multi-token decode scratch
       (`bench/out/r3-1-31b-multi-token-decode/scratch-subprocess/step*/`)
       which carries `kv_write` / `sample` patterns the canary inventory
       does not cover.

    Returns (samples, missing): one sample dict per kernel that has
    sim_stats on disk, plus the list of kernels we expected but did
    not find.
    """
    samples: list[dict[str, Any]] = []
    missing: list[str] = []
    for kernel, meta in CANARY_INVENTORY.items():
        sim_stats_path = canary_compile_root / kernel / "scratch" / "sim_stats.json"
        sample = _sample_from_stats(
            kernel=kernel,
            pattern=meta["pattern"],
            sim_stats_path=sim_stats_path,
            output_bytes=int(meta["output_bytes"]),
            sample_source="canary_compile",
        )
        if sample is None:
            missing.append(kernel)
            continue
        samples.append(sample)

    if multi_token_decode_root is not None:
        # Walk every step* dir; pick whichever step has a sim_stats.json
        # (typically step000 or step001). The orchestrator writes one
        # sim_stats.json per (step, kernel) pair.
        step_dirs = sorted(
            (multi_token_decode_root / "scratch-subprocess").glob("step*")
        ) if (multi_token_decode_root / "scratch-subprocess").is_dir() else []
        for kernel, meta in EXTRA_DECODE_INVENTORY.items():
            sample: dict[str, Any] | None = None
            for step_dir in step_dirs:
                sim_stats_path = step_dir / meta["scratch_subdir"] / "sim_stats.json"
                sample = _sample_from_stats(
                    kernel=kernel,
                    pattern=meta["pattern"],
                    sim_stats_path=sim_stats_path,
                    output_bytes=int(meta["output_bytes"]),
                    sample_source=f"bounded_multi_token_decode/{step_dir.name}",
                )
                if sample is not None:
                    break
            if sample is None:
                missing.append(f"{kernel} (no multi-token decode step had sim_stats)")
                continue
            samples.append(sample)

    return samples, missing


def derive_constants(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the derived calibration constants.

    ``bytesPerCycle`` is the median across canary samples (used by the
    predicted-wallclock predictor as the fallback for any pattern without a
    per-pattern override).

    ``perPatternCyclesPerCall`` is keyed by host-plan pattern name;
    when multiple canary kernels share a pattern (e.g. attention_decode
    has both head256 and head512), the larger cycle count wins so the
    predicted budget is conservative.
    """
    if not samples:
        raise ValueError("no canary samples available")
    bytes_per_cycle_values = [s["bytesPerCycle"] for s in samples]
    median_bpc = statistics.median(bytes_per_cycle_values)

    per_pattern: dict[str, int] = {}
    for s in samples:
        pattern = s["pattern"]
        cycles = int(s["cycleCount"])
        prior = per_pattern.get(pattern)
        if prior is None or cycles > prior:
            per_pattern[pattern] = cycles
    return {
        "bytesPerCycle": median_bpc,
        "perPatternCyclesPerCall": per_pattern,
    }


def build_receipt(
    canary_compile_root: Path,
    samples: list[dict[str, Any]],
    missing: list[str],
    constants: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_simfabric_throughput_calibration",
        "receiptClass": "manifest_shape_per_kernel_dispatch_proxy",
        "comparisonMode": "no_oracle",
        "calibrationSource": "canary_proxy",
        "calibrationSourceRoot": _try_relative(canary_compile_root),
        "frozenAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "samples": samples,
        "missingCanaryKernels": missing,
        "derivedConstants": constants,
        "claim": {
            "scope": (
                "Per-pattern cycles-per-call calibration for the "
                "predicted-wallclock simfabric wall-clock predictor. Constants are "
                "derived from the bootstrap canary lane's per-kernel "
                "sim_stats.json files (8x3 fabric, ~14 simulated "
                "tiles); the receipt's sha256 is intended to be "
                "cited in config/manifest-simfabric-budget.json's "
                "calibrationStatus field, replacing the "
                "<bootstrap-pending-rung-3> sentinel."
            ),
            "notWhat": (
                "NOT a manifest-shape per-kernel manifest-shape dispatch receipt. The "
                "manifest-shape simfabric (246x236 fabric, ~58k PEs) "
                "cannot be exercised in tractable wall-clock on the "
                "local host where this calibration was produced; "
                "individual kernel dispatches at manifest shape do "
                "not finish inside the chain_step_adapter timeout. "
                "Use this calibration as a bootstrap input until a "
                "real manifest-shape per-kernel manifest-shape dispatch lands (R3-1 / "
                "R3-3 hardware path) and supersedes it."
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--canary-compile-root",
        type=Path,
        default=REPO_ROOT / "bench" / "out" / "csl-real-canary-compile",
    )
    p.add_argument(
        "--multi-token-decode-root",
        type=Path,
        default=REPO_ROOT / "bench" / "out" / "r3-1-31b-multi-token-decode",
        help=(
            "Optional path to the bounded multi-token decode "
            "scratch root. When present, the tool also pulls "
            "kv_write/sample sim_stats from "
            "<root>/scratch-subprocess/step*/scratch_<kernel>/sim_stats.json "
            "to extend per-pattern coverage beyond the canary "
            "inventory. Pass an absent path or use a directory that "
            "doesn't contain scratch-subprocess/ to skip."
        ),
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=(
            REPO_ROOT
            / "bench"
            / "out"
            / "r3-1-31b-manifest-simfabric-canary-proxy-calibration"
        ),
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    canary_compile_root: Path = args.canary_compile_root
    out_dir: Path = args.out_dir

    if not canary_compile_root.is_dir():
        sys.stderr.write(
            f"derive_canary_proxy_calibration: canary compile root "
            f"{canary_compile_root} is not a directory\n"
        )
        return 2

    multi_token_decode_root: Path | None = args.multi_token_decode_root
    if multi_token_decode_root is not None and not (
        multi_token_decode_root / "scratch-subprocess"
    ).is_dir():
        multi_token_decode_root = None

    samples, missing = collect_samples(
        canary_compile_root,
        multi_token_decode_root=multi_token_decode_root,
    )
    if not samples:
        sys.stderr.write(
            "derive_canary_proxy_calibration: no canary sim_stats.json "
            "files found under "
            f"{_try_relative(canary_compile_root)} -- "
            f"missing={missing!r}\n"
        )
        return 2

    constants = derive_constants(samples)
    receipt = build_receipt(canary_compile_root, samples, missing, constants)
    receipt_sha = _sha256_canonical(receipt)
    receipt["selfDigest"] = receipt_sha

    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = out_dir / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt_file_sha = _sha256_file(receipt_path)

    throughput_path = out_dir / "throughput-config.json"
    throughput_path.write_text(
        json.dumps(constants, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "receiptPath": _try_relative(receipt_path),
                "throughputConfigPath": _try_relative(throughput_path),
                "receiptCanonicalSha256": receipt_sha,
                "receiptFileSha256": receipt_file_sha,
                "samples": len(samples),
                "missing": missing,
                "constants": constants,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
