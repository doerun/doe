#!/usr/bin/env cs_python
"""Generic single-step kernel adapter for the subprocess chain driver.

Reads zero or more input .npy tensors, memcpy_h2d's them to the named
device symbols of a compiled CSL kernel, launches the kernel, then
memcpy_d2h's the named output symbols into one or more output .npy
files. Exits cleanly; the subprocess boundary resets SDK global state
so the parent chain driver can spawn a fresh adapter per step and avoid
the `simfab_api.cc:111: Assertion '0' failed` that multiple SdkRuntime
instances trigger in one process.

CLI:
  --compile-dir       cslc -o output directory
  --launch-fn         device function to launch (default: compute)
  --width             PE grid width
  --chunk-size        default elements-per-PE (tensors may override)
  --input             symbol:path.npy[:dtype[:chunk_size]]   (may repeat)
  --output            symbol:path.npy[:dtype[:chunk_size]]   (may repeat)
  --cmaddr            optional CM endpoint

Per-tensor chunk_size override matters when a kernel has inputs of
different per-PE sizes — e.g. gather: indices=num_tokens, table=rows*hidden.

Dtype maps: f32 → MEMCPY_32BIT + np.float32; u32 → MEMCPY_32BIT +
np.uint32; f16 → MEMCPY_32BIT with a uint32 byte-preserving view; u8 →
MEMCPY_32BIT with a uint32 byte-preserving view. The f16 path keeps the
logical tensor dtype as np.float16 while satisfying SDK memcpy calls that
require 32-bit host words. f16 per-PE chunk sizes must be even so each
memcpy word carries exactly two half values.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)


DTYPE_MAP = {
    "f32": (np.float32, MemcpyDataType.MEMCPY_32BIT),
    "u32": (np.uint32, MemcpyDataType.MEMCPY_32BIT),
    "f16": (np.float16, MemcpyDataType.MEMCPY_32BIT),
    "u8": (np.uint8, MemcpyDataType.MEMCPY_32BIT),
}


def _load_writeable_mmap_or_copy(path: str) -> np.ndarray:
    try:
        return np.load(path, mmap_mode="r+").ravel()
    except (OSError, ValueError):
        return np.load(path, mmap_mode="r").ravel()


def parse_spec(spec: str) -> tuple[str, str, str, int | None]:
    parts = spec.split(":")
    if len(parts) == 2:
        symbol, path = parts
        dtype = "f32"
        chunk_override: int | None = None
    elif len(parts) == 3:
        symbol, path, dtype = parts
        chunk_override = None
    elif len(parts) == 4:
        symbol, path, dtype, chunk = parts
        chunk_override = int(chunk)
    else:
        raise ValueError(f"bad spec {spec!r} — expected symbol:path[:dtype[:chunk_size]]")
    if dtype not in DTYPE_MAP:
        raise ValueError(f"dtype {dtype!r} must be one of {list(DTYPE_MAP)}")
    return symbol, path, dtype, chunk_override


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--compile-dir", required=True)
    p.add_argument("--launch-fn", default="compute")
    p.add_argument("--width", type=int, required=True)
    p.add_argument(
        "--height",
        type=int,
        default=1,
        help=(
            "PE grid height. Defaults to 1 for 1-D rows. Required for 2-D "
            "kernels like tiled_matmul that use @set_rectangle(P, P) where "
            "width=P and height=P."
        ),
    )
    p.add_argument("--chunk-size", type=int, required=True)
    p.add_argument("--input", action="append", default=[])
    p.add_argument("--output", action="append", required=True)
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


def _memcpy_payload_for_h2d(
    *, path: str, dtype: str, chunk_size: int, pe_count: int
) -> tuple[np.ndarray, MemcpyDataType, int]:
    if dtype == "f16":
        if chunk_size % 2 != 0:
            raise ValueError(
                f"f16 chunk_size {chunk_size} must be even for "
                "MEMCPY_32BIT byte-preserving transfer"
            )
        raw = _load_writeable_mmap_or_copy(path)
        expected = pe_count * chunk_size
        if raw.size != expected:
            raise ValueError(
                f"f16 tensor {path} has {raw.size} elements, expected {expected}"
            )
        if (
            raw.dtype != np.float16
            or not raw.flags.c_contiguous
            or not raw.flags.writeable
        ):
            raw = np.ascontiguousarray(raw, dtype=np.float16)
        return (
            raw.view(np.uint32),
            MemcpyDataType.MEMCPY_32BIT,
            chunk_size // 2,
        )
    if dtype == "u8":
        if chunk_size % 4 != 0:
            raise ValueError(
                f"u8 chunk_size {chunk_size} must be 4-aligned for "
                "MEMCPY_32BIT byte-preserving transfer"
            )
        raw = _load_writeable_mmap_or_copy(path)
        expected = pe_count * chunk_size
        if raw.size != expected:
            raise ValueError(
                f"u8 tensor {path} has {raw.size} bytes, expected {expected}"
            )
        if (
            raw.dtype != np.uint8
            or not raw.flags.c_contiguous
            or not raw.flags.writeable
        ):
            raw = np.ascontiguousarray(raw, dtype=np.uint8)
        return (
            raw.view(np.uint32),
            MemcpyDataType.MEMCPY_32BIT,
            chunk_size // 4,
        )
    np_dtype, mcpy_dtype = DTYPE_MAP[dtype]
    return (
        np.load(path).astype(np_dtype, copy=False).ravel(),
        mcpy_dtype,
        chunk_size,
    )


def _memcpy_buffer_for_d2h(
    *, dtype: str, chunk_size: int, pe_count: int
) -> tuple[np.ndarray, MemcpyDataType, int, np.dtype]:
    if dtype == "f16":
        if chunk_size % 2 != 0:
            raise ValueError(
                f"f16 chunk_size {chunk_size} must be even for "
                "MEMCPY_32BIT byte-preserving transfer"
            )
        return (
            np.zeros(pe_count * (chunk_size // 2), dtype=np.uint32),
            MemcpyDataType.MEMCPY_32BIT,
            chunk_size // 2,
            np.dtype(np.float16),
        )
    if dtype == "u8":
        if chunk_size % 4 != 0:
            raise ValueError(
                f"u8 chunk_size {chunk_size} must be 4-aligned for "
                "MEMCPY_32BIT byte-preserving transfer"
            )
        return (
            np.zeros(pe_count * (chunk_size // 4), dtype=np.uint32),
            MemcpyDataType.MEMCPY_32BIT,
            chunk_size // 4,
            np.dtype(np.uint8),
        )
    np_dtype, mcpy_dtype = DTYPE_MAP[dtype]
    return (
        np.zeros(pe_count * chunk_size, dtype=np_dtype),
        mcpy_dtype,
        chunk_size,
        np.dtype(np_dtype),
    )


def _save_outputs(outputs: list[tuple[str, str, np.ndarray]]) -> None:
    for symbol, path, arr in outputs:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.save(path, arr)
        print(f"[adapter] wrote {symbol} -> {path} ({arr.dtype} shape={arr.shape})")


def main() -> int:
    args = parse_args()
    width = args.width
    height = args.height
    chunk_size = args.chunk_size
    pe_count = width * height

    cmaddr = args.cmaddr.strip() or None
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    runner.load()
    runner.run()

    for spec in args.input:
        symbol, path, dtype, chunk_override = parse_spec(spec)
        sym_id = runner.get_id(symbol)
        this_chunk = chunk_override if chunk_override is not None else chunk_size
        arr, mcpy_dtype, memcpy_chunk = _memcpy_payload_for_h2d(
            path=path,
            dtype=dtype,
            chunk_size=this_chunk,
            pe_count=pe_count,
        )
        runner.memcpy_h2d(
            sym_id, arr, 0, 0, width, height, memcpy_chunk,
            streaming=False, order=MemcpyOrder.ROW_MAJOR,
            data_type=mcpy_dtype, nonblock=False,
        )

    runner.launch(args.launch_fn, nonblock=False)

    outputs: list[tuple[str, str, np.ndarray]] = []
    for spec in args.output:
        symbol, path, dtype, chunk_override = parse_spec(spec)
        this_chunk = chunk_override if chunk_override is not None else chunk_size
        arr, mcpy_dtype, memcpy_chunk, output_dtype = _memcpy_buffer_for_d2h(
            dtype=dtype,
            chunk_size=this_chunk,
            pe_count=pe_count,
        )
        sym_id = runner.get_id(symbol)
        runner.memcpy_d2h(
            arr, sym_id, 0, 0, width, height, memcpy_chunk,
            streaming=False, order=MemcpyOrder.ROW_MAJOR,
            data_type=mcpy_dtype, nonblock=False,
        )
        if dtype in ("f16", "u8"):
            arr = arr.view(output_dtype).astype(output_dtype, copy=False)
        outputs.append((symbol, path, arr))

    _save_outputs(outputs)

    runner.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
