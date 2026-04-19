#!/usr/bin/env cs_python
"""Generic single-step kernel adapter for the subprocess chain driver.

Reads one or more input .npy tensors, memcpy_h2d's them to the named
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
np.uint32. Chain payloads are 32-bit today by design; larger dtypes
are a follow-up once the streaming executor lands.
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
}


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
    p.add_argument("--input", action="append", required=True)
    p.add_argument("--output", action="append", required=True)
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


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
        np_dtype, mcpy_dtype = DTYPE_MAP[dtype]
        arr = np.load(path).astype(np_dtype, copy=False)
        sym_id = runner.get_id(symbol)
        this_chunk = chunk_override if chunk_override is not None else chunk_size
        runner.memcpy_h2d(
            sym_id, arr.ravel(), 0, 0, width, height, this_chunk,
            streaming=False, order=MemcpyOrder.ROW_MAJOR,
            data_type=mcpy_dtype, nonblock=False,
        )

    runner.launch(args.launch_fn, nonblock=False)

    outputs: list[tuple[str, str, np.ndarray]] = []
    for spec in args.output:
        symbol, path, dtype, chunk_override = parse_spec(spec)
        np_dtype, mcpy_dtype = DTYPE_MAP[dtype]
        this_chunk = chunk_override if chunk_override is not None else chunk_size
        arr = np.zeros(pe_count * this_chunk, dtype=np_dtype)
        sym_id = runner.get_id(symbol)
        runner.memcpy_d2h(
            arr, sym_id, 0, 0, width, height, this_chunk,
            streaming=False, order=MemcpyOrder.ROW_MAJOR,
            data_type=mcpy_dtype, nonblock=False,
        )
        outputs.append((symbol, path, arr))

    runner.stop()

    for symbol, path, arr in outputs:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.save(path, arr)
        print(f"[adapter] wrote {symbol} → {path} ({arr.dtype} shape={arr.shape})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
