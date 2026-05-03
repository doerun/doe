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
  --input             symbol:path.npy[:dtype[:chunk_size[:x,y,w,h]]]   (may repeat)
  --output            symbol:path.npy[:dtype[:chunk_size[:x,y,w,h]]]   (may repeat)
  --cmaddr            optional CM endpoint

Per-tensor chunk_size override matters when a kernel has inputs of
different per-PE sizes. Output region override matters for kernels whose
host contract reads a reduced PE subset, e.g. dense GEMV reads the sink
column after east-west reduction.

Dtype maps: f32 → MEMCPY_32BIT + np.float32; u32 → MEMCPY_32BIT +
np.uint32; f16 → MEMCPY_32BIT with a uint32 byte-preserving view; u8 →
MEMCPY_32BIT with a uint32 byte-preserving view. The f16 path keeps the
logical tensor dtype as np.float16 while satisfying SDK memcpy calls that
require 32-bit host words. f16 per-PE chunk sizes must be even so each
memcpy word carries exactly two half values.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

os.environ.setdefault("CSL_SUPPRESS_SIMFAB_TRACE", "1")

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
PHASE_TRACE_PATH: Path | None = None
SIMFAB_THREADS_ENV = "DOE_SIMFAB_THREADS"
MAX_SIMFAB_THREADS = 64


def _simfab_numthreads_from_env() -> int | None:
    raw = os.environ.get(SIMFAB_THREADS_ENV)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{SIMFAB_THREADS_ENV} must be an integer, received {raw!r}"
        ) from exc
    if value <= 0 or value > MAX_SIMFAB_THREADS:
        raise ValueError(
            f"{SIMFAB_THREADS_ENV} must be in 1..{MAX_SIMFAB_THREADS}, "
            f"received {value}"
        )
    return value


def _load_writeable_mmap_or_copy(path: str) -> np.ndarray:
    try:
        return np.load(path, mmap_mode="r+").ravel()
    except (OSError, ValueError):
        return np.load(path, mmap_mode="r").ravel()


def _writeable_contiguous_array(raw: np.ndarray, dtype: np.dtype) -> np.ndarray:
    if raw.dtype == dtype and raw.flags.c_contiguous and raw.flags.writeable:
        return raw
    return np.array(raw, dtype=dtype, copy=True, order="C")


def _parse_region(region: str) -> tuple[int, int, int, int]:
    pieces = region.split(",")
    if len(pieces) != 4:
        raise ValueError(f"bad region {region!r} - expected x,y,width,height")
    x, y, width, height = (int(piece) for piece in pieces)
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError(f"bad region {region!r} - coordinates must be positive")
    return x, y, width, height


def parse_io_spec(
    spec: str,
) -> tuple[str, str, str, int | None, tuple[int, int, int, int] | None]:
    parts = spec.split(":")
    if len(parts) == 2:
        symbol, path = parts
        dtype = "f32"
        chunk_override: int | None = None
        region = None
    elif len(parts) == 3:
        symbol, path, dtype = parts
        chunk_override = None
        region = None
    elif len(parts) == 4:
        symbol, path, dtype, chunk = parts
        chunk_override = int(chunk)
        region = None
    elif len(parts) == 5:
        symbol, path, dtype, chunk, region_token = parts
        chunk_override = int(chunk)
        region = _parse_region(region_token)
    else:
        raise ValueError(
            f"bad spec {spec!r} - expected "
            "symbol:path[:dtype[:chunk_size[:x,y,width,height]]]"
        )
    if dtype not in DTYPE_MAP:
        raise ValueError(f"dtype {dtype!r} must be one of {list(DTYPE_MAP)}")
    return symbol, path, dtype, chunk_override, region


def parse_spec(spec: str) -> tuple[str, str, str, int | None]:
    symbol, path, dtype, chunk_override, _ = parse_io_spec(spec)
    return symbol, path, dtype, chunk_override


