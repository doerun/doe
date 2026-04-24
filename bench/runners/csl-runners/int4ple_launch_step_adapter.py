#!/usr/bin/env cs_python
"""Execute one INT4 PLE HostPlan launch in a fresh SDK process."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    MemcpyDataType,
    MemcpyOrder,
    SdkRuntime,
)


DTYPE_MAP = {
    "f32": (np.float32, MemcpyDataType.MEMCPY_32BIT),
    "u32": (np.uint32, MemcpyDataType.MEMCPY_32BIT),
    "f16": (np.uint16, MemcpyDataType.MEMCPY_16BIT),
    "u16": (np.uint16, MemcpyDataType.MEMCPY_16BIT),
}


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


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec)
    receipt_path = Path(args.receipt_out)
    progress_path = Path(args.progress_out) if args.progress_out else None
    spec = load_json(spec_path)
    blockers: list[str] = []
    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "int4ple_launch_step_receipt",
        "status": "blocked",
        "compileDir": str(spec.get("compileDir") or ""),
        "launchFunction": str(spec.get("launchFunction") or "compute"),
        "launchIndex": int(spec.get("launchIndex") or 0),
        "blockers": blockers,
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
            host = _load_array(path, dtype, total_elements)
            _, memcpy_dtype = _dtype_config(dtype)
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
                elements_per_pe,
                streaming=False,
                order=MemcpyOrder.ROW_MAJOR,
                data_type=memcpy_dtype,
                nonblock=False,
            )
        if blockers:
            raise ValueError("; ".join(blockers))
        append_progress(progress_path, "launch_step_launch", launchIndex=launch_index)
        print("phase:launch", flush=True)
        runner.launch(str(spec.get("launchFunction") or "compute"), nonblock=False)
        outputs: list[dict[str, Any]] = []
        for item in spec.get("outputs") or []:
            if not isinstance(item, dict):
                blockers.append("output_spec_not_object")
                continue
            symbol = str(item.get("symbol") or "")
            dtype = str(item.get("dtype") or "")
            path = Path(str(item.get("path") or ""))
            elements_per_pe = int(item.get("elementsPerPe") or 0)
            total_elements = width * height * elements_per_pe
            if not symbol or not dtype or not path:
                blockers.append(f"output_spec_incomplete:{symbol or 'missing_symbol'}")
                continue
            np_dtype, memcpy_dtype = _dtype_config(dtype)
            host = np.zeros(total_elements, dtype=np_dtype)
            append_progress(
                progress_path,
                "launch_step_memcpy_d2h",
                launchIndex=launch_index,
                symbol=symbol,
                elements=total_elements,
            )
            print(f"phase:memcpy_d2h:{symbol}", flush=True)
            runner.memcpy_d2h(
                host,
                int(runner.get_id(symbol)),
                0,
                0,
                width,
                height,
                elements_per_pe,
                streaming=False,
                order=MemcpyOrder.ROW_MAJOR,
                data_type=memcpy_dtype,
                nonblock=False,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, host)
            outputs.append(
                {
                    "symbol": symbol,
                    "dtype": dtype,
                    "path": str(path),
                    "elementsPerPe": elements_per_pe,
                    "totalElements": total_elements,
                }
            )
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
