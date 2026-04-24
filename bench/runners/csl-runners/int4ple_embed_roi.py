#!/usr/bin/env python3
"""Sparse HostPlan execution helpers for the chunked INT4 PLE embed target."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


FLOAT16_BYTES = 2
FLOAT32_BYTES = 4


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_token_ids(prompt_path: Path) -> np.ndarray:
    tokens = np.fromfile(prompt_path, dtype=np.uint32)
    return tokens.astype(np.uint32, copy=False).ravel()


def token_chunks(tokens: np.ndarray, tokens_per_chunk: int) -> list[np.ndarray]:
    if tokens_per_chunk <= 0:
        raise ValueError("tokens_per_chunk must be positive")
    result: list[np.ndarray] = []
    for start in range(0, int(tokens.size), tokens_per_chunk):
        chunk = np.zeros(tokens_per_chunk, dtype=np.uint32)
        current = tokens[start : start + tokens_per_chunk]
        chunk[: current.size] = current
        result.append(chunk)
    if not result:
        result.append(np.zeros(tokens_per_chunk, dtype=np.uint32))
    return result


def active_pe_ids_for_tokens(
    tokens: np.ndarray,
    *,
    rows_per_pe: int,
    pe_count: int,
) -> list[int]:
    if rows_per_pe <= 0:
        raise ValueError("rows_per_pe must be positive")
    result = {
        int(token) // rows_per_pe
        for token in tokens.astype(np.uint64, copy=False)
        if int(token) // rows_per_pe < pe_count
    }
    return sorted(result)


def pe_coordinates(flat_pe_id: int, width: int) -> tuple[int, int]:
    if width <= 0:
        raise ValueError("width must be positive")
    return flat_pe_id % width, flat_pe_id // width


def read_weight_range_bytes(
    weight_mapping: dict[str, Any],
    logical_offset: int,
    byte_count: int,
) -> bytes:
    if logical_offset < 0 or byte_count < 0:
        raise ValueError("weight range must be non-negative")
    if byte_count == 0:
        return b""
    spans = weight_mapping.get("spans") or []
    chunks = bytearray()
    cursor = 0
    remaining_start = logical_offset
    remaining_count = byte_count
    if isinstance(spans, list) and spans:
        for span in spans:
            if not isinstance(span, dict):
                continue
            span_size = int(span.get("size") or 0)
            span_start = cursor
            span_end = span_start + span_size
            cursor = span_end
            if remaining_start >= span_end:
                continue
            if remaining_count <= 0:
                break
            read_start = max(remaining_start, span_start)
            read_count = min(span_end - read_start, remaining_count)
            shard_path = Path(str(span.get("shardPath") or ""))
            if not shard_path.is_file():
                raise FileNotFoundError(f"weight shard missing: {shard_path}")
            shard_offset = int(span.get("offset") or 0) + (read_start - span_start)
            with shard_path.open("rb") as handle:
                handle.seek(shard_offset)
                payload = handle.read(read_count)
            chunks.extend(payload)
            remaining_count -= len(payload)
            remaining_start = read_start + len(payload)
    else:
        shard_path = Path(str(weight_mapping.get("path") or weight_mapping.get("shard") or ""))
        if not shard_path.is_file():
            raise FileNotFoundError(f"weight shard missing: {shard_path}")
        base_offset = int(weight_mapping.get("byteOffset") or weight_mapping.get("offsetBytes") or 0)
        with shard_path.open("rb") as handle:
            handle.seek(base_offset + logical_offset)
            chunks.extend(handle.read(byte_count))
        remaining_count = byte_count - len(chunks)
    if remaining_count > 0:
        raise ValueError(
            "weight range unavailable:"
            f"{weight_mapping.get('weightKey') or weight_mapping.get('tensor')}:"
            f"{byte_count - remaining_count}<{byte_count}"
        )
    return bytes(chunks)


def materialize_f16_embedding_table_slice(
    weight_mapping: dict[str, Any],
    *,
    row_start: int,
    rows_per_pe: int,
    hidden_offset: int,
    hidden_per_pe: int,
    vocab_size: int,
    hidden_size: int,
) -> np.ndarray:
    if rows_per_pe <= 0 or hidden_per_pe <= 0 or hidden_size <= 0:
        raise ValueError("embedding slice dimensions must be positive")
    table = np.zeros(rows_per_pe * hidden_per_pe, dtype=np.float32)
    for local_row in range(rows_per_pe):
        row = row_start + local_row
        if row >= vocab_size:
            continue
        hidden_count = min(hidden_per_pe, max(0, hidden_size - hidden_offset))
        if hidden_count <= 0:
            continue
        logical_element = row * hidden_size + hidden_offset
        raw = read_weight_range_bytes(
            weight_mapping,
            logical_element * FLOAT16_BYTES,
            hidden_count * FLOAT16_BYTES,
        )
        values = np.frombuffer(raw, dtype=np.float16).astype(np.float32, copy=False)
        dest = local_row * hidden_per_pe
        table[dest : dest + hidden_count] = values
    return table


def array_link(path: Path, array: np.ndarray) -> dict[str, Any]:
    data = array.tobytes(order="C")
    return {
        "path": str(path),
        "sha256": sha256_bytes(data),
        "byteLength": len(data),
        "elementCount": int(array.size),
    }


def build_embed_roi_spec(
    *,
    roi_dir: Path,
    launch: dict[str, Any],
    prompt_path: Path,
    output_buffer_path: Path,
) -> tuple[dict[str, Any], str]:
    compile_params = launch.get("compileParams") or {}
    geometry = launch.get("targetGeometry") or {}
    input_bindings = launch.get("resolvedInputs") or launch.get("inputBindings") or []
    output_bindings = launch.get("resolvedOutputs") or launch.get("outputBindings") or []
    table_binding = next(
        (
            item
            for item in input_bindings
            if isinstance(item, dict) and item.get("symbol") == "table"
        ),
        None,
    )
    output_binding = next(
        (
            item
            for item in output_bindings
            if isinstance(item, dict) and item.get("symbol") == "output"
        ),
        None,
    )
    if not isinstance(table_binding, dict):
        raise ValueError("embed table binding missing")
    if not isinstance(output_binding, dict):
        raise ValueError("embed output binding missing")
    table_materialization = table_binding.get("materialization") or {}
    output_materialization = output_binding.get("materialization") or {}
    weight_mapping = table_materialization.get("weightMapping") or {}
    if not isinstance(weight_mapping, dict):
        raise ValueError("embed weight mapping missing")
    shape = weight_mapping.get("shape") or []
    if len(shape) >= 2:
        vocab_size = int(shape[0])
        hidden_size = int(shape[1])
    else:
        hidden_size = int(compile_params.get("hidden_size") or 0)
        byte_size = int(weight_mapping.get("byteSize") or 0)
        vocab_size = byte_size // max(1, hidden_size * FLOAT16_BYTES)
    rows_per_pe = int(compile_params.get("rows_per_pe") or 0)
    hidden_per_pe = int(compile_params.get("hidden_per_pe") or 0)
    tokens_per_chunk = int(compile_params.get("tokens_per_chunk") or 0)
    width = int(geometry.get("width") or compile_params.get("width") or 1)
    height = int(geometry.get("height") or compile_params.get("height") or 1)
    pe_count = int(geometry.get("peCount") or (width * height))
    if min(rows_per_pe, hidden_size, hidden_per_pe, tokens_per_chunk, width, height, pe_count) <= 0:
        raise ValueError("embed compile params incomplete for ROI execution")

    tokens = load_token_ids(prompt_path)
    chunks = token_chunks(tokens, tokens_per_chunk)
    roi_dir.mkdir(parents=True, exist_ok=True)
    sublaunches: list[dict[str, Any]] = []
    input_symbol = str(table_binding.get("symbol") or "table")
    output_symbol = str(output_binding.get("symbol") or "output")
    indices_symbol = "indices"
    indices_binding = next(
        (
            item
            for item in input_bindings
            if isinstance(item, dict) and item.get("symbol") == "indices"
        ),
        {},
    )
    indices_symbol = str(indices_binding.get("symbol") or indices_symbol)
    for token_chunk_index, chunk in enumerate(chunks):
        indices_path = roi_dir / f"indices-token-{token_chunk_index:04d}.npy"
        np.save(indices_path, chunk)
        active_pe_ids = active_pe_ids_for_tokens(
            chunk[: min(tokens_per_chunk, max(0, int(tokens.size) - token_chunk_index * tokens_per_chunk))],
            rows_per_pe=rows_per_pe,
            pe_count=pe_count,
        )
        for hidden_offset in range(0, hidden_size, hidden_per_pe):
            pe_tables: list[dict[str, Any]] = []
            for flat_pe_id in active_pe_ids:
                pe_x, pe_y = pe_coordinates(flat_pe_id, width)
                row_start = flat_pe_id * rows_per_pe
                table = materialize_f16_embedding_table_slice(
                    weight_mapping,
                    row_start=row_start,
                    rows_per_pe=rows_per_pe,
                    hidden_offset=hidden_offset,
                    hidden_per_pe=hidden_per_pe,
                    vocab_size=vocab_size,
                    hidden_size=hidden_size,
                )
                table_path = (
                    roi_dir
                    / f"table-token-{token_chunk_index:04d}-hidden-{hidden_offset:06d}-pe-{flat_pe_id:05d}.npy"
                )
                np.save(table_path, table)
                pe_tables.append(
                    {
                        "flatPeId": flat_pe_id,
                        "x": pe_x,
                        "y": pe_y,
                        "rowStart": row_start,
                        "rowEnd": min(row_start + rows_per_pe, vocab_size),
                        "table": array_link(table_path, table),
                    }
                )
            sublaunches.append(
                {
                    "tokenChunkIndex": token_chunk_index,
                    "tokenStart": token_chunk_index * tokens_per_chunk,
                    "tokenCount": int(
                        min(tokens_per_chunk, max(0, int(tokens.size) - token_chunk_index * tokens_per_chunk))
                    ),
                    "hiddenOffset": hidden_offset,
                    "hiddenCount": int(min(hidden_per_pe, hidden_size - hidden_offset)),
                    "indices": array_link(indices_path, chunk),
                    "activePeCount": len(active_pe_ids),
                    "peTables": pe_tables,
                }
            )
    compact_output = np.zeros((int(tokens.size), hidden_size), dtype=np.float32)
    np.save(output_buffer_path, compact_output)
    output_buffer = str(output_binding.get("buffer") or "")
    spec = {
        "schemaVersion": 1,
        "artifactKind": "int4ple_embed_roi_launch_spec",
        "compileDir": launch.get("compileDir"),
        "launchFunction": launch.get("launchFunction") or "compute",
        "launchIndex": int(launch.get("launchIndex") or 0),
        "cmaddr": "",
        "targetGeometry": {
            "width": width,
            "height": height,
            "peCount": pe_count,
        },
        "compileParams": {
            "rowsPerPe": rows_per_pe,
            "hiddenSize": hidden_size,
            "hiddenPerPe": hidden_per_pe,
            "tokensPerChunk": tokens_per_chunk,
            "vocabSize": vocab_size,
        },
        "symbols": {
            "indices": indices_symbol,
            "table": input_symbol,
            "output": output_symbol,
        },
        "prompt": {
            "path": str(prompt_path),
            "tokenCount": int(tokens.size),
            "sha256": sha256_bytes(tokens.tobytes(order="C")),
        },
        "output": {
            "buffer": output_buffer,
            "path": str(output_buffer_path),
            "dtype": str(output_materialization.get("dtype") or "f32"),
            "shape": [int(tokens.size), hidden_size],
            "elementCount": int(compact_output.size),
        },
        "sublaunches": sublaunches,
    }
    digest = sha256_bytes(
        json.dumps(spec, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return spec, digest