def _validate_region(
    *,
    region: tuple[int, int, int, int] | None,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    if region is None:
        return 0, 0, width, height
    x, y, region_width, region_height = region
    if x + region_width > width or y + region_height > height:
        raise ValueError(
            "output region exceeds PE grid: "
            f"{region!r} outside width={width},height={height}"
        )
    return region


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
    p.add_argument(
        "--batch-json",
        default="",
        help=(
            "Optional JSON file with steps[].inputs and steps[].outputs. "
            "When set, --input is ignored and --output only satisfies the "
            "legacy required CLI shape."
        ),
    )
    p.add_argument("--cmaddr", default="")
    p.add_argument(
        "--split-d2h-rows",
        action="store_true",
        help=(
            "Copy output regions back one device row at a time and "
            "concatenate them in row-major order."
        ),
    )
    p.add_argument(
        "--phase-trace",
        default="",
        help="Optional path for durable phase breadcrumb lines.",
    )
    return p.parse_args()


def _load_batch_steps(path: str) -> list[dict[str, object]]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_steps = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(raw_steps, list):
        raise ValueError(f"batch JSON {path} must contain steps[]")
    steps: list[dict[str, object]] = []
    for index, step in enumerate(raw_steps):
        if not isinstance(step, dict):
            raise ValueError(f"batch step {index} must be an object")
        inputs = step.get("inputs")
        outputs = step.get("outputs")
        if not isinstance(inputs, list) or not all(
            isinstance(item, str) for item in inputs
        ):
            raise ValueError(f"batch step {index} inputs must be strings")
        if not isinstance(outputs, list) or not all(
            isinstance(item, str) for item in outputs
        ):
            raise ValueError(f"batch step {index} outputs must be strings")
        steps.append(step)
    return steps


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
        raw = _writeable_contiguous_array(raw, np.dtype(np.float16))
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
        raw = _writeable_contiguous_array(raw, np.dtype(np.uint8))
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


def _logical_output_array(
    *,
    arr: np.ndarray,
    dtype: str,
    output_dtype: np.dtype,
) -> np.ndarray:
    if dtype in ("f16", "u8"):
        return arr.view(output_dtype).astype(output_dtype, copy=False)
    return arr


def _copy_d2h_output(
    *,
    runner: SdkRuntime,
    symbol: str,
    path: str,
    dtype: str,
    chunk_size: int,
    region: tuple[int, int, int, int],
    split_rows: bool,
    step_index: int,
) -> tuple[str, str, np.ndarray]:
    region_x, region_y, region_width, region_height = region
    sym_id = runner.get_id(symbol)
    if split_rows and (region_height > 1 or region_width > 1):
        rows: list[np.ndarray] = []
        for row_offset in range(region_height):
            row_parts: list[np.ndarray] = []
            row_y = region_y + row_offset
            for col_offset in range(region_width):
                arr, mcpy_dtype, memcpy_chunk, output_dtype = (
                    _memcpy_buffer_for_d2h(
                        dtype=dtype,
                        chunk_size=chunk_size,
                        pe_count=1,
                    )
                )
                col_x = region_x + col_offset
                _phase(
                    "memcpy_d2h_start",
                    step=step_index,
                    symbol=symbol,
                    x=col_x,
                    y=row_y,
                    width=1,
                    height=1,
                    chunk=memcpy_chunk,
                    words=arr.size,
                    rowOffset=row_offset,
                    colOffset=col_offset,
                )
                runner.memcpy_d2h(
                    arr,
                    sym_id,
                    col_x,
                    row_y,
                    1,
                    1,
                    memcpy_chunk,
                    streaming=False, order=MemcpyOrder.ROW_MAJOR,
                    data_type=mcpy_dtype, nonblock=False,
                )
                _phase(
                    "memcpy_d2h_complete",
                    step=step_index,
                    symbol=symbol,
                    rowOffset=row_offset,
                    colOffset=col_offset,
                )
                row_parts.append(
                    _logical_output_array(
                        arr=arr,
                        dtype=dtype,
                        output_dtype=output_dtype,
                    ).reshape(-1)
                )
            rows.append(np.concatenate(row_parts))
        return symbol, path, np.concatenate(rows)

    region_pe_count = region_width * region_height
    arr, mcpy_dtype, memcpy_chunk, output_dtype = _memcpy_buffer_for_d2h(
        dtype=dtype,
        chunk_size=chunk_size,
        pe_count=region_pe_count,
    )
    _phase(
        "memcpy_d2h_start",
        step=step_index,
        symbol=symbol,
        x=region_x,
        y=region_y,
        width=region_width,
        height=region_height,
        chunk=memcpy_chunk,
        words=arr.size,
    )
    runner.memcpy_d2h(
        arr,
        sym_id,
        region_x,
        region_y,
        region_width,
        region_height,
        memcpy_chunk,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=mcpy_dtype, nonblock=False,
    )
    _phase("memcpy_d2h_complete", step=step_index, symbol=symbol)
    return (
        symbol,
        path,
        _logical_output_array(
            arr=arr,
            dtype=dtype,
            output_dtype=output_dtype,
        ),
    )


def _phase(name: str, **fields: object) -> None:
    suffix = "".join(f" {key}={value}" for key, value in sorted(fields.items()))
    line = f"phase:{name}{suffix}"
    print(line, flush=True)
    if PHASE_TRACE_PATH is not None:
        PHASE_TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PHASE_TRACE_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def main() -> int:
    global PHASE_TRACE_PATH
    args = parse_args()
    PHASE_TRACE_PATH = Path(args.phase_trace) if args.phase_trace else None
    if PHASE_TRACE_PATH is not None:
        PHASE_TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PHASE_TRACE_PATH.write_text("", encoding="utf-8")
    width = args.width
    height = args.height
    chunk_size = args.chunk_size
    pe_count = width * height

    cmaddr = args.cmaddr.strip() or None
    simfab_numthreads = _simfab_numthreads_from_env()
    runtime_kwargs: dict[str, object] = {"cmaddr": cmaddr}
    if simfab_numthreads is not None:
        runtime_kwargs["simfab_numthreads"] = simfab_numthreads
    runner = SdkRuntime(args.compile_dir, **runtime_kwargs)
    _phase(
        "simfab_config",
        simfabNumthreads=simfab_numthreads if simfab_numthreads is not None else "sdk_default",
    )
    _phase("load_start")
    runner.load()
    _phase("load_complete")
    _phase("run_start")
    runner.run()
    _phase("run_complete")

    batch_steps = _load_batch_steps(args.batch_json)
    if not batch_steps:
        batch_steps = [{"inputs": args.input, "outputs": args.output}]

    for step_index, step in enumerate(batch_steps):
        _phase("step_start", step=step_index)
        inputs = step["inputs"]
        outputs_spec = step["outputs"]
        assert isinstance(inputs, list)
        assert isinstance(outputs_spec, list)

        for spec in inputs:
            symbol, path, dtype, chunk_override, region = parse_io_spec(spec)
            sym_id = runner.get_id(symbol)
            this_chunk = chunk_override if chunk_override is not None else chunk_size
            region_x, region_y, region_width, region_height = _validate_region(
                region=region,
                width=width,
                height=height,
            )
            region_pe_count = region_width * region_height
            arr, mcpy_dtype, memcpy_chunk = _memcpy_payload_for_h2d(
                path=path,
                dtype=dtype,
                chunk_size=this_chunk,
                pe_count=region_pe_count,
            )
            _phase(
                "memcpy_h2d_start",
                step=step_index,
                symbol=symbol,
                x=region_x,
                y=region_y,
                width=region_width,
                height=region_height,
                chunk=memcpy_chunk,
                words=arr.size,
            )
            runner.memcpy_h2d(
                sym_id,
                arr,
                region_x,
                region_y,
                region_width,
                region_height,
                memcpy_chunk,
                streaming=False, order=MemcpyOrder.ROW_MAJOR,
                data_type=mcpy_dtype, nonblock=False,
            )
            _phase("memcpy_h2d_complete", step=step_index, symbol=symbol)

        _phase("launch_start", step=step_index, function=args.launch_fn)
        runner.launch(args.launch_fn, nonblock=False)
        _phase("launch_complete", step=step_index, function=args.launch_fn)

        outputs: list[tuple[str, str, np.ndarray]] = []
        for spec in outputs_spec:
            symbol, path, dtype, chunk_override, region = parse_io_spec(spec)
            this_chunk = chunk_override if chunk_override is not None else chunk_size
            region_tuple = _validate_region(
                region=region,
                width=width,
                height=height,
            )
            outputs.append(
                _copy_d2h_output(
                    runner=runner,
                    symbol=symbol,
                    path=path,
                    dtype=dtype,
                    chunk_size=this_chunk,
                    region=region_tuple,
                    split_rows=args.split_d2h_rows,
                    step_index=step_index,
                )
            )

        _save_outputs(outputs)
        _phase("step_complete", step=step_index)
    _phase("stop_start")
    runner.stop()
    _phase("stop_complete")

    return 0


if __name__ == "__main__":
    sys.exit(main())
