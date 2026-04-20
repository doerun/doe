#!/usr/bin/env python3
"""Materialize numpy-PRNG input fixtures so the Node+WebGPU reference
export can consume the same bytes the CSL runner uses.

The CSL runner generates per-layer inputs via numpy's default_rng(seed).
standard_normal(size, f32). Reproducing that exact PRNG stream in
JavaScript is not feasible (numpy uses PCG64; JS has no matching
implementation). Instead, this tool writes the numpy PRNG output to
side-channel fixture files that the Node+WebGPU export reads.

Files emitted (one per seed):

  bench/out/doppler-reference/inputs/input_seed<S>_size<N>.f32

Usage:

  python3 bench/tools/doppler_prepare_webgpu_inputs.py \\
    --size 1024 \\
    --seeds 1000 2000 2001 ... 2034

The runner's seed convention:
  initial_rows_seed = 1000
  per_layer_seed    = 2000 + layer_idx  (for E2B: 2000..2034)
Both proj_l and wts_l use default_rng(per_layer_seed) separately, so
proj_l == wts_l bit-exactly. One fixture file per distinct seed is
sufficient.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "bench" / "out" / "doppler-reference" / "inputs"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--size", type=int, default=1024)
    p.add_argument(
        "--seeds", type=int, nargs="+", required=True,
        help="One or more integer seeds to materialize. "
             "For E2B single-layer: 1000 (initial rows) + 2000 "
             "(per-layer 0). For full E2B chain: 1000 + 2000..2034.",
    )
    p.add_argument(
        "--out-dir", default=str(DEFAULT_OUT_DIR),
        help="Output directory; defaults to bench/out/doppler-reference/inputs/",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for seed in args.seeds:
        arr = np.random.default_rng(
            seed=seed
        ).standard_normal(size=args.size, dtype=np.float32)
        fname = f"input_seed{seed}_size{args.size}.f32"
        fpath = out_dir / fname
        arr.astype(np.float32).tofile(fpath)
        try:
            rel = str(fpath.relative_to(REPO_ROOT))
        except ValueError:
            rel = str(fpath)
        written.append(rel)

    print(
        f"materialized {len(written)} input fixture(s) at {out_dir.name}/"
    )
    for w in written:
        print(f"  {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
