#!/usr/bin/env cs_python
"""Execute one INT4 PLE HostPlan launch in a fresh SDK process."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

os.environ.setdefault("CSL_SUPPRESS_SIMFAB_TRACE", "1")

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    MemcpyDataType,
    MemcpyOrder,
    SdkRuntime,
)


DTYPE_MAP = {
    "f32": (np.float32, MemcpyDataType.MEMCPY_32BIT),
    "u32": (np.uint32, MemcpyDataType.MEMCPY_32BIT),
    "f16": (np.float16, MemcpyDataType.MEMCPY_32BIT),
    "u16": (np.uint16, MemcpyDataType.MEMCPY_16BIT),
}
F16_D2H_CHUNK_WORDS = 128
ATTENTION_D2H_REGION_PE_WIDTH = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--receipt-out", required=True)
    parser.add_argument("--progress-out", default="")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def array_sha256(path: Path) -> str:
    array = np.load(path, allow_pickle=False).ravel()
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def append_progress(path: Path | None, phase: str, **fields: Any) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestampUnix": time.time(),
        "phase": phase,
        **fields,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _dtype_config(dtype: str) -> tuple[Any, Any]:
    if dtype not in DTYPE_MAP:
        raise ValueError(f"unsupported adapter dtype {dtype!r}")
    return DTYPE_MAP[dtype]


def _load_array(path: Path, dtype: str, expected_size: int) -> np.ndarray:
    np_dtype, _ = _dtype_config(dtype)
    array = np.load(path, allow_pickle=False).astype(np_dtype, copy=False).ravel()
    if array.size != expected_size:
        raise ValueError(
            f"array size mismatch for {path}: {array.size} != expected {expected_size}"
        )
    return array


def _load_writeable_mmap_or_copy(path: Path) -> np.ndarray:
    try:
        return np.load(path, allow_pickle=False, mmap_mode="r+").ravel()
    except (OSError, ValueError):
        return np.load(path, allow_pickle=False, mmap_mode="r").ravel()


def _writeable_contiguous_array(host: np.ndarray, dtype: np.dtype) -> np.ndarray:
    if host.dtype == dtype and host.flags.c_contiguous and host.flags.writeable:
        return host
    return np.array(host, dtype=dtype, copy=True, order="C")


def _memcpy_payload_for_h2d(
    *,
    path: Path,
    dtype: str,
    elements_per_pe: int,
    total_elements: int,
) -> tuple[np.ndarray, Any, int]:
    if dtype == "f16":
        if elements_per_pe % 2 != 0:
            raise ValueError(
                f"f16 elementsPerPe {elements_per_pe} must be even for "
                "MEMCPY_32BIT byte-preserving transfer"
            )
        host = _load_writeable_mmap_or_copy(path)
        if host.size != total_elements:
            raise ValueError(
                f"array size mismatch for {path}: {host.size} != expected {total_elements}"
            )
        host = _writeable_contiguous_array(host, np.dtype(np.float16))
        return (
            host.view(np.uint32),
            MemcpyDataType.MEMCPY_32BIT,
            elements_per_pe // 2,
        )
    host = _load_array(path, dtype, total_elements)
    _, memcpy_dtype = _dtype_config(dtype)
    return host, memcpy_dtype, elements_per_pe


def _memcpy_buffer_for_d2h(
    *,
    dtype: str,
    elements_per_pe: int,
    total_elements: int,
) -> tuple[np.ndarray, Any, int, np.dtype]:
    if dtype == "f16":
        if elements_per_pe % 2 != 0:
            raise ValueError(
                f"f16 elementsPerPe {elements_per_pe} must be even for "
                "MEMCPY_32BIT byte-preserving transfer"
            )
        return (
            np.zeros(total_elements // 2, dtype=np.uint32),
            MemcpyDataType.MEMCPY_32BIT,
            elements_per_pe // 2,
            np.dtype(np.float16),
        )
    np_dtype, memcpy_dtype = _dtype_config(dtype)
    return (
        np.zeros(total_elements, dtype=np_dtype),
        memcpy_dtype,
        elements_per_pe,
        np.dtype(np_dtype),
    )


def _required_positive_int(mapping: dict[str, Any], key: str) -> int:
    try:
        value = int(mapping.get(key) or 0)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        raise ValueError(f"transform_field_missing:{key}")
    return value


def _attention_query_output_required_pe_rows(
    output_transform: dict[str, Any],
) -> int:
    rows = _required_positive_int(output_transform, "rows")
    cols = _required_positive_int(output_transform, "cols")
    head_dim = _required_positive_int(output_transform, "headDim")
    target_rows = _required_positive_int(output_transform, "targetRows")
    rows_per_pe = _required_positive_int(output_transform, "rowsPerPe")
    if cols % head_dim != 0:
        raise ValueError(f"attention_output_cols_mismatch:{cols}%{head_dim}")
    head_rows = rows * (cols // head_dim)
    required_pe_rows = (head_rows + rows_per_pe - 1) // rows_per_pe
    if required_pe_rows > target_rows:
        raise ValueError(
            "attention_output_rows_exceed_target:"
            f"{head_rows}>{target_rows * rows_per_pe}"
        )
    return required_pe_rows


def _summa_c_tiles_to_logical(
    host: np.ndarray,
    transform: dict[str, Any],
    *,
    region: dict[str, int] | None = None,
) -> np.ndarray:
    rows = _required_positive_int(transform, "rows")
    cols = _required_positive_int(transform, "cols")
    padded_rows = _required_positive_int(transform, "paddedRows")
    padded_cols = _required_positive_int(transform, "paddedCols")
    grid_height = _required_positive_int(transform, "gridHeight")
    grid_width = _required_positive_int(transform, "gridWidth")
    tile_rows = _required_positive_int(transform, "tileRows")
    tile_cols = _required_positive_int(transform, "tileCols")
    region = region or {
        "x": 0,
        "y": 0,
        "width": grid_width,
        "height": grid_height,
    }
    region_x = int(region.get("x") or 0)
    region_y = int(region.get("y") or 0)
    region_width = int(region.get("width") or 0)
    region_height = int(region.get("height") or 0)
    if region_width <= 0 or region_height <= 0:
        raise ValueError("summa_c_region_empty")
    if region_x < 0 or region_y < 0:
        raise ValueError("summa_c_region_negative")
    if region_x + region_width > grid_width or region_y + region_height > grid_height:
        raise ValueError("summa_c_region_exceeds_grid")
    if rows > padded_rows or cols > padded_cols:
        raise ValueError(
            "summa_c_logical_shape_exceeds_target:"
            f"{rows}x{cols}>{padded_rows}x{padded_cols}"
        )
    expected = region_height * region_width * tile_rows * tile_cols
    if host.size != expected:
        raise ValueError(f"summa_c_tile_size_mismatch:{host.size}!={expected}")
    region_logical = host.reshape(
        region_height,
        region_width,
        tile_cols,
        tile_rows,
    ).transpose(0, 3, 1, 2).reshape(
        region_height * tile_rows,
        region_width * tile_cols,
    )
    row_start = region_y * tile_rows
    col_start = region_x * tile_cols
    row_end = row_start + region_logical.shape[0]
    col_end = col_start + region_logical.shape[1]
    if rows > row_end or cols > col_end:
        raise ValueError(
            "summa_c_region_does_not_cover_logical_output:"
            f"{rows}x{cols}>{row_end}x{col_end}"
        )
    row_offset = max(0, -row_start)
    col_offset = max(0, -col_start)
    return region_logical[
        row_offset : row_offset + rows,
        col_offset : col_offset + cols,
    ].reshape(-1).astype(host.dtype, copy=False)


def _dense_gemv_row_shards_to_logits(
    host: np.ndarray,
    transform: dict[str, Any],
) -> np.ndarray:
    width = _required_positive_int(transform, "width")
    height = _required_positive_int(transform, "height")
    out_dim = _required_positive_int(transform, "outDim")
    out_dim_per_pe = _required_positive_int(transform, "outDimPerPe")
    compact_expected = height * out_dim_per_pe
    full_expected = width * compact_expected
    if host.size == compact_expected:
        logits = host.reshape(height, out_dim_per_pe).reshape(-1)
        return logits[:out_dim].astype(np.float32, copy=False)
    if host.size != full_expected:
        raise ValueError(
            "dense_gemv_output_size_mismatch:"
            f"{host.size}!={compact_expected}|{full_expected}"
        )
    root_x = width - 1
    logits = host.reshape(height, width, out_dim_per_pe)[:, root_x, :].reshape(-1)
    return logits[:out_dim].astype(np.float32, copy=False)


def _d2h_region_for_output(
    *,
    output_transform: dict[str, Any],
    width: int,
    height: int,
) -> dict[str, int]:
    transform_kind = str(output_transform.get("kind") or "")
    if transform_kind == "dense_gemv_row_shards_to_logits":
        return {
            "x": width - 1,
            "y": 0,
            "width": 1,
            "height": height,
        }
    if transform_kind == "summa_tiles_to_logical_matrix":
        rows = _required_positive_int(output_transform, "rows")
        cols = _required_positive_int(output_transform, "cols")
        tile_rows = _required_positive_int(output_transform, "tileRows")
        tile_cols = _required_positive_int(output_transform, "tileCols")
        region_width = min(width, max(1, (cols + tile_cols - 1) // tile_cols))
        region_height = min(height, max(1, (rows + tile_rows - 1) // tile_rows))
        return {
            "x": 0,
            "y": 0,
            "width": region_width,
            "height": region_height,
        }
    if transform_kind == "pe_rows_to_logical_matrix":
        rows = _required_positive_int(output_transform, "rows")
        return {
            "x": 0,
            "y": 0,
            "width": min(width, rows),
            "height": 1,
        }
    if transform_kind == "attention_query_rows_to_logical_matrix":
        required_pe_rows = _attention_query_output_required_pe_rows(output_transform)
        if required_pe_rows > width * height:
            raise ValueError(
                "attention_output_region_exceeds_grid:"
                f"{required_pe_rows}>{width * height}"
            )
        region_height = max(1, (required_pe_rows + width - 1) // width)
        region_width = width if region_height > 1 else required_pe_rows
        return {
            "x": 0,
            "y": 0,
            "width": region_width,
            "height": min(height, region_height),
        }
    return {
        "x": 0,
        "y": 0,
        "width": width,
        "height": height,
    }


def _d2h_regions_for_output(
    *,
    output_transform: dict[str, Any],
    width: int,
    height: int,
) -> list[dict[str, int]]:
    region = _d2h_region_for_output(
        output_transform=output_transform,
        width=width,
        height=height,
    )
    if (
        str(output_transform.get("kind") or "") == "summa_tiles_to_logical_matrix"
        and int(region["height"]) > 1
    ):
        return [
            {
                "x": int(region["x"]),
                "y": y,
                "width": int(region["width"]),
                "height": 1,
            }
            for y in range(int(region["y"]), int(region["y"]) + int(region["height"]))
        ]
    if (
        str(output_transform.get("kind") or "") == "pe_rows_to_logical_matrix"
        and int(region["width"]) > 1
    ):
        return [
            {
                "x": x,
                "y": int(region["y"]),
                "width": 1,
                "height": int(region["height"]),
            }
            for x in range(int(region["x"]), int(region["x"]) + int(region["width"]))
        ]
    if (
        str(output_transform.get("kind") or "")
        == "attention_query_rows_to_logical_matrix"
        and int(output_transform.get("rowsPerPe") or 0) > 1
        and int(region["width"]) > ATTENTION_D2H_REGION_PE_WIDTH
    ):
        regions: list[dict[str, int]] = []
        width_limit = int(region["x"]) + int(region["width"])
        for y in range(int(region["y"]), int(region["y"]) + int(region["height"])):
            x = int(region["x"])
            while x < width_limit:
                chunk_width = min(ATTENTION_D2H_REGION_PE_WIDTH, width_limit - x)
                regions.append({
                    "x": x,
                    "y": y,
                    "width": chunk_width,
                    "height": 1,
                })
                x += chunk_width
        return regions
    return [region]


def _chunked_f16_output_available(runner: Any, symbol: str) -> bool:
    try:
        symbol_id = runner.get_id(f"{symbol}_chunk_0000")
    except Exception:
        return False
    return symbol_id is not None


def _chunked_f16_memcpy_d2h(
    *,
    runner: Any,
    symbol: str,
    elements_per_pe: int,
    region: dict[str, int],
    progress_path: Path | None,
    launch_index: int,
) -> np.ndarray:
    if elements_per_pe % 2 != 0:
        raise ValueError(
            f"f16 elementsPerPe {elements_per_pe} must be even for chunked D2H"
        )
    words_per_pe = elements_per_pe // 2
    pe_hosts: list[np.ndarray] = []
    for pe_y in range(int(region["y"]), int(region["y"]) + int(region["height"])):
        for pe_x in range(int(region["x"]), int(region["x"]) + int(region["width"])):
            chunks: list[np.ndarray] = []
            for chunk_index, word_start in enumerate(
                range(0, words_per_pe, F16_D2H_CHUNK_WORDS)
            ):
                word_count = min(F16_D2H_CHUNK_WORDS, words_per_pe - word_start)
                chunk_symbol = f"{symbol}_chunk_{chunk_index:04d}"
                host_part = np.zeros(F16_D2H_CHUNK_WORDS, dtype=np.uint32)
                append_progress(
                    progress_path,
                    "launch_step_memcpy_d2h_chunk",
                    launchIndex=launch_index,
                    symbol=chunk_symbol,
                    peX=pe_x,
                    peY=pe_y,
                    words=word_count,
                )
                chunk_symbol_id = runner.get_id(chunk_symbol)
                if chunk_symbol_id is None:
                    raise ValueError(f"chunked_f16_symbol_unresolved:{chunk_symbol}")
                runner.memcpy_d2h(
                    host_part,
                    int(chunk_symbol_id),
                    pe_x,
                    pe_y,
                    1,
                    1,
                    F16_D2H_CHUNK_WORDS,
                    streaming=False,
                    order=MemcpyOrder.ROW_MAJOR,
                    data_type=MemcpyDataType.MEMCPY_32BIT,
                    nonblock=False,
                )
                chunks.append(host_part[:word_count])
            pe_hosts.append(np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.uint32))
    return np.concatenate(pe_hosts) if pe_hosts else np.zeros(0, dtype=np.uint32)


def _pe_rows_to_logical_matrix(
    host: np.ndarray,
    output_transform: dict[str, Any],
) -> np.ndarray:
    rows = _required_positive_int(output_transform, "rows")
    cols = _required_positive_int(output_transform, "cols")
    expected = rows * cols
    if host.size < expected:
        raise ValueError(f"pe_rows_output_size_mismatch:{host.size}<{expected}")
    return host[:expected].reshape(rows, cols).reshape(-1)


def _rope_pe_heads_to_logical_matrix(
    host: np.ndarray,
    output_transform: dict[str, Any],
) -> np.ndarray:
    rows = _required_positive_int(output_transform, "rows")
    cols = _required_positive_int(output_transform, "cols")
    head_dim = _required_positive_int(output_transform, "headDim")
    target_rows = _required_positive_int(output_transform, "targetRows")
    if cols % head_dim != 0:
        raise ValueError(f"rope_output_cols_mismatch:{cols}%{head_dim}")
    head_rows = rows * (cols // head_dim)
    expected = target_rows * head_dim
    if host.size < expected:
        raise ValueError(f"rope_output_size_mismatch:{host.size}<{expected}")
    if head_rows > target_rows:
        raise ValueError(f"rope_output_rows_exceed_target:{head_rows}>{target_rows}")
    heads = host[:expected].reshape(target_rows, head_dim)[:head_rows, :]
    return heads.reshape(rows, cols).reshape(-1)


def _attention_query_rows_to_logical_matrix(
    host: np.ndarray,
    output_transform: dict[str, Any],
) -> np.ndarray:
    rows = _required_positive_int(output_transform, "rows")
    cols = _required_positive_int(output_transform, "cols")
    head_dim = _required_positive_int(output_transform, "headDim")
    rows_per_pe = _required_positive_int(output_transform, "rowsPerPe")
    if cols % head_dim != 0:
        raise ValueError(f"attention_output_cols_mismatch:{cols}%{head_dim}")
    head_rows = rows * (cols // head_dim)
    required_pe_rows = _attention_query_output_required_pe_rows(output_transform)
    elements_per_pe = rows_per_pe * head_dim
    if host.size % elements_per_pe != 0:
        raise ValueError(
            "attention_output_size_not_pe_aligned:"
            f"{host.size}%{elements_per_pe}"
        )
    copied_pe_rows = host.size // elements_per_pe
    if copied_pe_rows < required_pe_rows:
        expected = required_pe_rows * elements_per_pe
        raise ValueError(f"attention_output_size_mismatch:{host.size}<{expected}")
    heads = host.reshape(copied_pe_rows * rows_per_pe, head_dim)[:head_rows, :]
    return heads.reshape(rows, cols).reshape(-1)


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec)
    receipt_path = Path(args.receipt_out)
    progress_path = Path(args.progress_out) if args.progress_out else None
    receipt_path.unlink(missing_ok=True)
    spec = load_json(spec_path)
    blockers: list[str] = []
    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "int4ple_launch_step_receipt",
        "status": "blocked",
        "compileDir": str(spec.get("compileDir") or ""),
        "launchFunction": str(spec.get("launchFunction") or "compute"),
        "postLaunchFunctions": [
            str(item)
            for item in spec.get("postLaunchFunctions") or []
            if str(item or "").strip()
        ],
        "launchIndex": int(spec.get("launchIndex") or 0),
        "blockers": blockers,
        "inputBuffers": [],
        "outputs": [],
    }

    compile_dir = Path(str(spec.get("compileDir") or ""))
    if not compile_dir.is_dir():
        blockers.append(f"compile_dir_missing:{compile_dir}")
        write_json(receipt_path, receipt)
        return 1

    grid = spec.get("targetGeometry") or {}
    width = int(grid.get("width") or 1)
    height = int(grid.get("height") or 1)
    cmaddr = str(spec.get("cmaddr") or "").strip() or None
    runner = None
    launch_index = int(spec.get("launchIndex") or 0)
    try:
        append_progress(progress_path, "launch_step_constructor", launchIndex=launch_index)
        print("phase:constructor", flush=True)
        runner = SdkRuntime(str(compile_dir), cmaddr=cmaddr)
        append_progress(progress_path, "launch_step_load", launchIndex=launch_index)
        print("phase:load", flush=True)
        runner.load()
        append_progress(progress_path, "launch_step_run", launchIndex=launch_index)
        print("phase:run", flush=True)
        runner.run()
        input_buffers: list[dict[str, Any]] = []
        for item in spec.get("inputs") or []:
            if not isinstance(item, dict):
                blockers.append("input_spec_not_object")
                continue
            symbol = str(item.get("symbol") or "")
            dtype = str(item.get("dtype") or "")
            path = Path(str(item.get("path") or ""))
            elements_per_pe = int(item.get("elementsPerPe") or 0)
            total_elements = width * height * elements_per_pe
            if not symbol or not dtype or not path:
                blockers.append(f"input_spec_incomplete:{symbol or 'missing_symbol'}")
                continue
            input_buffers.append(
                {
                    "name": str(item.get("buffer") or symbol),
                    "symbol": symbol,
                    "role": str(item.get("role") or "input"),
                    "path": str(path),
                    "dtype": dtype,
                    "elementsPerPe": elements_per_pe,
                    "totalElements": total_elements,
                    "sha256": array_sha256(path),
                    "sha256Kind": "array_tobytes_c_order",
                }
            )
            host, memcpy_dtype, memcpy_elements_per_pe = _memcpy_payload_for_h2d(
                path=path,
                dtype=dtype,
                elements_per_pe=elements_per_pe,
                total_elements=total_elements,
            )
            append_progress(
                progress_path,
                "launch_step_memcpy_h2d",
                launchIndex=launch_index,
                symbol=symbol,
                elements=total_elements,
            )
            print(f"phase:memcpy_h2d:{symbol}", flush=True)
            runner.memcpy_h2d(
                int(runner.get_id(symbol)),
                host,
                0,
                0,
                width,
                height,
                memcpy_elements_per_pe,
                streaming=False,
                order=MemcpyOrder.ROW_MAJOR,
                data_type=memcpy_dtype,
                nonblock=False,
            )
        receipt["inputBuffers"] = input_buffers
        if blockers:
            raise ValueError("; ".join(blockers))
        append_progress(progress_path, "launch_step_launch", launchIndex=launch_index)
        print("phase:launch", flush=True)
        runner.launch(str(spec.get("launchFunction") or "compute"), nonblock=False)
        for post_launch in spec.get("postLaunchFunctions") or []:
            post_launch_name = str(post_launch or "").strip()
            if not post_launch_name:
                continue
            append_progress(
                progress_path,
                "launch_step_post_launch",
                launchIndex=launch_index,
                function=post_launch_name,
            )
            print(f"phase:post_launch:{post_launch_name}", flush=True)
            runner.launch(post_launch_name, nonblock=False)
        outputs: list[dict[str, Any]] = []
        for item in spec.get("outputs") or []:
            if not isinstance(item, dict):
                blockers.append("output_spec_not_object")
                continue
            symbol = str(item.get("symbol") or "")
            dtype = str(item.get("dtype") or "")
            path = Path(str(item.get("path") or ""))
            elements_per_pe = int(item.get("elementsPerPe") or 0)
            output_transform = item.get("outputTransform") or {}
            region = _d2h_region_for_output(
                output_transform=output_transform
                if isinstance(output_transform, dict)
                else {},
                width=width,
                height=height,
            )
            regions = _d2h_regions_for_output(
                output_transform=output_transform
                if isinstance(output_transform, dict)
                else {},
                width=width,
                height=height,
            )
            d2h_elements = (
                int(region["width"]) * int(region["height"]) * elements_per_pe
            )
            device_total_elements = width * height * elements_per_pe
            if not symbol or not dtype or not path:
                blockers.append(f"output_spec_incomplete:{symbol or 'missing_symbol'}")
                continue
            raw_hosts: list[np.ndarray] = []
            np_dtype, _ = _dtype_config(dtype)
            logical_dtype = np.dtype(np_dtype)
            if dtype == "f16" and _chunked_f16_output_available(runner, symbol):
                raw_hosts.append(
                    _chunked_f16_memcpy_d2h(
                        runner=runner,
                        symbol=symbol,
                        elements_per_pe=elements_per_pe,
                        region=region,
                        progress_path=progress_path,
                        launch_index=launch_index,
                    )
                )
                logical_dtype = np.dtype(np.float16)
            else:
                for region_index, copy_region in enumerate(regions):
                    copy_elements = (
                        int(copy_region["width"])
                        * int(copy_region["height"])
                        * elements_per_pe
                    )
                    host_part, memcpy_dtype, memcpy_elements_per_pe, logical_dtype = (
                        _memcpy_buffer_for_d2h(
                            dtype=dtype,
                            elements_per_pe=elements_per_pe,
                            total_elements=copy_elements,
                        )
                    )
                    append_progress(
                        progress_path,
                        "launch_step_memcpy_d2h",
                        launchIndex=launch_index,
                        symbol=symbol,
                        elements=copy_elements,
                        deviceElements=device_total_elements,
                        region=copy_region,
                        regionIndex=region_index,
                        regionCount=len(regions),
                    )
                    print(f"phase:memcpy_d2h:{symbol}:{region_index}", flush=True)
                    runner.memcpy_d2h(
                        host_part,
                        int(runner.get_id(symbol)),
                        int(copy_region["x"]),
                        int(copy_region["y"]),
                        int(copy_region["width"]),
                        int(copy_region["height"]),
                        memcpy_elements_per_pe,
                        streaming=False,
                        order=MemcpyOrder.ROW_MAJOR,
                        data_type=memcpy_dtype,
                        nonblock=False,
                    )
                    raw_hosts.append(host_part)
            if raw_hosts:
                host = (
                    raw_hosts[0]
                    if len(raw_hosts) == 1
                    else np.concatenate(raw_hosts)
                )
            else:
                host, _, _, logical_dtype = _memcpy_buffer_for_d2h(
                    dtype=dtype,
                    elements_per_pe=elements_per_pe,
                    total_elements=0,
                )
            if dtype == "f16":
                host = host.view(logical_dtype).astype(logical_dtype, copy=False)
            saved_host = host
            if isinstance(output_transform, dict):
                transform_kind = str(output_transform.get("kind") or "")
                if transform_kind == "summa_tiles_to_logical_matrix":
                    saved_host = _summa_c_tiles_to_logical(
                        host,
                        output_transform,
                        region=region,
                    )
                elif transform_kind == "dense_gemv_row_shards_to_logits":
                    saved_host = _dense_gemv_row_shards_to_logits(host, output_transform)
                elif transform_kind == "pe_rows_to_logical_matrix":
                    saved_host = _pe_rows_to_logical_matrix(host, output_transform)
                elif transform_kind == "rope_pe_heads_to_logical_matrix":
                    saved_host = _rope_pe_heads_to_logical_matrix(
                        host,
                        output_transform,
                    )
                elif transform_kind == "attention_query_rows_to_logical_matrix":
                    saved_host = _attention_query_rows_to_logical_matrix(
                        host,
                        output_transform,
                    )
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, saved_host)
            outputs.append(
                {
                    "symbol": symbol,
                    "buffer": str(item.get("buffer") or symbol),
                    "dtype": dtype,
                    "path": str(path),
                    "elementsPerPe": elements_per_pe,
                    "totalElements": int(saved_host.size),
                    "deviceTotalElements": device_total_elements,
                    "d2hElements": d2h_elements,
                    "deviceRegion": region,
                    "sha256": hashlib.sha256(
                        saved_host.tobytes(order="C")
                    ).hexdigest(),
                    "sha256Kind": "array_tobytes_c_order",
                }
            )
            if len(regions) > 1:
                outputs[-1]["deviceRegions"] = regions
            if isinstance(output_transform, dict) and output_transform:
                outputs[-1]["outputTransform"] = output_transform
        receipt["outputs"] = outputs
    except Exception as exc:  # pragma: no cover - SDK subprocess evidence
        blockers.append(f"launch_failed:{type(exc).__name__}:{str(exc)[:200]}")
    finally:
        if runner is not None:
            try:
                append_progress(progress_path, "launch_step_stop", launchIndex=launch_index)
                runner.stop()
            except Exception:
                pass

    receipt["status"] = "succeeded" if not blockers else "blocked"
    write_json(receipt_path, receipt)
    if blockers:
        print(f"FAIL:{'; '.join(blockers)}", file=sys.stderr, flush=True)
    else:
        append_progress(progress_path, "launch_step_done", launchIndex=launch_index)
        print("phase:done", flush=True)
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
