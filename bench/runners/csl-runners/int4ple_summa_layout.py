"""SUMMA host-side tile layouts for the INT4 PLE CSL HostPlan runner.

Pure NumPy transforms that convert logical activation/weight matrices into
the per-PE SUMMA tile order expected by the generated CSL kernels and back
again. No file I/O lives here; weight bytes are read by the runner and
passed in as already-materialized matrices.

These helpers were extracted from
``bench/runners/csl-runners/int4ple_compile_target_sim_runner.py`` per the
sharding follow-up tracked in ``docs/status/cerebras-csl.md`` (late+16).
"""

from __future__ import annotations

from typing import Any

import numpy as np


def required_positive_int(mapping: dict[str, Any], key: str) -> int:
    """Return ``mapping[key]`` as a positive int, raising on absence or zero."""
    try:
        value = int(mapping.get(key) or 0)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        raise ValueError(f"transform_field_missing:{key}")
    return value


def a_tiles_from_logical(
    host: np.ndarray,
    transform: dict[str, Any],
) -> tuple[np.ndarray, int]:
    """Tile a logical row-major matrix into SUMMA A-side per-PE order.

    Returns the flat tile buffer and the original logical row count so the
    caller can carry forward the unpadded shape for downstream detiling.
    """
    source_cols = required_positive_int(transform, "sourceCols")
    padded_rows = required_positive_int(transform, "paddedRows")
    padded_cols = required_positive_int(transform, "paddedReduction")
    grid_height = required_positive_int(transform, "gridHeight")
    grid_width = required_positive_int(transform, "gridWidth")
    tile_rows = required_positive_int(transform, "tileRows")
    tile_cols = required_positive_int(transform, "tileReduction")
    if host.size % source_cols != 0:
        raise ValueError(
            f"summa_a_logical_size_mismatch:{host.size}%{source_cols}"
        )
    rows = host.size // source_cols
    if rows > padded_rows or source_cols > padded_cols:
        raise ValueError(
            "summa_a_logical_shape_exceeds_target:"
            f"{rows}x{source_cols}>{padded_rows}x{padded_cols}"
        )
    padded = np.zeros((padded_rows, padded_cols), dtype=np.float32)
    padded[:rows, :source_cols] = host.astype(np.float32, copy=False).reshape(
        rows, source_cols
    )
    tiles = padded.reshape(
        grid_height,
        tile_rows,
        grid_width,
        tile_cols,
    ).transpose(0, 2, 3, 1)
    return tiles.reshape(-1).astype(np.float32, copy=False), rows


QK_K_BLOCK_ELEMENTS = 256
QK_K_BLOCK_BYTES = 144


