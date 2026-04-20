"""Doppler RDRR Q4_K_M decode helpers for Doe evidence tooling."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Q4_K_M_BLOCK_ELEMENTS = 256
Q4_K_M_SUBBLOCK_ELEMENTS = 32
Q4_K_M_SUBBLOCKS = 8
Q4_K_M_BLOCK_BYTES = 144
Q4_K_M_QUANT_BYTES_OFFSET = 16


@dataclass(frozen=True)
class TensorSpan:
    shard_index: int
    filename: str
    offset: int
    size: int


def product(values: list[int]) -> int:
    result = 1
    for value in values:
        result *= int(value)
    return result


def float16_to_float32(word: int) -> float:
    return float(struct.unpack("<e", struct.pack("<H", word))[0])


def f32_values_to_bytes(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def f16_bytes_to_f32_values(raw: bytes) -> list[float]:
    if len(raw) % 2 != 0:
        raise ValueError("F16 span has odd byte length")
    return [
        float16_to_float32(raw[i] | (raw[i + 1] << 8))
        for i in range(0, len(raw), 2)
    ]


def f32_bytes_to_values(raw: bytes) -> list[float]:
    if len(raw) % 4 != 0:
        raise ValueError("F32 span byte length is not divisible by 4")
    return [row[0] for row in struct.iter_unpack("<f", raw)]


def unpack_q4k_scale_min_bits(
    block: bytes,
) -> tuple[list[int], list[int], float, float]:
    if len(block) != Q4_K_M_BLOCK_BYTES:
        raise ValueError(
            f"Q4_K_M block has {len(block)} bytes, expected "
            f"{Q4_K_M_BLOCK_BYTES}"
        )
    d = float16_to_float32(block[0] | (block[1] << 8))
    dmin = float16_to_float32(block[2] | (block[3] << 8))
    scale_bits = [0] * Q4_K_M_SUBBLOCKS
    min_bits = [0] * Q4_K_M_SUBBLOCKS
    for index in range(4):
        scale_bits[index] = block[4 + index] & 0x3F
        scale_bits[index + 4] = ((block[4 + index] >> 6) & 0x03) << 4
        min_bits[index] = block[8 + index] & 0x3F
        min_bits[index + 4] = ((block[8 + index] >> 6) & 0x03) << 4
    for index in range(4):
        scale_bits[index + 4] |= block[12 + index] & 0x0F
        min_bits[index + 4] |= (block[12 + index] >> 4) & 0x0F
    return scale_bits, min_bits, d, dmin


def dequantize_q4km_block(block: bytes) -> list[float]:
    scale_bits, min_bits, d, dmin = unpack_q4k_scale_min_bits(block)
    scales = [d * value for value in scale_bits]
    min_offsets = [dmin * value for value in min_bits]
    result = [0.0] * Q4_K_M_BLOCK_ELEMENTS
    for chunk in range(4):
        chunk_base = chunk * 64
        byte_base = Q4_K_M_QUANT_BYTES_OFFSET + chunk * 32
        for index in range(32):
            packed = block[byte_base + index]
            low = packed & 0x0F
            high = (packed >> 4) & 0x0F
            lo_index = chunk_base + index
            hi_index = chunk_base + 32 + index
            lo_subblock = lo_index // Q4_K_M_SUBBLOCK_ELEMENTS
            hi_subblock = hi_index // Q4_K_M_SUBBLOCK_ELEMENTS
            result[lo_index] = (
                scales[lo_subblock] * low - min_offsets[lo_subblock]
            )
            result[hi_index] = (
                scales[hi_subblock] * high - min_offsets[hi_subblock]
            )
    return result


def dequantize_q4km_flat_bytes(
    raw: bytes,
    num_blocks: int,
    shape: list[int],
) -> list[float]:
    expected_len = num_blocks * Q4_K_M_BLOCK_BYTES
    if len(raw) != expected_len:
        raise ValueError(
            f"Q4_K_M flat byte length {len(raw)} != expected {expected_len}"
        )
    total = product(shape)
    values: list[float] = []
    for block_index in range(num_blocks):
        start = block_index * Q4_K_M_BLOCK_BYTES
        block_values = dequantize_q4km_block(
            raw[start:start + Q4_K_M_BLOCK_BYTES]
        )
        remaining = total - len(values)
        values.extend(block_values[:remaining])
        if len(values) >= total:
            break
    return values


def dequantize_q4km_rowwise_bytes(
    raw: bytes,
    shape: list[int],
) -> list[float]:
    if len(shape) < 2:
        raise ValueError("rowwise Q4_K_M tensor shape must have rows and cols")
    rows = int(shape[0])
    cols = product([int(value) for value in shape[1:]])
    blocks_per_row = math.ceil(cols / Q4_K_M_BLOCK_ELEMENTS)
    expected_len = rows * blocks_per_row * Q4_K_M_BLOCK_BYTES
    if len(raw) != expected_len:
        raise ValueError(
            f"Q4_K_M rowwise byte length {len(raw)} != expected "
            f"{expected_len}"
        )
    values: list[float] = []
    row_stride = blocks_per_row * Q4_K_M_BLOCK_BYTES
    for row in range(rows):
        row_values: list[float] = []
        row_start = row * row_stride
        for block_index in range(blocks_per_row):
            block_start = row_start + block_index * Q4_K_M_BLOCK_BYTES
            row_values.extend(
                dequantize_q4km_block(
                    raw[block_start:block_start + Q4_K_M_BLOCK_BYTES]
                )
            )
        values.extend(row_values[:cols])
    return values


def shards_by_index(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        int(shard["index"]): shard
        for shard in manifest.get("shards", [])
    }


def tensor_spans(
    tensor: dict[str, Any],
    shard_table: dict[int, dict[str, Any]],
) -> list[TensorSpan]:
    raw_spans = tensor.get("spans")
    normalized: list[dict[str, Any]]
    if isinstance(raw_spans, list):
        normalized = raw_spans
    elif tensor.get("shard") is not None:
        normalized = [{
            "shardIndex": int(tensor["shard"]),
            "offset": int(tensor["offset"]),
            "size": int(tensor["size"]),
        }]
    else:
        return []
    spans: list[TensorSpan] = []
    for raw_span in normalized:
        shard_index = int(raw_span.get("shardIndex", raw_span.get("shard")))
        shard = shard_table.get(shard_index)
        filename = (
            str(shard.get("filename"))
            if shard is not None and shard.get("filename")
            else f"shard_{shard_index:05d}.bin"
        )
        spans.append(TensorSpan(
            shard_index=shard_index,
            filename=filename,
            offset=int(raw_span["offset"]),
            size=int(raw_span["size"]),
        ))
    return spans


def read_tensor_byte_range(
    artifact_root: Path,
    manifest: dict[str, Any],
    tensor_name: str,
    byte_start: int,
    byte_count: int,
) -> bytes:
    tensor = (manifest.get("tensors") or {}).get(tensor_name)
    if tensor is None:
        raise KeyError(f"tensor not found in RDRR manifest: {tensor_name}")
    declared_size = int(tensor.get("size", 0))
    if byte_start < 0 or byte_count < 0 or byte_start + byte_count > declared_size:
        raise ValueError(
            f"{tensor_name}: requested byte range "
            f"{byte_start}:{byte_start + byte_count} exceeds tensor size "
            f"{declared_size}"
        )
    spans = tensor_spans(tensor, shards_by_index(manifest))
    if not spans:
        raise ValueError(f"{tensor_name}: no tensor spans in manifest")
    remaining_start = byte_start
    remaining_count = byte_count
    chunks = bytearray()
    for span in spans:
        if remaining_start >= span.size:
            remaining_start -= span.size
            continue
        take_start = span.offset + remaining_start
        take_count = min(span.size - remaining_start, remaining_count)
        path = artifact_root / span.filename
        if not path.is_file():
            raise FileNotFoundError(f"shard file not found: {path}")
        file_size = path.stat().st_size
        if take_start < 0 or take_start + take_count > file_size:
            raise ValueError(
                f"{tensor_name}: span range outside shard {span.filename}: "
                f"{take_start}+{take_count} > {file_size}"
            )
        with path.open("rb") as handle:
            handle.seek(take_start)
            raw = handle.read(take_count)
        if len(raw) != take_count:
            raise ValueError(
                f"{tensor_name}: short read from {span.filename}"
            )
        chunks.extend(raw)
        remaining_start = 0
        remaining_count -= take_count
        if remaining_count == 0:
            break
    if remaining_count != 0:
        raise ValueError(f"{tensor_name}: spans ended before range was read")
    return bytes(chunks)


def read_f16_tensor_prefix(
    artifact_root: Path,
    manifest: dict[str, Any],
    tensor_name: str,
    count: int,
) -> list[float]:
    tensor = (manifest.get("tensors") or {}).get(tensor_name)
    if tensor is None:
        raise KeyError(f"tensor not found in RDRR manifest: {tensor_name}")
    if tensor.get("dtype") != "F16":
        raise ValueError(f"{tensor_name}: dtype {tensor.get('dtype')!r} != F16")
    raw = read_tensor_byte_range(artifact_root, manifest, tensor_name, 0, count * 2)
    return f16_bytes_to_f32_values(raw)


def read_f32_tensor_prefix(
    artifact_root: Path,
    manifest: dict[str, Any],
    tensor_name: str,
    count: int,
) -> list[float]:
    tensor = (manifest.get("tensors") or {}).get(tensor_name)
    if tensor is None:
        raise KeyError(f"tensor not found in RDRR manifest: {tensor_name}")
    if tensor.get("dtype") != "F32":
        raise ValueError(f"{tensor_name}: dtype {tensor.get('dtype')!r} != F32")
    raw = read_tensor_byte_range(artifact_root, manifest, tensor_name, 0, count * 4)
    return f32_bytes_to_values(raw)


def read_q4km_rowwise_prefix(
    artifact_root: Path,
    manifest: dict[str, Any],
    tensor_name: str,
    count: int,
) -> list[float]:
    tensor = (manifest.get("tensors") or {}).get(tensor_name)
    if tensor is None:
        raise KeyError(f"tensor not found in RDRR manifest: {tensor_name}")
    if tensor.get("dtype") != "Q4_K_M":
        raise ValueError(
            f"{tensor_name}: dtype {tensor.get('dtype')!r} != Q4_K_M"
        )
    if tensor.get("layout") != "row":
        raise ValueError(f"{tensor_name}: Q4_K_M layout must be row")
    shape = [int(value) for value in tensor.get("shape", [])]
    if len(shape) < 2:
        raise ValueError(f"{tensor_name}: rowwise tensor shape is invalid")
    rows = shape[0]
    cols = product(shape[1:])
    total = rows * cols
    if count < 0 or count > total:
        raise ValueError(
            f"{tensor_name}: prefix count {count} outside tensor size {total}"
        )
    blocks_per_row = math.ceil(cols / Q4_K_M_BLOCK_ELEMENTS)
    row_stride_bytes = blocks_per_row * Q4_K_M_BLOCK_BYTES
    out: list[float] = []
    remaining = count
    for row in range(rows):
        if remaining == 0:
            break
        values_this_row = min(cols, remaining)
        blocks_needed = math.ceil(values_this_row / Q4_K_M_BLOCK_ELEMENTS)
        raw = read_tensor_byte_range(
            artifact_root,
            manifest,
            tensor_name,
            row * row_stride_bytes,
            blocks_needed * Q4_K_M_BLOCK_BYTES,
        )
        row_values = dequantize_q4km_flat_bytes(
            raw,
            blocks_needed,
            [1, blocks_needed * Q4_K_M_BLOCK_ELEMENTS],
        )
        out.extend(row_values[:values_this_row])
        remaining -= values_this_row
    return out


def read_tensor_prefix_as_f32(
    artifact_root: Path,
    manifest: dict[str, Any],
    tensor_name: str,
    count: int,
) -> list[float]:
    tensor = (manifest.get("tensors") or {}).get(tensor_name)
    if tensor is None:
        raise KeyError(f"tensor not found in RDRR manifest: {tensor_name}")
    dtype = tensor.get("dtype")
    if dtype == "Q4_K_M":
        return read_q4km_rowwise_prefix(
            artifact_root, manifest, tensor_name, count
        )
    if dtype == "F16":
        return read_f16_tensor_prefix(artifact_root, manifest, tensor_name, count)
    if dtype == "F32":
        return read_f32_tensor_prefix(artifact_root, manifest, tensor_name, count)
    raise ValueError(f"{tensor_name}: unsupported dtype {dtype!r}")
