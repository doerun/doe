"""Lock-in tests for the Q4_K_M passthrough SUMMA tile transform (Wedge 6 of
the fused-dequant SUMMA plan).

Pinned contract:

  - 256-aligned K (block boundary alignment) is required at three layers
    (sourceCols, paddedReduction, tileReduction). Misalignment must raise.
  - Per-row byte stride is ``(K / 256) * 144``.
  - Identity passthrough is byte-exact: with grid=1x1 and tile=full, the
    output equals the input.
  - Gemma 4 31B SUMMA shape (Kt = 2560 = 10 * 256) yields the expected
    aggregate byte count.
  - ``_summa_b_tiles_from_q4k_bytes`` is a uint8 transform: dtype must be
    preserved (no silent f32 widening anywhere in the pipeline).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / "bench" / "runners" / "csl-runners"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from int4ple_summa_layout import (  # noqa: E402
    QK_K_BLOCK_BYTES,
    QK_K_BLOCK_ELEMENTS,
    b_tiles_from_q4k_bytes,
)


def _minimal_transform(
    *,
    source_rows: int,
    source_cols: int,
    grid_height: int,
    grid_width: int,
    tile_cols: int,
    tile_reduction: int,
) -> dict:
    return {
        "sourceRows": source_rows,
        "sourceCols": source_cols,
        "paddedCols": grid_height * tile_cols,
        "paddedReduction": grid_width * tile_reduction,
        "gridHeight": grid_height,
        "gridWidth": grid_width,
        "tileCols": tile_cols,
        "tileReduction": tile_reduction,
    }


class Q4kPassthroughTests(unittest.TestCase):
    def test_canonical_block_constants(self) -> None:
        self.assertEqual(QK_K_BLOCK_ELEMENTS, 256)
        self.assertEqual(QK_K_BLOCK_BYTES, 144)

    def test_identity_single_pe_single_block(self) -> None:
        transform = _minimal_transform(
            source_rows=1,
            source_cols=256,
            grid_height=1,
            grid_width=1,
            tile_cols=1,
            tile_reduction=256,
        )
        src = np.arange(QK_K_BLOCK_BYTES, dtype=np.uint8)
        out = b_tiles_from_q4k_bytes(src, transform)
        self.assertEqual(out.dtype, np.uint8)
        self.assertEqual(out.size, QK_K_BLOCK_BYTES)
        self.assertTrue(np.array_equal(out, src))

    def test_gemma_4_31b_shape_byte_count(self) -> None:
        # Gemma 4 31B SUMMA tile contract: Kt = 2560 = 10 * 256, 16x16 grid.
        kt = 2560
        transform = _minimal_transform(
            source_rows=16,
            source_cols=kt,
            grid_height=16,
            grid_width=1,
            tile_cols=1,
            tile_reduction=kt,
        )
        bytes_per_row = (kt // QK_K_BLOCK_ELEMENTS) * QK_K_BLOCK_BYTES
        src = np.zeros(16 * bytes_per_row, dtype=np.uint8)
        out = b_tiles_from_q4k_bytes(src, transform)
        self.assertEqual(out.size, 16 * bytes_per_row)
        self.assertEqual(out.dtype, np.uint8)

    def test_unaligned_source_cols_rejected(self) -> None:
        transform = _minimal_transform(
            source_rows=1,
            source_cols=200,  # not 256-aligned
            grid_height=1,
            grid_width=1,
            tile_cols=1,
            tile_reduction=256,
        )
        with self.assertRaises(ValueError) as ctx:
            b_tiles_from_q4k_bytes(np.zeros(144, dtype=np.uint8), transform)
        self.assertIn("source_cols_unaligned", str(ctx.exception))

    def test_unaligned_tile_cols_rejected(self) -> None:
        # paddedReduction = 2 * 128 = 256 (aligned), but tile_reduction = 128
        # is not — so a Q4K block would straddle two PEs along K. The
        # tile-level guard must catch this even when the global padded
        # reduction looks fine.
        transform = _minimal_transform(
            source_rows=1,
            source_cols=256,
            grid_height=1,
            grid_width=2,
            tile_cols=1,
            tile_reduction=128,
        )
        with self.assertRaises(ValueError) as ctx:
            b_tiles_from_q4k_bytes(np.zeros(144, dtype=np.uint8), transform)
        self.assertIn("tile_cols_unaligned", str(ctx.exception))

    def test_input_size_mismatch_rejected(self) -> None:
        transform = _minimal_transform(
            source_rows=2,
            source_cols=256,
            grid_height=2,
            grid_width=1,
            tile_cols=1,
            tile_reduction=256,
        )
        # Expected 2 * 144 = 288 bytes, supply 100.
        with self.assertRaises(ValueError) as ctx:
            b_tiles_from_q4k_bytes(np.zeros(100, dtype=np.uint8), transform)
        self.assertIn("q4k_input_size_mismatch", str(ctx.exception))

    def test_output_dtype_is_uint8(self) -> None:
        # The wedge's whole point: bytes ship to fabric, no host f32
        # widening. If any future refactor changes the return dtype, this
        # fires.
        transform = _minimal_transform(
            source_rows=1,
            source_cols=256,
            grid_height=1,
            grid_width=1,
            tile_cols=1,
            tile_reduction=256,
        )
        src = np.arange(QK_K_BLOCK_BYTES, dtype=np.uint8)
        out = b_tiles_from_q4k_bytes(src, transform)
        self.assertEqual(out.dtype, np.uint8)
        self.assertEqual(out.itemsize, 1)


if __name__ == "__main__":
    unittest.main()