def b_tiles_from_q4k_bytes(
    matrix_nk_bytes: np.ndarray,
    transform: dict[str, Any],
) -> np.ndarray:
    """Tile a logical [N, K_bytes] Q4_K_M weight byte stream into SUMMA B-side
    per-PE order without dequantizing on the host.

    Per-row stride is ``(K / QK_K_BLOCK_ELEMENTS) * QK_K_BLOCK_BYTES`` bytes.
    The K-axis tile width must be a multiple of ``QK_K_BLOCK_ELEMENTS`` (256)
    so Q4K block boundaries align with SUMMA tile boundaries; otherwise a
    block would straddle two PEs and require cross-PE reassembly.

    The output is a flat ``uint8`` array carrying the byte order
    ``[grid_height, grid_width, tile_rows, tile_byte_stride]`` where
    ``tile_byte_stride = (tile_cols / 256) * 144``.
    """
    source_rows = required_positive_int(transform, "sourceRows")
    source_cols = required_positive_int(transform, "sourceCols")
    padded_rows = required_positive_int(transform, "paddedCols")
    padded_cols = required_positive_int(transform, "paddedReduction")
    grid_height = required_positive_int(transform, "gridHeight")
    grid_width = required_positive_int(transform, "gridWidth")
    tile_rows = required_positive_int(transform, "tileCols")
    tile_cols = required_positive_int(transform, "tileReduction")
    if source_cols % QK_K_BLOCK_ELEMENTS != 0:
        raise ValueError(
            "summa_b_q4k_source_cols_unaligned:"
            f"{source_cols}%{QK_K_BLOCK_ELEMENTS}"
        )
    if padded_cols % QK_K_BLOCK_ELEMENTS != 0:
        raise ValueError(
            "summa_b_q4k_padded_cols_unaligned:"
            f"{padded_cols}%{QK_K_BLOCK_ELEMENTS}"
        )
    if tile_cols % QK_K_BLOCK_ELEMENTS != 0:
        raise ValueError(
            "summa_b_q4k_tile_cols_unaligned:"
            f"{tile_cols}%{QK_K_BLOCK_ELEMENTS}"
        )
    source_bytes_per_row = (source_cols // QK_K_BLOCK_ELEMENTS) * QK_K_BLOCK_BYTES
    padded_bytes_per_row = (padded_cols // QK_K_BLOCK_ELEMENTS) * QK_K_BLOCK_BYTES
    tile_bytes_per_row = (tile_cols // QK_K_BLOCK_ELEMENTS) * QK_K_BLOCK_BYTES
    expected_input_bytes = source_rows * source_bytes_per_row
    if matrix_nk_bytes.size != expected_input_bytes:
        raise ValueError(
            "summa_b_q4k_input_size_mismatch:"
            f"{matrix_nk_bytes.size}!={expected_input_bytes}"
        )
    if source_rows > padded_rows:
        raise ValueError(
            "summa_b_q4k_source_rows_exceed_padded:"
            f"{source_rows}>{padded_rows}"
        )
    flat = matrix_nk_bytes.astype(np.uint8, copy=False).reshape(
        source_rows, source_bytes_per_row
    )
    padded = np.zeros((padded_rows, padded_bytes_per_row), dtype=np.uint8)
    padded[:source_rows, :source_bytes_per_row] = flat
    tiles = padded.reshape(
        grid_width,
        tile_rows,
        grid_height,
        tile_bytes_per_row,
    ).transpose(2, 0, 1, 3)
    return tiles.reshape(-1).astype(np.uint8, copy=False)


def b_tiles_from_weight_matrix(
    matrix_nk: np.ndarray,
    transform: dict[str, Any],
) -> np.ndarray:
    """Tile a logical [N, K] weight matrix into SUMMA B-side per-PE order."""
    source_rows = required_positive_int(transform, "sourceRows")
    source_cols = required_positive_int(transform, "sourceCols")
    padded_rows = required_positive_int(transform, "paddedCols")
    padded_cols = required_positive_int(transform, "paddedReduction")
    grid_height = required_positive_int(transform, "gridHeight")
    grid_width = required_positive_int(transform, "gridWidth")
    tile_rows = required_positive_int(transform, "tileCols")
    tile_cols = required_positive_int(transform, "tileReduction")
    if matrix_nk.size != source_rows * source_cols:
        raise ValueError(
            "summa_b_weight_shape_mismatch:"
            f"{matrix_nk.size}!={source_rows}x{source_cols}"
        )
    if source_rows > padded_rows or source_cols > padded_cols:
        raise ValueError(
            "summa_b_logical_shape_exceeds_target:"
            f"{source_rows}x{source_cols}>{padded_rows}x{padded_cols}"
        )
    padded = np.zeros((padded_rows, padded_cols), dtype=np.float32)
    padded[:source_rows, :source_cols] = matrix_nk.astype(
        np.float32,
        copy=False,
    ).reshape(source_rows, source_cols)
    tiles = padded.reshape(
        grid_width,
        tile_rows,
        grid_height,
        tile_cols,
    ).transpose(2, 0, 1, 3)
    return tiles.reshape(-1).astype(np.float32, copy=False)
