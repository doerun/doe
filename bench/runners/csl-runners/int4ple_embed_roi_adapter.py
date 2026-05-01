#!/usr/bin/env cs_python
"""Execute one chunked INT4 PLE embed launch over sparse PE ROIs."""

from __future__ import annotations

import argparse
import hashlib
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


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_npy_atomic(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("wb") as handle:
        np.save(handle, array)
    tmp_path.replace(path)


def embed_roi_partial_paths(output_path: Path) -> tuple[Path, Path]:
    return (
        output_path.with_name(f"{output_path.name}.partial.npy"),
        output_path.with_name(f"{output_path.name}.partial.json"),
    )


def load_embed_roi_partial(
    *,
    partial_array_path: Path,
    partial_state_path: Path,
    spec_sha256: str,
    token_count: int,
    hidden_size: int,
) -> tuple[np.ndarray | None, list[dict[str, Any]]]:
    if not partial_array_path.exists() and not partial_state_path.exists():
        return None, []
    if not partial_array_path.is_file() or not partial_state_path.is_file():
        raise ValueError("embed_roi_partial_incomplete")
    state = load_json(partial_state_path)
    if state.get("specSha256") != spec_sha256:
        raise ValueError("embed_roi_partial_identity_mismatch")
    if int(state.get("tokenCount") or 0) != token_count:
        raise ValueError("embed_roi_partial_token_count_mismatch")
    if int(state.get("hiddenSize") or 0) != hidden_size:
        raise ValueError("embed_roi_partial_hidden_size_mismatch")
    array = np.load(partial_array_path, allow_pickle=False).astype(
        np.float32,
        copy=False,
    )
    if array.shape != (token_count, hidden_size):
        raise ValueError(
            "embed_roi_partial_shape_mismatch:"
            f"{array.shape}!={(token_count, hidden_size)}"
        )
    completed = [
        item
        for item in state.get("completedSublaunches") or []
        if isinstance(item, dict)
    ]
    return array, completed


def write_embed_roi_partial(
    *,
    partial_array_path: Path,
    partial_state_path: Path,
    compact: np.ndarray,
    spec_sha256: str,
    token_count: int,
    hidden_size: int,
    completed_sublaunches: list[dict[str, Any]],
) -> None:
    write_npy_atomic(partial_array_path, compact)
    write_json_atomic(
        partial_state_path,
        {
            "schemaVersion": 1,
            "artifactKind": "int4ple_embed_roi_partial_checkpoint",
            "specSha256": spec_sha256,
            "tokenCount": token_count,
            "hiddenSize": hidden_size,
            "completedSublaunches": completed_sublaunches,
        },
    )


def embed_roi_input_buffers(spec: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = spec.get("prompt") or {}
    records: list[dict[str, Any]] = []
    if isinstance(prompt, dict):
        records.append(
            {
                "name": "prompt",
                "role": "prompt_tokens",
                "path": str(prompt.get("path") or ""),
                "dtype": "u32",
                "totalElements": int(prompt.get("tokenCount") or 0),
                "sha256": str(prompt.get("sha256") or ""),
                "sha256Kind": "raw_file_bytes",
            }
        )
    tile_inputs = []
    for sublaunch_index, sublaunch in enumerate(spec.get("sublaunches") or []):
        if not isinstance(sublaunch, dict):
            continue
        for pe in sublaunch.get("peTables") or []:
            if not isinstance(pe, dict):
                continue
            indices = pe.get("indices") or {}
            table = pe.get("table") or {}
            if not isinstance(indices, dict) or not isinstance(table, dict):
                continue
            tile_inputs.append(
                {
                    "sublaunchIndex": sublaunch_index,
                    "x": int(pe.get("x") or 0),
                    "y": int(pe.get("y") or 0),
                    "indicesSha256": str(indices.get("sha256") or ""),
                    "tableSha256": str(table.get("sha256") or ""),
                }
            )
    records.append(
        {
            "name": "embed_roi_materialized_inputs",
            "role": "weights_and_indices",
            "totalElements": len(tile_inputs),
            "sha256": sha256_json(tile_inputs),
            "sha256Kind": "sha256_json_tile_input_list",
        }
    )
    return records


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


def load_array(path: Path, dtype: Any, expected_size: int) -> np.ndarray:
    array = np.load(path, allow_pickle=False).astype(dtype, copy=False).ravel()
    if array.size != expected_size:
        raise ValueError(f"array size mismatch for {path}: {array.size}!={expected_size}")
    return array


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec)
    receipt_path = Path(args.receipt_out)
    progress_path = Path(args.progress_out) if args.progress_out else None
    spec = load_json(spec_path)
    blockers: list[str] = []
    launch_index = int(spec.get("launchIndex") or 0)
    symbols = spec.get("symbols") or {}
    params = spec.get("compileParams") or {}
    output = spec.get("output") or {}
    token_count = int((spec.get("prompt") or {}).get("tokenCount") or 0)
    hidden_size = int(params.get("hiddenSize") or 0)
    hidden_per_pe = int(params.get("hiddenPerPe") or 0)
    rows_per_pe = int(params.get("rowsPerPe") or 0)
    tokens_per_chunk = int(params.get("tokensPerChunk") or 0)
    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "int4ple_embed_roi_launch_receipt",
        "status": "blocked",
        "compileDir": str(spec.get("compileDir") or ""),
        "launchFunction": str(spec.get("launchFunction") or "compute"),
        "launchIndex": launch_index,
        "blockers": blockers,
        "inputBuffers": embed_roi_input_buffers(spec),
        "sublaunchCount": len(spec.get("sublaunches") or []),
        "output": output,
    }

    compile_dir = Path(str(spec.get("compileDir") or ""))
    if not compile_dir.is_dir():
        blockers.append(f"compile_dir_missing:{compile_dir}")
        write_json(receipt_path, receipt)
        return 1
    if min(token_count, hidden_size, hidden_per_pe, rows_per_pe, tokens_per_chunk) <= 0:
        blockers.append("embed_roi_shape_incomplete")
        write_json(receipt_path, receipt)
        return 1

    output_path = Path(str(output.get("path") or ""))
    partial_array_path, partial_state_path = embed_roi_partial_paths(output_path)
    spec_sha256 = sha256_json(spec)
    runner = None
    completed_sublaunches: list[dict[str, Any]] = []
    completed_indices: set[int] = set()
    try:
        compact = np.zeros((token_count, hidden_size), dtype=np.float32)
        partial, completed_sublaunches = load_embed_roi_partial(
            partial_array_path=partial_array_path,
            partial_state_path=partial_state_path,
            spec_sha256=spec_sha256,
            token_count=token_count,
            hidden_size=hidden_size,
        )
        if partial is not None:
            compact = partial
            completed_indices = {
                int(item.get("sublaunchIndex") or 0)
                for item in completed_sublaunches
            }
            append_progress(
                progress_path,
                "embed_roi_partial_resume",
                launchIndex=launch_index,
                completedSublaunchCount=len(completed_indices),
            )
        receipt["partialCheckpoint"] = {
            "arrayPath": str(partial_array_path),
            "statePath": str(partial_state_path),
            "completedSublaunchCount": len(completed_indices),
            "specSha256": spec_sha256,
        }
        if len(completed_indices) == len(spec.get("sublaunches") or []):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(output_path, compact)
            receipt["completedSublaunches"] = completed_sublaunches
            receipt["output"]["sha256"] = hashlib.sha256(
                compact.tobytes(order="C")
            ).hexdigest()
            receipt["output"]["sha256Kind"] = "array_tobytes_c_order"
            receipt["status"] = "succeeded"
            partial_array_path.unlink(missing_ok=True)
            partial_state_path.unlink(missing_ok=True)
            write_json(receipt_path, receipt)
            append_progress(progress_path, "embed_roi_done", launchIndex=launch_index)
            print("phase:done", flush=True)
            return 0
        append_progress(progress_path, "embed_roi_constructor", launchIndex=launch_index)
        print("phase:constructor", flush=True)
        runner = SdkRuntime(str(compile_dir), cmaddr=str(spec.get("cmaddr") or "").strip() or None)
        indices_id = int(runner.get_id(str(symbols.get("indices") or "indices")))
        table_id = int(runner.get_id(str(symbols.get("table") or "table")))
        output_id = int(runner.get_id(str(symbols.get("output") or "output")))
        append_progress(progress_path, "embed_roi_load", launchIndex=launch_index)
        print("phase:load", flush=True)
        runner.load()
        append_progress(progress_path, "embed_roi_run", launchIndex=launch_index)
        print("phase:run", flush=True)
        runner.run()
        for sublaunch_index, sublaunch in enumerate(spec.get("sublaunches") or []):
            if sublaunch_index in completed_indices:
                append_progress(
                    progress_path,
                    "embed_roi_sublaunch_reused",
                    launchIndex=launch_index,
                    sublaunchIndex=sublaunch_index,
                )
                continue
            token_start = int(sublaunch.get("tokenStart") or 0)
            token_chunk_count = int(sublaunch.get("tokenCount") or 0)
            hidden_offset = int(sublaunch.get("hiddenOffset") or 0)
            pe_tables = [
                item
                for item in sublaunch.get("peTables") or []
                if isinstance(item, dict)
            ]
            append_progress(
                progress_path,
                "embed_roi_sublaunch_start",
                launchIndex=launch_index,
                sublaunchIndex=sublaunch_index,
                tokenStart=token_start,
                hiddenOffset=hidden_offset,
                activePeCount=len(pe_tables),
            )
            for pe in pe_tables:
                table_info = pe.get("table") or {}
                indices_info = pe.get("indices") or {}
                indices = load_array(
                    Path(str(indices_info.get("path") or "")),
                    np.uint32,
                    tokens_per_chunk,
                )
                table = load_array(
                    Path(str(table_info.get("path") or "")),
                    np.float32,
                    rows_per_pe * hidden_per_pe,
                )
                x = int(pe.get("x") or 0)
                y = int(pe.get("y") or 0)
                runner.memcpy_h2d(
                    indices_id,
                    indices,
                    x,
                    y,
                    1,
                    1,
                    tokens_per_chunk,
                    streaming=False,
                    order=MemcpyOrder.ROW_MAJOR,
                    data_type=MemcpyDataType.MEMCPY_32BIT,
                    nonblock=False,
                )
                runner.memcpy_h2d(
                    table_id,
                    table,
                    x,
                    y,
                    1,
                    1,
                    rows_per_pe * hidden_per_pe,
                    streaming=False,
                    order=MemcpyOrder.ROW_MAJOR,
                    data_type=MemcpyDataType.MEMCPY_32BIT,
                    nonblock=False,
                )
            append_progress(
                progress_path,
                "embed_roi_launch",
                launchIndex=launch_index,
                sublaunchIndex=sublaunch_index,
            )
            runner.launch(str(spec.get("launchFunction") or "compute"), nonblock=False)
            for pe in pe_tables:
                x = int(pe.get("x") or 0)
                y = int(pe.get("y") or 0)
                host = np.zeros(tokens_per_chunk * hidden_per_pe, dtype=np.float32)
                runner.memcpy_d2h(
                    host,
                    output_id,
                    x,
                    y,
                    1,
                    1,
                    tokens_per_chunk * hidden_per_pe,
                    streaming=False,
                    order=MemcpyOrder.ROW_MAJOR,
                    data_type=MemcpyDataType.MEMCPY_32BIT,
                    nonblock=False,
                )
                for owned in pe.get("ownedTokenRows") or []:
                    if not isinstance(owned, dict):
                        continue
                    global_token_index = int(owned.get("globalTokenIndex") or 0)
                    local_token_index = int(owned.get("localTokenIndex") or 0)
                    if global_token_index < token_start:
                        continue
                    if global_token_index >= token_start + token_chunk_count:
                        continue
                    source_start = local_token_index * hidden_per_pe
                    source_end = source_start + int(sublaunch.get("hiddenCount") or 0)
                    dest_end = hidden_offset + int(sublaunch.get("hiddenCount") or 0)
                    compact[global_token_index, hidden_offset:dest_end] = host[
                        source_start:source_end
                    ]
            completed_sublaunches.append(
                {
                    "sublaunchIndex": sublaunch_index,
                    "tokenStart": token_start,
                    "tokenCount": token_chunk_count,
                    "hiddenOffset": hidden_offset,
                    "activePeCount": len(pe_tables),
                }
            )
            append_progress(
                progress_path,
                "embed_roi_sublaunch_complete",
                launchIndex=launch_index,
                sublaunchIndex=sublaunch_index,
            )
            write_embed_roi_partial(
                partial_array_path=partial_array_path,
                partial_state_path=partial_state_path,
                compact=compact,
                spec_sha256=spec_sha256,
                token_count=token_count,
                hidden_size=hidden_size,
                completed_sublaunches=completed_sublaunches,
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(output_path, compact)
        receipt["completedSublaunches"] = completed_sublaunches
        receipt["output"]["sha256"] = hashlib.sha256(compact.tobytes(order="C")).hexdigest()
        receipt["output"]["sha256Kind"] = "array_tobytes_c_order"
        partial_array_path.unlink(missing_ok=True)
        partial_state_path.unlink(missing_ok=True)
    except Exception as exc:  # pragma: no cover - SDK subprocess evidence
        blockers.append(f"embed_roi_failed:{type(exc).__name__}:{str(exc)[:200]}")
    finally:
        if runner is not None:
            try:
                append_progress(progress_path, "embed_roi_stop", launchIndex=launch_index)
                runner.stop()
            except Exception:
                pass

    receipt["status"] = "succeeded" if not blockers else "blocked"
    write_json(receipt_path, receipt)
    if blockers:
        print(f"FAIL:{'; '.join(blockers)}", file=sys.stderr, flush=True)
    else:
        append_progress(progress_path, "embed_roi_done", launchIndex=launch_index)
        print("phase:done", flush=True)
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
