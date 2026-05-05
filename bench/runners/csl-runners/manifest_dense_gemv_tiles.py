"""Dense-GEMV tile dispatch support for manifest per-kernel evidence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Callable


MEMCPY_FABRIC_WEST_RESERVED = 4
MEMCPY_FABRIC_EAST_RESERVED = 3
MEMCPY_FABRIC_NORTH_RESERVED = 1
MEMCPY_FABRIC_SOUTH_RESERVED = 1
COMPILE_COMMAND_SHAPE_VERSION = 1
DEFAULT_SPLIT_D2H_ROW_TILE_HEIGHT = 1

# Empirical SDK 2.10 / simfabric D2H descriptor element-count cliff. A single
# tile dispatch whose total output element count (width * height *
# out_dim_per_pe) reaches 2^16 stalls at memcpy_d2h_start with
# totalOutputBytes=0 and lastPhaseReached='memcpy_d2h_start'. Below the cliff,
# the same kernel produces a real partial.npy. Empirically: width=120,
# height=1, out_dim_per_pe=512 (61,440 elements) lands; width=128, height=1
# (65,536) stalls. Hardware/cmaddr path may have different limits; this guard
# is for simfabric only and may be tightened or relaxed once the governed
# width/height sweep records canonical receipts at this boundary.
SDK_D2H_ELEMENT_COUNT_LIMIT = 65536


def _batch_step_groups(
    pending: list[dict[str, Any]],
    step_budget: int,
) -> list[list[dict[str, Any]]]:
    if step_budget <= 0:
        return [pending]
    return [
        pending[start : start + step_budget]
        for start in range(0, len(pending), step_budget)
    ]


def _batch_step_completed(phase_events: list[dict[str, str]]) -> bool:
    return any(event.get("phase") == "step_complete" for event in phase_events)


def _batch_group_dir_name(
    batch_group_index: int,
    batch_pending: list[dict[str, Any]],
) -> str:
    first = batch_pending[0]
    last = batch_pending[-1]
    return (
        f"g{batch_group_index:04d}"
        f"_x{int(first['widthStart']):04d}_w{int(first['width']):04d}"
        f"_y{int(first['rowStart']):04d}_y{int(last['rowStart']):04d}"
    )


def _tile_y_range_dict(
    tile_y_range: tuple[int, int] | None,
) -> dict[str, int] | None:
    if tile_y_range is None:
        return None
    start, end = tile_y_range
    return {"start": int(start), "endExclusive": int(end)}


def _filter_tiles_by_y_range(
    planned_tiles: list[dict[str, int]],
    tile_y_range: tuple[int, int] | None,
) -> list[dict[str, int]]:
    if tile_y_range is None:
        return planned_tiles
    start, end = tile_y_range
    return [
        tile for tile in planned_tiles
        if start <= int(tile["rowStart"]) < end
    ]


def is_safe_tile_shape(
    *,
    width: int,
    height: int,
    out_dim_per_pe: int,
    limit: int = SDK_D2H_ELEMENT_COUNT_LIMIT,
) -> bool:
    """Return True if a single dispatch of this tile shape stays strictly
    under the simfabric D2H element-count cliff.
    """
    if width < 1 or height < 1 or out_dim_per_pe < 1:
        return False
    return width * height * out_dim_per_pe < limit


def max_safe_tile_width(
    *,
    height: int,
    out_dim_per_pe: int,
    limit: int = SDK_D2H_ELEMENT_COUNT_LIMIT,
) -> int:
    """Largest tile width whose shape (width * height * out_dim_per_pe) stays
    strictly under the simfabric D2H element-count cliff. Returns 0 when no
    width is safe (e.g. height * out_dim_per_pe alone exceeds the limit).
    """
    if height < 1 or out_dim_per_pe < 1:
        return 0
    per_unit = height * out_dim_per_pe
    if per_unit >= limit:
        return 0
    return (limit - 1) // per_unit


def _tile_shape_safety(
    *,
    width: int,
    height: int,
    out_dim_per_pe: int,
    split_d2h_rows: bool = False,
    limit: int = SDK_D2H_ELEMENT_COUNT_LIMIT,
) -> dict[str, Any]:
    d2h_copy_height = 1 if split_d2h_rows and height > 1 else height
    return {
        "kind": "simfabric_d2h_element_count_limit",
        "width": width,
        "height": height,
        "splitD2HRows": split_d2h_rows,
        "d2hCopyHeight": d2h_copy_height,
        "outDimPerPe": out_dim_per_pe,
        "outputElements": width * height * out_dim_per_pe,
        "d2hElementsPerCopy": width * d2h_copy_height * out_dim_per_pe,
        "limit": limit,
        "safe": is_safe_tile_shape(
            width=width,
            height=d2h_copy_height,
            out_dim_per_pe=out_dim_per_pe,
            limit=limit,
        ),
        "maxSafeWidth": max_safe_tile_width(
            height=d2h_copy_height,
            out_dim_per_pe=out_dim_per_pe,
            limit=limit,
        ),
    }


def _blocked_tile_run(
    *,
    output_records: list[dict[str, Any]],
    dispatch_mode: str,
    blocker: str,
    tile_compile: dict[str, Any],
    tile_coverage: dict[str, Any] | None,
    weight_input_scope: str,
    weight_residency_mode: str,
) -> DenseGemvTileRun:
    return DenseGemvTileRun(
        output_records=output_records,
        dispatch_command=[dispatch_mode],
        dispatch_exit_code=None,
        dispatch_stdout="",
        dispatch_stderr=blocker,
        dispatch_timed_out=False,
        dispatch_wallclock_ns=0,
        blocker=blocker,
        dispatch_mode=dispatch_mode,
        tile_compile=tile_compile,
        tile_dispatches=[],
        tile_coverage=tile_coverage,
        weight_input_scope=weight_input_scope,
        weight_residency_mode=weight_residency_mode,
    )


DEFAULT_CSL_SDK_ROOTS: tuple[Path, ...] = (
    Path("/home/x/cerebras-sdk"),
    Path("/home/x/cerebras-sdk-2.10.0"),
)
_PHASE_LINE_RE = re.compile(r"^phase:([^\s]+)(?:\s+(.*))?$")


DispatchFn = Callable[..., tuple[int, str, str, bool]]


def _tile_dispatch_key(entry: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(entry.get("widthStart") or 0),
        int(entry.get("rowStart") or 0),
        int(entry.get("width") or 0),
        int(entry.get("rowCount") or entry.get("tileHeight") or 0),
    )


@dataclass(frozen=True)
class DenseGemvTileRun:
    output_records: list[dict[str, Any]]
    dispatch_command: list[str]
    dispatch_exit_code: int | None
    dispatch_stdout: str
    dispatch_stderr: str
    dispatch_timed_out: bool
    dispatch_wallclock_ns: int
    blocker: str | None
    dispatch_mode: str
    tile_compile: dict[str, Any]
    tile_dispatches: list[dict[str, Any]]
    tile_coverage: dict[str, Any] | None = None
    weight_input_scope: str = ""
    weight_residency_mode: str = ""


def discover_cslc(explicit: Path | None = None) -> Path | None:
    if explicit is not None and explicit.is_file():
        return explicit
    raw_env = os.environ.get("DOE_CSLC", "").strip()
    if raw_env:
        candidate = Path(raw_env)
        if candidate.is_file():
            return candidate
    for root in DEFAULT_CSL_SDK_ROOTS:
        candidate = root / "cslc"
        if candidate.is_file():
            return candidate
    found = shutil.which("cslc")
    return Path(found) if found else None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tail(text: str, lines: int = 20) -> list[str]:
    return text.splitlines()[-lines:] if text else []


def _stable_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tile_partial_receipt_path(partial_path: Path) -> Path:
    return partial_path.with_name(f"{partial_path.stem}.tile-receipt.json")


def _tile_partial_receipt_count(tile_root: Path) -> int:
    if not tile_root.is_dir():
        return 0
    return sum(1 for _ in tile_root.rglob("partial.tile-receipt.json"))


def _tile_partial_artifact_counts(
    *,
    tile_root: Path,
    accepted_count: int,
    reused_count: int,
) -> dict[str, int]:
    receipts_on_disk = _tile_partial_receipt_count(tile_root)
    fresh_count = max(0, accepted_count - reused_count)
    return {
        "tilePartialReceiptsOnDisk": receipts_on_disk,
        "verifiedReusablePartials": reused_count,
        "verifiedFreshEmitterPartials": fresh_count,
        "verifiedAcceptedPartials": accepted_count,
        "uncheckedOrStaleTilePartialReceiptsOnDisk": max(
            0,
            receipts_on_disk - accepted_count,
        ),
    }


def _tile_partial_receipt_payload(
    *,
    command: list[str],
    activation: dict[str, Any],
    weight: dict[str, Any],
    output: dict[str, Any],
    compile_receipt: dict[str, Any],
    tile_shape_safety: dict[str, Any],
    width_start: int,
    width_count: int,
    row_start: int,
    row_count: int,
    worker_id: str = "",
    receipt_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schemaVersion": 1,
        "artifactKind": "doe_dense_gemv_width_tile_partial_receipt",
        "commandDigest": _stable_digest(command),
        "activationSha256": str(activation.get("sha256") or ""),
        "weightSha256": str(weight.get("sha256") or ""),
        "outputSha256": str(output.get("sha256") or ""),
        "outputBytes": int(output.get("totalBytes") or 0),
        "compileParamDigest": str(compile_receipt.get("compileParamDigest") or ""),
        "compileCommandDigest": str(compile_receipt.get("commandDigest") or ""),
        "tileShapeSafety": tile_shape_safety,
        "widthStart": width_start,
        "width": width_count,
        "rowStart": row_start,
        "rowCount": row_count,
    }
    if worker_id:
        payload["workerId"] = worker_id
    if receipt_identity:
        payload["receiptIdentity"] = receipt_identity
    return payload


def _load_verified_tile_partial(
    *,
    partial_path: Path,
    command: list[str],
    activation: dict[str, Any],
    weight: dict[str, Any],
    compile_receipt: dict[str, Any],
    tile_shape_safety: dict[str, Any],
    width_start: int,
    width_count: int,
    row_start: int,
    row_count: int,
    receipt_identity: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    receipt_path = _tile_partial_receipt_path(partial_path)
    if not partial_path.is_file() or not receipt_path.is_file():
        return None
    output = {
        "path": str(partial_path),
        "totalBytes": partial_path.stat().st_size,
        "sha256": sha256_file(partial_path),
        "tilePartialReceiptPath": str(receipt_path),
    }
    expected = _tile_partial_receipt_payload(
        command=command,
        activation=activation,
        weight=weight,
        output=output,
        compile_receipt=compile_receipt,
        tile_shape_safety=tile_shape_safety,
        width_start=width_start,
        width_count=width_count,
        row_start=row_start,
        row_count=row_count,
        receipt_identity=receipt_identity,
    )
    try:
        actual = _load_json(receipt_path)
    except (OSError, ValueError):
        return None
    for key, value in expected.items():
        if actual.get(key) != value:
            return None
    return output


def _tile_partial_anchor(
    *,
    entry: dict[str, Any],
    repo_root: Path,
    kind: str,
) -> dict[str, Any] | None:
    if entry.get("exitCode") != 0 or bool(entry.get("timedOut")):
        return None
    output = entry.get("output")
    if not isinstance(output, dict):
        return None
    if int(output.get("totalBytes") or 0) <= 0:
        return None
    receipt_path_raw = output.get("tilePartialReceiptPath")
    receipt_path = (
        repo_root / str(receipt_path_raw)
        if isinstance(receipt_path_raw, str)
        else None
    )
    receipt = {}
    if receipt_path is not None and receipt_path.is_file():
        try:
            receipt = _load_json(receipt_path)
        except (OSError, ValueError):
            receipt = {}
    return {
        "kind": kind,
        "tileIndex": int(entry.get("tileIndex") or 0),
        "widthStart": int(entry.get("widthStart") or 0),
        "width": int(entry.get("width") or 0),
        "rowStart": int(entry.get("rowStart") or 0),
        "rowCount": int(entry.get("rowCount") or 0),
        "reusedVerifiedPartial": bool(entry.get("reusedVerifiedPartial")),
        "output": output,
        "phaseTracePath": str(entry.get("phaseTracePath") or ""),
        "commandDigest": str(receipt.get("commandDigest") or ""),
        "compileParamDigest": str(receipt.get("compileParamDigest") or ""),
        "compileCommandDigest": str(receipt.get("compileCommandDigest") or ""),
        "tileShapeSafety": entry.get("tileShapeSafety") or {},
    }


def _first_current_emitter_partial(
    *,
    tile_dispatches: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any] | None:
    for entry in tile_dispatches:
        anchor = _tile_partial_anchor(
            entry=entry,
            repo_root=repo_root,
            kind="first_verified_current_emitter_tile_partial",
        )
        if anchor is not None:
            return anchor
    return None


def _first_fresh_emitter_partial(
    *,
    tile_dispatches: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any] | None:
    for entry in tile_dispatches:
        if bool(entry.get("reusedVerifiedPartial")):
            continue
        anchor = _tile_partial_anchor(
            entry=entry,
            repo_root=repo_root,
            kind="first_fresh_emitter_partial",
        )
        if anchor is not None:
            return anchor
    return None


def _write_tile_partial_receipt(
    *,
    partial_path: Path,
    command: list[str],
    activation: dict[str, Any],
    weight: dict[str, Any],
    output: dict[str, Any],
    compile_receipt: dict[str, Any],
    tile_shape_safety: dict[str, Any],
    width_start: int,
    width_count: int,
    row_start: int,
    row_count: int,
    worker_id: str = "",
    receipt_identity: dict[str, Any] | None = None,
) -> None:
    receipt_path = _tile_partial_receipt_path(partial_path)
    receipt_path.write_text(
        _json_dumps(
            _tile_partial_receipt_payload(
                command=command,
                activation=activation,
                weight=weight,
                output=output,
                compile_receipt=compile_receipt,
                tile_shape_safety=tile_shape_safety,
                width_start=width_start,
                width_count=width_count,
                row_start=row_start,
                row_count=row_count,
                worker_id=worker_id,
                receipt_identity=receipt_identity,
            )
        ),
        encoding="utf-8",
    )


def _parse_phase_events(text: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for line in text.splitlines():
        match = _PHASE_LINE_RE.match(line.strip())
        if match is None:
            continue
        event = {"phase": match.group(1)}
        raw_fields = match.group(2) or ""
        for token in raw_fields.split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            event[key] = value
        events.append(event)
    return events


def _last_phase(phase_events: list[dict[str, str]]) -> str:
    if not phase_events:
        return ""
    return str(phase_events[-1].get("phase") or "")


def _phase_events_for_batch_step(
    phase_events: list[dict[str, str]],
    step_index: int,
) -> list[dict[str, str]]:
    step_key = str(step_index)
    filtered = [
        event
        for event in phase_events
        if str(event.get("step") or "") == step_key
    ]
    return filtered if filtered else phase_events


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root))
    except ValueError:
        return str(path)


def _compile_command(
    *,
    cslc: Path,
    layout_path: Path,
    output_dir: Path,
    width: int,
    height: int,
    out_dim_per_pe: int,
    in_dim_per_pe: int,
) -> list[str]:
    fabric_width = width + MEMCPY_FABRIC_WEST_RESERVED + MEMCPY_FABRIC_EAST_RESERVED
    fabric_height = height + MEMCPY_FABRIC_NORTH_RESERVED + MEMCPY_FABRIC_SOUTH_RESERVED
    return [
        str(cslc),
        str(layout_path),
        "--arch=wse3",
        f"--fabric-dims={fabric_width},{fabric_height}",
        f"--fabric-offsets={MEMCPY_FABRIC_WEST_RESERVED},{MEMCPY_FABRIC_NORTH_RESERVED}",
        "--channels=1",
        (
            f"--params=width:{width},height:{height},"
            f"out_dim:{height * out_dim_per_pe},"
            f"out_dim_per_pe:{out_dim_per_pe},"
            f"in_dim_per_pe:{in_dim_per_pe}"
        ),
        "-o",
        str(output_dir),
        "--memcpy",
    ]


def _compile_param_digest(
    *,
    source_digest: str,
    width: int,
    tile_height: int,
    out_dim_per_pe: int,
    in_dim_per_pe: int,
) -> str:
    return _stable_digest(
        {
            "shapeVersion": COMPILE_COMMAND_SHAPE_VERSION,
            "arch": "wse3",
            "memcpy": True,
            "width": width,
            "height": tile_height,
            "fabricWidth": (
                width
                + MEMCPY_FABRIC_WEST_RESERVED
                + MEMCPY_FABRIC_EAST_RESERVED
            ),
            "fabricHeight": (
                tile_height
                + MEMCPY_FABRIC_NORTH_RESERVED
                + MEMCPY_FABRIC_SOUTH_RESERVED
            ),
            "fabricOffsetX": MEMCPY_FABRIC_WEST_RESERVED,
            "fabricOffsetY": MEMCPY_FABRIC_NORTH_RESERVED,
            "outDim": tile_height * out_dim_per_pe,
            "outDimPerPe": out_dim_per_pe,
            "inDimPerPe": in_dim_per_pe,
            "sourceDigest": source_digest,
        }
    )


def _run_command(
    command: list[str],
    *,
    timeout_seconds: int,
    cwd: Path | None = None,
) -> tuple[int, str, str, bool]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=None if timeout_seconds <= 0 else timeout_seconds,
            cwd=str(cwd) if cwd is not None else None,
        )
    except subprocess.TimeoutExpired as err:
        return (
            -1,
            (err.stdout or "") if isinstance(err.stdout, str) else "",
            (err.stderr or "") if isinstance(err.stderr, str) else "",
            True,
        )
    return proc.returncode, proc.stdout, proc.stderr, False


def _run_width_tile_dispatch(
    *,
    item: dict[str, Any],
    timeout_seconds: int,
    repo_root: Path,
    dispatcher: DispatchFn | None,
) -> dict[str, Any]:
    started = time.monotonic_ns()
    command = item["command"]
    if dispatcher is None:
        exit_code, stdout, stderr, timed_out = _run_command(
            command,
            timeout_seconds=timeout_seconds,
            cwd=repo_root,
        )
    else:
        exit_code, stdout, stderr, timed_out = dispatcher(
            command,
            timeout_seconds=timeout_seconds,
        )
    return {
        "item": item,
        "exitCode": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "timedOut": timed_out,
        "wallclockNs": time.monotonic_ns() - started,
    }


def _ensure_tile_compile(
    *,
    cslc: Path | None,
    source_dir: Path,
    tile_compile_dir: Path,
    width: int,
    tile_height: int,
    out_dim_per_pe: int,
    in_dim_per_pe: int,
    timeout_seconds: int,
    repo_root: Path,
) -> tuple[dict[str, Any], str | None]:
    layout_path = source_dir / "layout.csl"
    pe_path = source_dir / "pe_program.csl"
    if not layout_path.is_file():
        return (
            {
                "verdict": "blocked",
                "blocker": f"dense_gemv_tile_layout_missing:{layout_path}",
            },
            f"dense_gemv_tile_layout_missing:{layout_path}",
        )
    if not pe_path.is_file():
        return (
            {
                "verdict": "blocked",
                "blocker": f"dense_gemv_tile_pe_program_missing:{pe_path}",
            },
            f"dense_gemv_tile_pe_program_missing:{pe_path}",
        )
    tile_compile_dir.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256()
    source_hash.update(sha256_file(layout_path).encode("ascii"))
    source_hash.update(sha256_file(pe_path).encode("ascii"))
    source_digest = source_hash.hexdigest()
    compile_param_digest = _compile_param_digest(
        source_digest=source_digest,
        width=width,
        tile_height=tile_height,
        out_dim_per_pe=out_dim_per_pe,
        in_dim_per_pe=in_dim_per_pe,
    )
    receipt_path = tile_compile_dir / "dense-gemv-tile-compile.json"
    existing_bin = tile_compile_dir / "bin"
    if existing_bin.is_dir() and receipt_path.is_file():
        try:
            existing = _load_json(receipt_path)
        except (OSError, ValueError):
            existing = {}
        existing_command_digest = existing.get("commandDigest")
        command_digest_matches = (
            cslc is not None
            and existing_command_digest == _stable_digest(
                _compile_command(
                    cslc=cslc,
                    layout_path=layout_path,
                    output_dir=tile_compile_dir,
                    width=width,
                    height=tile_height,
                    out_dim_per_pe=out_dim_per_pe,
                    in_dim_per_pe=in_dim_per_pe,
                )
            )
        )
        if (
            existing.get("sourceDigest") == source_digest
            and existing.get("tileHeight") == tile_height
            and existing.get("width") == width
            and existing.get("outDimPerPe") == out_dim_per_pe
            and existing.get("inDimPerPe") == in_dim_per_pe
            and existing.get("compileParamDigest") == compile_param_digest
            and (cslc is None or command_digest_matches)
            and existing.get("verdict") == "bound"
        ):
            existing["reused"] = True
            return existing, None
    if cslc is None:
        return (
            {
                "verdict": "blocked",
                "blocker": "cslc_unavailable_for_dense_gemv_tile_compile",
                "compileParamDigest": compile_param_digest,
            },
            "cslc_unavailable_for_dense_gemv_tile_compile",
        )

    command = _compile_command(
        cslc=cslc,
        layout_path=layout_path,
        output_dir=tile_compile_dir,
        width=width,
        height=tile_height,
        out_dim_per_pe=out_dim_per_pe,
        in_dim_per_pe=in_dim_per_pe,
    )
    command_digest = _stable_digest(command)

    started = time.monotonic_ns()
    exit_code, stdout, stderr, timed_out = _run_command(
        command,
        timeout_seconds=timeout_seconds,
        cwd=repo_root,
    )
    elapsed_ns = time.monotonic_ns() - started
    blocker = None
    if timed_out:
        blocker = "dense_gemv_tile_compile_timed_out"
    elif exit_code != 0:
        blocker = f"dense_gemv_tile_compile_exit_code_{exit_code}"
    elif not existing_bin.is_dir():
        blocker = f"dense_gemv_tile_compile_bin_missing:{existing_bin}"
    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_dense_gemv_tile_compile_receipt",
        "sourceDigest": source_hash.hexdigest(),
        "layoutPath": _relative(layout_path, repo_root),
        "peProgramPath": _relative(pe_path, repo_root),
        "compileDir": _relative(tile_compile_dir, repo_root),
        "width": width,
        "tileHeight": tile_height,
        "outDimPerPe": out_dim_per_pe,
        "inDimPerPe": in_dim_per_pe,
        "compileParamDigest": compile_param_digest,
        "command": command,
        "commandDigest": command_digest,
        "exitCode": exit_code,
        "timedOut": timed_out,
        "wallclockNs": elapsed_ns,
        "stdoutTail": _tail(stdout),
        "stderrTail": _tail(stderr),
        "verdict": "blocked" if blocker else "bound",
        "blocker": blocker,
        "reused": False,
    }
    receipt_path.write_text(
        _json_dumps(receipt),
        encoding="utf-8",
    )
    return receipt, blocker


def _load_json(path: Path) -> dict[str, Any]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _dtype_for_elem_type(elem_type: str):
    import numpy as np

    return {
        "f32": np.float32,
        "f16": np.float16,
        "u32": np.uint32,
        "i32": np.int32,
        "u16": np.uint16,
        "i16": np.int16,
        "u8": np.uint8,
        "i8": np.int8,
    }.get(elem_type, np.float32)


def _record_by_symbol(records: list[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
    for record in records:
        if str(record.get("symbol") or "") == symbol:
            return record
    return None


def _materialize_tile_input(
    *,
    source_record: dict[str, Any],
    target_path: Path,
    full_height: int,
    width: int,
    row_start: int,
    tile_height: int,
    repo_root: Path,
    width_start: int = 0,
    width_count: int | None = None,
) -> dict[str, Any]:
    import numpy as np

    source_path = Path(str(source_record.get("absolutePath") or source_record["path"]))
    if not source_path.is_absolute():
        source_path = repo_root / source_path
    chunk = int(source_record["perPeChunk"])
    active_width = width if width_count is None else width_count
    elem_type = str(source_record.get("elemType") or "f32")
    dtype = _dtype_for_elem_type(elem_type)
    source = np.load(source_path, mmap_mode="r")
    tile = source.reshape(full_height, width, chunk)[
        row_start : row_start + tile_height,
        width_start : width_start + active_width,
        :,
    ].reshape(-1)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(target_path, tile.astype(dtype, copy=False))
    return {
        "path": str(target_path),
        "sha256": sha256_file(target_path),
        "totalBytes": target_path.stat().st_size,
        "totalElements": int(tile.size),
        "sourcePath": str(source_path),
        "sourceSha256": str(source_record.get("sha256") or ""),
        "sourceRowStart": row_start,
        "sourceWidthStart": width_start,
        "sourceWidth": active_width,
        "tileHeight": tile_height,
        "perPeChunk": chunk,
        "elemType": elem_type,
    }


def _hash_output_record(output_record: dict[str, Any]) -> None:
    path = Path(str(output_record.get("absolutePath") or output_record["path"]))
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        output_record["totalBytes"] = 0
        output_record["sha256"] = ""
        return
    output_record["totalBytes"] = path.stat().st_size
    output_record["sha256"] = sha256_file(path)


def _dispatch_command(
    *,
    cs_python: Path,
    adapter: Path,
    compile_dir: Path,
    width: int,
    height: int,
    activation_path: Path,
    weight_path: Path,
    output_path: Path,
    in_dim_per_pe: int,
    out_dim_per_pe: int,
    cmaddr: str,
    split_d2h_rows: bool = False,
    phase_trace_path: Path | None = None,
) -> list[str]:
    command = [
        str(cs_python),
        str(adapter),
        "--compile-dir",
        str(compile_dir),
        "--width",
        str(width),
        "--height",
        str(height),
        "--chunk-size",
        str(in_dim_per_pe),
        "--input",
        f"activation:{activation_path}:f16:{in_dim_per_pe}",
        "--input",
        f"weight:{weight_path}:f16:{out_dim_per_pe * in_dim_per_pe}",
        "--output",
        (
            f"output:{output_path}:f32:{out_dim_per_pe}:"
            f"{width - 1},0,1,{height}"
        ),
    ]
    if split_d2h_rows:
        command.append("--split-d2h-rows")
    if phase_trace_path is not None:
        command.extend(["--phase-trace", str(phase_trace_path)])
    if cmaddr:
        command.extend(["--cmaddr", cmaddr])
    return command


def _width_chunks(width: int, hidden_tile_width: int) -> list[tuple[int, int]]:
    tile_width = max(1, min(hidden_tile_width, width))
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < width:
        count = min(tile_width, width - start)
        chunks.append((start, count))
        start += count
    return chunks


def _safe_row_tile_height(
    *,
    width: int,
    out_dim_per_pe: int,
    full_height: int,
    allow_unsafe_tile_shapes: bool,
    split_d2h_rows: bool = False,
    max_row_tile_height: int = 0,
) -> int:
    if allow_unsafe_tile_shapes:
        return max(1, full_height)
    if split_d2h_rows and is_safe_tile_shape(
        width=width,
        height=1,
        out_dim_per_pe=out_dim_per_pe,
    ):
        if max_row_tile_height > 0:
            return max(1, min(full_height, max_row_tile_height))
        return max(1, full_height)
    per_row = width * out_dim_per_pe
    if per_row <= 0:
        return 0
    safe_height = max(
        0,
        min(full_height, (SDK_D2H_ELEMENT_COUNT_LIMIT - 1) // per_row),
    )
    if max_row_tile_height > 0:
        safe_height = min(safe_height, max_row_tile_height)
    return safe_height


def _planned_width_row_tiles(
    *,
    width: int,
    full_height: int,
    hidden_tile_width: int,
    out_dim_per_pe: int,
    allow_unsafe_tile_shapes: bool,
    split_d2h_rows: bool = False,
    max_row_tile_height: int = 0,
) -> list[dict[str, int]]:
    tiles: list[dict[str, int]] = []
    for width_start, width_count in _width_chunks(width, hidden_tile_width):
        row_tile_height = _safe_row_tile_height(
            width=width_count,
            out_dim_per_pe=out_dim_per_pe,
            full_height=full_height,
            allow_unsafe_tile_shapes=allow_unsafe_tile_shapes,
            split_d2h_rows=split_d2h_rows,
            max_row_tile_height=max_row_tile_height,
        )
        if row_tile_height <= 0:
            return []
        for row_start in range(0, full_height, row_tile_height):
            row_count = min(row_tile_height, full_height - row_start)
            tiles.append(
                {
                    "widthStart": width_start,
                    "width": width_count,
                    "rowStart": row_start,
                    "rowCount": row_count,
                    "rowTileHeight": row_tile_height,
                }
            )
    return tiles


def _width_row_tile_shape_summary(
    *,
    planned_tiles: list[dict[str, int]],
    out_dim_per_pe: int,
    split_d2h_rows: bool = False,
) -> dict[str, Any]:
    shape_summaries: dict[tuple[int, int], dict[str, Any]] = {}
    max_safety: dict[str, Any] | None = None
    for tile in planned_tiles:
        width = int(tile["width"])
        row_count = int(tile["rowCount"])
        safety = _tile_shape_safety(
            width=width,
            height=row_count,
            out_dim_per_pe=out_dim_per_pe,
            split_d2h_rows=split_d2h_rows,
        )
        key = (width, row_count)
        shape_summaries[key] = safety
        if max_safety is None or int(safety["outputElements"]) > int(
            max_safety["outputElements"]
        ):
            max_safety = safety
    if max_safety is None:
        return _tile_shape_safety(
            width=0,
            height=0,
            out_dim_per_pe=out_dim_per_pe,
        )
    return {
        **max_safety,
        "safe": all(bool(s["safe"]) for s in shape_summaries.values()),
        "plannedTileShapes": [
            {
                "width": width,
                "height": height,
                "tileShapeSafety": safety,
            }
            for (width, height), safety in sorted(shape_summaries.items())
        ],
    }


def _io_specs_from_command(command: list[str]) -> tuple[list[str], list[str]]:
    inputs: list[str] = []
    outputs: list[str] = []
    index = 0
    while index < len(command):
        token = command[index]
        if token == "--input" and index + 1 < len(command):
            inputs.append(command[index + 1])
            index += 2
            continue
        if token == "--output" and index + 1 < len(command):
            outputs.append(command[index + 1])
            index += 2
            continue
        index += 1
    return inputs, outputs


def _batch_dispatch_command(
    *,
    cs_python: Path,
    adapter: Path,
    compile_dir: Path,
    width: int,
    height: int,
    in_dim_per_pe: int,
    batch_path: Path,
    dummy_output_spec: str,
    cmaddr: str,
    split_d2h_rows: bool = False,
    phase_trace_path: Path | None = None,
) -> list[str]:
    command = [
        str(cs_python),
        str(adapter),
        "--compile-dir",
        str(compile_dir),
        "--width",
        str(width),
        "--height",
        str(height),
        "--chunk-size",
        str(in_dim_per_pe),
        "--output",
        dummy_output_spec,
        "--batch-json",
        str(batch_path),
    ]
    if split_d2h_rows:
        command.append("--split-d2h-rows")
    if phase_trace_path is not None:
        command.extend(["--phase-trace", str(phase_trace_path)])
    if cmaddr:
        command.extend(["--cmaddr", cmaddr])
    return command


def _run_batch_for_pending_tiles(
    *,
    pending: list[dict[str, Any]],
    batch_command: list[str],
    timeout_seconds: int,
    repo_root: Path,
    dispatcher: DispatchFn | None,
) -> tuple[int, str, str, bool, int]:
    started = time.monotonic_ns()
    if dispatcher is None:
        exit_code, stdout, stderr, timed_out = _run_command(
            batch_command,
            timeout_seconds=timeout_seconds,
            cwd=repo_root,
        )
    else:
        exit_code, stdout, stderr, timed_out = dispatcher(
            batch_command,
            timeout_seconds=timeout_seconds,
        )
    return exit_code, stdout, stderr, timed_out, time.monotonic_ns() - started


def _run_dense_gemv_width_tiled_batched(
    *,
    kernel: str,
    compile_root: Path,
    source_root: Path,
    compile_params: dict[str, int],
    activation_record: dict[str, Any],
    weight_record: dict[str, Any],
    output_record: dict[str, Any],
    output_records: list[dict[str, Any]],
    scratch_dir: Path,
    cs_python: Path,
    adapter: Path,
    cmaddr: str,
    timeout_seconds: int,
    repo_root: Path,
    cslc: Path | None,
    hidden_tile_width: int,
    effective_hidden_tile_width: int,
    allow_unsafe_tile_shapes: bool,
    reuse_verified_tile_partials: bool,
    tile_dispatch_budget: int,
    chunks: list[tuple[int, int]],
    planned_tiles: list[dict[str, int]],
    full_expected_tile_count: int,
    tile_shape_safety: dict[str, Any],
    tile_split_d2h_rows: bool,
    max_row_tile_height: int,
    batch_runtime_step_budget: int,
    tile_y_range: tuple[int, int] | None,
    finalize_from_tile_receipts: bool,
    worker_id: str,
    receipt_identity: dict[str, Any] | None,
    dispatcher: DispatchFn | None,
) -> DenseGemvTileRun:
    import numpy as np

    width = int(compile_params["width"])
    full_height = int(compile_params["height"])
    out_dim = int(compile_params["out_dim"])
    out_dim_per_pe = int(compile_params["out_dim_per_pe"])
    in_dim_per_pe = int(compile_params["in_dim_per_pe"])
    compile_receipts: list[dict[str, Any]] = []
    compile_receipts_by_shape: dict[tuple[int, int], dict[str, Any]] = {}
    compile_dirs_by_shape: dict[tuple[int, int], Path] = {}
    pending_by_shape: dict[tuple[int, int], list[dict[str, Any]]] = {}
    commands: list[list[str]] = []
    tile_dispatches: list[dict[str, Any]] = []
    tile_y_range_meta = _tile_y_range_dict(tile_y_range)
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    partial_paths: list[Path] = []
    reused_tile_count = 0
    new_dispatch_count = 0
    aggregate_started = time.monotonic_ns()
    blocker: str | None = None
    budget_exhausted = False
    dispatch_exit_code: int | None = 0
    dispatch_timed_out = False
    aggregate = np.zeros((full_height, out_dim_per_pe), dtype=np.float32)

    for tile in planned_tiles:
        width_start = int(tile["widthStart"])
        width_count = int(tile["width"])
        row_start = int(tile["rowStart"])
        row_count = int(tile["rowCount"])
        shape_key = (width_count, row_count)
        tile_compile_dir = (
            compile_root / f"{kernel}_row_tile_w{width_count}_h{row_count}"
        )
        if shape_key in compile_receipts_by_shape:
            compile_receipt = compile_receipts_by_shape[shape_key]
        else:
            compile_receipt, compile_blocker = _ensure_tile_compile(
                cslc=discover_cslc(cslc),
                source_dir=source_root / kernel,
                tile_compile_dir=tile_compile_dir,
                width=width_count,
                tile_height=row_count,
                out_dim_per_pe=out_dim_per_pe,
                in_dim_per_pe=in_dim_per_pe,
                timeout_seconds=timeout_seconds,
                repo_root=repo_root,
            )
            compile_receipts.append(compile_receipt)
            compile_receipts_by_shape[shape_key] = compile_receipt
            compile_dirs_by_shape[shape_key] = tile_compile_dir
            if compile_blocker is not None:
                blocker = compile_blocker
                dispatch_exit_code = None
                break

        tile_dir = (
            scratch_dir
            / "width-row-tiles"
            / f"x{width_start:04d}_w{width_count:04d}"
            / f"y{row_start:04d}_h{row_count:04d}"
        )
        activation_path = tile_dir / "in" / "activation.npy"
        weight_path = tile_dir / "in" / "weight.npy"
        partial_path = tile_dir / "out" / "partial.npy"
        phase_trace_path = tile_dir / "phase-trace.log"
        activation_tile = _materialize_tile_input(
            source_record=activation_record,
            target_path=activation_path,
            full_height=full_height,
            width=width,
            row_start=row_start,
            tile_height=row_count,
            repo_root=repo_root,
            width_start=width_start,
            width_count=width_count,
        )
        weight_tile = _materialize_tile_input(
            source_record=weight_record,
            target_path=weight_path,
            full_height=full_height,
            width=width,
            row_start=row_start,
            tile_height=row_count,
            repo_root=repo_root,
            width_start=width_start,
            width_count=width_count,
        )
        weight_tile["weightInputScope"] = "hidden_width_slice"
        weight_tile["weightResidencyMode"] = "per_tile_h2d_sliced"
        command = _dispatch_command(
            cs_python=cs_python,
            adapter=adapter,
            compile_dir=tile_compile_dir,
            width=width_count,
            height=row_count,
            activation_path=activation_path,
            weight_path=weight_path,
            output_path=partial_path,
            in_dim_per_pe=in_dim_per_pe,
            out_dim_per_pe=out_dim_per_pe,
            cmaddr=cmaddr,
            split_d2h_rows=tile_split_d2h_rows and row_count > 1,
            phase_trace_path=phase_trace_path,
        )
        tile_safety = _tile_shape_safety(
            width=width_count,
            height=row_count,
            out_dim_per_pe=out_dim_per_pe,
            split_d2h_rows=tile_split_d2h_rows and row_count > 1,
        )
        reused_output = None
        if reuse_verified_tile_partials:
            reused_output = _load_verified_tile_partial(
                partial_path=partial_path,
                command=command,
                activation=activation_tile,
                weight=weight_tile,
                compile_receipt=compile_receipt,
                tile_shape_safety=tile_safety,
                width_start=width_start,
                width_count=width_count,
                row_start=row_start,
                row_count=row_count,
                receipt_identity=receipt_identity,
            )
        if reused_output is not None:
            tile_dispatches.append(
                {
                    "tileIndex": len(tile_dispatches),
                    "widthStart": width_start,
                    "width": width_count,
                    "rowStart": row_start,
                    "rowCount": row_count,
                    "activation": activation_tile,
                    "weight": weight_tile,
                    "output": reused_output,
                    "command": command,
                    "executionMode": "verified_partial_reuse",
                    "tileD2HMode": (
                        "row_split_copyback"
                        if tile_safety.get("splitD2HRows")
                        else "single_region_copyback"
                    ),
                    "exitCode": 0,
                    "timedOut": False,
                    "wallclockNs": 0,
                    "tileShapeSafety": tile_safety,
                    "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
                    "reusedVerifiedPartial": True,
                    "phaseEvents": [],
                    "lastPhaseReached": "verified_partial_reused",
                    "stdoutTail": [],
                    "stderrTail": [],
                }
            )
            aggregate[
                row_start : row_start + row_count,
                :,
            ] += np.load(partial_path).astype(
                np.float32,
                copy=False,
            ).reshape(row_count, out_dim_per_pe)
            partial_paths.append(partial_path)
            reused_tile_count += 1
            continue
        if finalize_from_tile_receipts:
            blocker = "dense_gemv_width_tile_receipts_incomplete"
            dispatch_exit_code = None
            break
        if tile_dispatch_budget > 0 and new_dispatch_count >= tile_dispatch_budget:
            budget_exhausted = True
            break
        partial_path.unlink(missing_ok=True)
        _tile_partial_receipt_path(partial_path).unlink(missing_ok=True)
        inputs, outputs = _io_specs_from_command(command)
        pending_by_shape.setdefault(shape_key, []).append(
            {
                "widthStart": width_start,
                "width": width_count,
                "rowStart": row_start,
                "rowCount": row_count,
                "activation": activation_tile,
                "weight": weight_tile,
                "partialPath": partial_path,
                "command": command,
                "inputs": inputs,
                "outputs": outputs,
                "compileReceipt": compile_receipt,
                "tileShapeSafety": tile_safety,
                "splitD2HRows": tile_split_d2h_rows and row_count > 1,
            }
        )
        new_dispatch_count += 1

    for shape_key, pending in pending_by_shape.items():
        if not pending:
            continue
        width_count, row_count = shape_key
        groups = _batch_step_groups(pending, batch_runtime_step_budget)
        for batch_group_index, batch_pending in enumerate(groups):
            first_outputs = batch_pending[0]["outputs"]
            batch_root = (
                scratch_dir
                / "width-row-batches"
                / f"w{width_count:04d}_h{row_count:04d}"
            )
            if batch_runtime_step_budget > 0:
                batch_dir = batch_root / _batch_group_dir_name(
                    batch_group_index,
                    batch_pending,
                )
            else:
                batch_dir = batch_root
            batch_path = batch_dir / "batch.json"
            batch_phase_trace_path = batch_dir / "phase-trace.log"
            batch_dir.mkdir(parents=True, exist_ok=True)
            batch_tile_range = {
                "widthStart": int(batch_pending[0]["widthStart"]),
                "width": width_count,
                "rowStart": int(batch_pending[0]["rowStart"]),
                "rowEndInclusive": int(batch_pending[-1]["rowStart"]),
            }
            batch_payload = {
                "schemaVersion": 1,
                "artifactKind": "doe_dense_gemv_width_tile_batch",
                "batchGroupIndex": batch_group_index,
                "batchRuntimeStepBudget": batch_runtime_step_budget,
                "batchTileRange": batch_tile_range,
                "steps": [
                    {"inputs": item["inputs"], "outputs": item["outputs"]}
                    for item in batch_pending
                ],
            }
            batch_path.write_text(_json_dumps(batch_payload), encoding="utf-8")
            dummy_output_spec = str(first_outputs[0])
            batch_command = _batch_dispatch_command(
                cs_python=cs_python,
                adapter=adapter,
                compile_dir=compile_dirs_by_shape[shape_key],
                width=width_count,
                height=row_count,
                in_dim_per_pe=in_dim_per_pe,
                batch_path=batch_path,
                dummy_output_spec=dummy_output_spec,
                cmaddr=cmaddr,
                split_d2h_rows=tile_split_d2h_rows and row_count > 1,
                phase_trace_path=batch_phase_trace_path,
            )
            commands.append(batch_command)
            exit_code, stdout, stderr, timed_out, elapsed_ns = (
                _run_batch_for_pending_tiles(
                    pending=batch_pending,
                    batch_command=batch_command,
                    timeout_seconds=timeout_seconds,
                    repo_root=repo_root,
                    dispatcher=dispatcher,
                )
            )
            stdout_parts.extend(_tail(stdout, lines=4))
            stderr_parts.extend(_tail(stderr, lines=4))
            phase_text = stdout
            if batch_phase_trace_path.is_file():
                phase_text = batch_phase_trace_path.read_text(encoding="utf-8")
            phase_events = _parse_phase_events(phase_text)
            batch_blocker: str | None = None
            if timed_out:
                batch_blocker = "dense_gemv_width_tile_batch_dispatch_timed_out"
                blocker = batch_blocker
                dispatch_exit_code = -1
                dispatch_timed_out = True
            elif exit_code != 0:
                batch_blocker = (
                    f"dense_gemv_width_tile_batch_dispatch_exit_code_{exit_code}"
                )
                blocker = batch_blocker
                dispatch_exit_code = exit_code

            for batch_step_index, item in enumerate(batch_pending):
                partial_path = item["partialPath"]
                partial_record = {
                    "path": _relative(partial_path, repo_root),
                    "totalBytes": partial_path.stat().st_size
                    if partial_path.is_file()
                    else 0,
                    "sha256": sha256_file(partial_path)
                    if partial_path.is_file()
                    else "",
                    "tilePartialReceiptPath": _relative(
                        _tile_partial_receipt_path(partial_path),
                        repo_root,
                    ),
                }
                row_start = int(item["rowStart"])
                item_row_count = int(item["rowCount"])
                item_phase_events = _phase_events_for_batch_step(
                    phase_events,
                    batch_step_index,
                )
                step_completed = _batch_step_completed(item_phase_events)
                entry_blocked = False
                if batch_blocker is not None and not step_completed:
                    entry_blocked = True
                if int(partial_record["totalBytes"]) <= 0:
                    if batch_blocker is None or step_completed:
                        blocker = "dense_gemv_width_tile_output_empty"
                        dispatch_exit_code = exit_code
                    entry_blocked = True
                tile_dispatches.append(
                    {
                        "tileIndex": len(tile_dispatches),
                        "widthStart": int(item["widthStart"]),
                        "width": int(item["width"]),
                        "rowStart": row_start,
                        "rowCount": item_row_count,
                        "activation": item["activation"],
                        "weight": item["weight"],
                        "output": partial_record,
                        "command": item["command"],
                        "batchCommand": batch_command,
                        "batchGroupIndex": batch_group_index,
                        "batchStepIndex": batch_step_index,
                        "batchTileRange": batch_tile_range,
                        "workerId": worker_id,
                        "batchPath": _relative(batch_path, repo_root),
                        "phaseTracePath": _relative(
                            batch_phase_trace_path,
                            repo_root,
                        ),
                        "executionMode": "batched_runtime",
                        "tileD2HMode": (
                            "row_split_copyback"
                            if item.get("splitD2HRows")
                            else "single_region_copyback"
                        ),
                        "exitCode": -1 if timed_out else exit_code,
                        "timedOut": timed_out,
                        "wallclockNs": elapsed_ns,
                        "tileShapeSafety": item["tileShapeSafety"],
                        "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
                        "reusedVerifiedPartial": False,
                        "phaseEvents": item_phase_events,
                        "lastPhaseReached": _last_phase(item_phase_events),
                        "stdoutTail": _tail(stdout),
                        "stderrTail": _tail(stderr),
                    }
                )
                if entry_blocked:
                    break
                _write_tile_partial_receipt(
                    partial_path=partial_path,
                    command=item["command"],
                    activation=item["activation"],
                    weight=item["weight"],
                    output=partial_record,
                    compile_receipt=item["compileReceipt"],
                    tile_shape_safety=item["tileShapeSafety"],
                    width_start=int(item["widthStart"]),
                    width_count=int(item["width"]),
                    row_start=row_start,
                    row_count=item_row_count,
                    worker_id=worker_id,
                    receipt_identity=receipt_identity,
                )
                aggregate[
                    row_start : row_start + item_row_count,
                    :,
                ] += np.load(partial_path).astype(
                    np.float32,
                    copy=False,
                ).reshape(item_row_count, out_dim_per_pe)
                partial_paths.append(partial_path)
            if blocker is not None:
                break
        if blocker is not None:
            break

    if blocker is None and budget_exhausted:
        blocker = "dense_gemv_width_tile_dispatch_budget_exhausted"
        dispatch_exit_code = None
    if blocker is None and tile_y_range is not None:
        blocker = "dense_gemv_width_tile_y_range_partial_coverage"
        dispatch_exit_code = None

    if blocker is None:
        logits = aggregate.reshape(-1)[:out_dim].astype(np.float32, copy=False)
        if int(logits.size) != out_dim:
            blocker = "dense_gemv_aggregate_shape_mismatch"
        output_path = Path(
            str(output_record.get("absolutePath") or output_record["path"])
        )
        if not output_path.is_absolute():
            output_path = repo_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
    if blocker is None:
        output_path = Path(
            str(output_record.get("absolutePath") or output_record["path"])
        )
        if not output_path.is_absolute():
            output_path = repo_root / output_path
        np.save(output_path, logits)
        output_record["dispatchMode"] = "dense_gemv_width_tiled"
        output_record["tileHeight"] = 0
        output_record["rowTileHeights"] = sorted(
            {int(tile["rowCount"]) for tile in planned_tiles}
        )
        output_record["requestedHiddenTileWidth"] = hidden_tile_width
        output_record["hiddenTileWidth"] = effective_hidden_tile_width
        output_record["tileCount"] = len(tile_dispatches)
        output_record["aggregatedElements"] = int(logits.size)
        output_record["tileShapeSafety"] = tile_shape_safety
        output_record["unsafeTileShapeAllowed"] = allow_unsafe_tile_shapes
        output_record["tileD2HMode"] = (
            "row_split_copyback"
            if tile_split_d2h_rows
            else "single_region_copyback"
        )
        output_record["reusedTileCount"] = reused_tile_count
        output_record["hostReduction"] = {
            "kind": "sum_hidden_width_tiles",
            "tileCount": len(partial_paths),
            "sourceDtype": "f32",
            "targetDtype": "f32",
            "reductionOrder": "width_start_then_row_start_ascending",
        }
        _hash_output_record(output_record)
        if int(output_record.get("totalBytes") or 0) <= 0:
            blocker = "dense_gemv_aggregate_output_empty"

    aggregate_elapsed_ns = time.monotonic_ns() - aggregate_started
    expected_tile_count = len(planned_tiles)
    partial_artifacts = _tile_partial_artifact_counts(
        tile_root=scratch_dir / "width-row-tiles",
        accepted_count=len(partial_paths),
        reused_count=reused_tile_count,
    )
    first_fresh = _first_fresh_emitter_partial(
        tile_dispatches=tile_dispatches,
        repo_root=repo_root,
    )
    canonical_anchor = _first_current_emitter_partial(
        tile_dispatches=tile_dispatches,
        repo_root=repo_root,
    )
    tile_coverage = {
        "kind": "width_row_tiles",
        "fullWidth": width,
        "fullHeight": full_height,
        "rowTileHeight": 0,
        "rowTileHeights": sorted({int(tile["rowCount"]) for tile in planned_tiles}),
        "requestedHiddenTileWidth": hidden_tile_width,
        "effectiveHiddenTileWidth": effective_hidden_tile_width,
        "tileShapeSafety": tile_shape_safety,
        "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
        "evidenceIntent": (
            "diagnostic_sweep"
            if allow_unsafe_tile_shapes
            else "partial_tile_worker"
            if tile_y_range is not None
            else "claim_eligible_tile_aggregate"
        ),
        "tileYRange": tile_y_range_meta,
        "workerId": worker_id,
        "receiptIdentity": receipt_identity or {},
        "hiddenWidthChunks": [
            {
                "widthStart": start,
                "width": count,
                "maxRowTileHeight": _safe_row_tile_height(
                    width=count,
                    out_dim_per_pe=out_dim_per_pe,
                    full_height=full_height,
                    allow_unsafe_tile_shapes=allow_unsafe_tile_shapes,
                    split_d2h_rows=tile_split_d2h_rows,
                    max_row_tile_height=max_row_tile_height,
                ),
            }
            for start, count in chunks
        ],
        "fullExpectedTileCount": full_expected_tile_count,
        "expectedTileCount": expected_tile_count,
        "completedTileCount": len(partial_paths),
        "reusedTileCount": reused_tile_count,
        "verifiedReusablePartials": partial_artifacts[
            "verifiedReusablePartials"
        ],
        "verifiedFreshEmitterPartials": partial_artifacts[
            "verifiedFreshEmitterPartials"
        ],
        "verifiedAcceptedPartials": partial_artifacts[
            "verifiedAcceptedPartials"
        ],
        "tilePartialReceiptsOnDisk": partial_artifacts[
            "tilePartialReceiptsOnDisk"
        ],
        "partialArtifacts": partial_artifacts,
        "canonicalTilePartialAnchor": canonical_anchor,
        "firstFreshEmitterPartial": first_fresh,
        "dispatchedTileCount": len(tile_dispatches) - reused_tile_count,
        "dispatchBudget": tile_dispatch_budget,
        "batchRuntime": True,
        "batchRuntimeStepBudget": batch_runtime_step_budget,
        "finalizeFromTileReceipts": finalize_from_tile_receipts,
        "tileDispatchJobs": 1,
        "maxRowTileHeight": max_row_tile_height,
        "tileD2HMode": (
            "row_split_copyback"
            if tile_split_d2h_rows
            else "single_region_copyback"
        ),
        "dispatchBudgetExhausted": (
            budget_exhausted
            and blocker == "dense_gemv_width_tile_dispatch_budget_exhausted"
        ),
        "coversFullHiddenWidth": sum(count for _, count in chunks) == width,
        "coversTileYRange": len(partial_paths) == expected_tile_count,
        "coversFullRows": (
            tile_y_range is None and len(partial_paths) == expected_tile_count
        ),
        "covered": blocker is None and len(partial_paths) == expected_tile_count,
    }
    return DenseGemvTileRun(
        output_records=output_records,
        dispatch_command=commands[0] if commands else ["dense_gemv_width_tiled"],
        dispatch_exit_code=dispatch_exit_code,
        dispatch_stdout="\n".join(stdout_parts),
        dispatch_stderr="\n".join(stderr_parts),
        dispatch_timed_out=dispatch_timed_out,
        dispatch_wallclock_ns=aggregate_elapsed_ns,
        blocker=blocker,
        dispatch_mode="dense_gemv_width_tiled",
        tile_compile={
            "mode": "dense_gemv_width_tiled",
            "requestedHiddenTileWidth": hidden_tile_width,
            "effectiveHiddenTileWidth": effective_hidden_tile_width,
            "shapeSafety": tile_shape_safety,
            "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
            "reuseVerifiedTilePartials": reuse_verified_tile_partials,
            "dispatchBudget": tile_dispatch_budget,
            "batchRuntime": True,
            "batchRuntimeStepBudget": batch_runtime_step_budget,
            "finalizeFromTileReceipts": finalize_from_tile_receipts,
            "maxRowTileHeight": max_row_tile_height,
            "tileD2HMode": (
                "row_split_copyback"
                if tile_split_d2h_rows
                else "single_region_copyback"
            ),
            "evidenceIntent": (
                "diagnostic_sweep"
                if allow_unsafe_tile_shapes
                else "partial_tile_worker"
                if tile_y_range is not None
                else "claim_eligible_tile_aggregate"
            ),
            "tileYRange": tile_y_range_meta,
            "workerId": worker_id,
            "receiptIdentity": receipt_identity or {},
            "widthTileCount": len(chunks),
            "batchShapeCount": len(pending_by_shape),
            "receipts": compile_receipts,
        },
        tile_dispatches=tile_dispatches,
        tile_coverage=tile_coverage,
        weight_input_scope="hidden_width_slice",
        weight_residency_mode="per_tile_h2d_sliced",
    )


def _run_dense_gemv_width_tiled(
    *,
    kernel: str,
    compile_root: Path,
    source_root: Path,
    compile_params: dict[str, int],
    activation_record: dict[str, Any],
    weight_record: dict[str, Any],
    output_record: dict[str, Any],
    output_records: list[dict[str, Any]],
    scratch_dir: Path,
    cs_python: Path,
    adapter: Path,
    cmaddr: str,
    timeout_seconds: int,
    repo_root: Path,
    cslc: Path | None,
    hidden_tile_width: int,
    allow_unsafe_tile_shapes: bool,
    reuse_verified_tile_partials: bool,
    tile_dispatch_budget: int,
    tile_dispatch_jobs: int,
    max_row_tile_height: int,
    batch_runtime: bool,
    batch_runtime_step_budget: int,
    tile_y_range: tuple[int, int] | None,
    finalize_from_tile_receipts: bool,
    worker_id: str,
    receipt_identity: dict[str, Any] | None,
    dispatcher: DispatchFn | None,
) -> DenseGemvTileRun:
    import numpy as np

    width = int(compile_params["width"])
    full_height = int(compile_params["height"])
    out_dim = int(compile_params["out_dim"])
    out_dim_per_pe = int(compile_params["out_dim_per_pe"])
    in_dim_per_pe = int(compile_params["in_dim_per_pe"])
    if hidden_tile_width <= 0:
        safety = _tile_shape_safety(
            width=hidden_tile_width,
            height=1,
            out_dim_per_pe=out_dim_per_pe,
        )
        return _blocked_tile_run(
            output_records=output_records,
            dispatch_mode="dense_gemv_width_tiled",
            blocker="dense_gemv_hidden_tile_width_invalid",
            tile_compile={
                "mode": "dense_gemv_width_tiled",
                "requestedHiddenTileWidth": hidden_tile_width,
                "shapeSafety": safety,
            },
            tile_coverage={
                "kind": "width_row_tiles",
                "fullWidth": width,
                "fullHeight": full_height,
                "rowTileHeight": 1,
                "requestedHiddenTileWidth": hidden_tile_width,
                "effectiveHiddenTileWidth": 0,
                "tileShapeSafety": safety,
                "expectedTileCount": 0,
                "completedTileCount": 0,
                "coversFullHiddenWidth": False,
                "coversFullRows": False,
                "covered": False,
            },
            weight_input_scope="hidden_width_slice",
            weight_residency_mode="per_tile_h2d_sliced",
        )
    max_safe_width = max_safe_tile_width(
        height=1,
        out_dim_per_pe=out_dim_per_pe,
    )
    if max_safe_width <= 0 and not allow_unsafe_tile_shapes:
        safety = _tile_shape_safety(
            width=1,
            height=1,
            out_dim_per_pe=out_dim_per_pe,
        )
        return _blocked_tile_run(
            output_records=output_records,
            dispatch_mode="dense_gemv_width_tiled",
            blocker="dense_gemv_tile_shape_exceeds_sdk_d2h_limit",
            tile_compile={
                "mode": "dense_gemv_width_tiled",
                "requestedHiddenTileWidth": hidden_tile_width,
                "effectiveHiddenTileWidth": 0,
                "shapeSafety": safety,
            },
            tile_coverage={
                "kind": "width_row_tiles",
                "fullWidth": width,
                "fullHeight": full_height,
                "rowTileHeight": 1,
                "requestedHiddenTileWidth": hidden_tile_width,
                "effectiveHiddenTileWidth": 0,
                "tileShapeSafety": safety,
                "expectedTileCount": 0,
                "completedTileCount": 0,
                "coversFullHiddenWidth": False,
                "coversFullRows": False,
                "covered": False,
            },
            weight_input_scope="hidden_width_slice",
            weight_residency_mode="per_tile_h2d_sliced",
        )
    effective_hidden_tile_width = (
        hidden_tile_width
        if allow_unsafe_tile_shapes
        else min(hidden_tile_width, max_safe_width)
    )
    tile_split_d2h_rows = (
        not allow_unsafe_tile_shapes and max_row_tile_height != 1
    )
    chunks = _width_chunks(width, effective_hidden_tile_width)
    all_planned_tiles = _planned_width_row_tiles(
        width=width,
        full_height=full_height,
        hidden_tile_width=effective_hidden_tile_width,
        out_dim_per_pe=out_dim_per_pe,
        allow_unsafe_tile_shapes=allow_unsafe_tile_shapes,
        split_d2h_rows=tile_split_d2h_rows,
        max_row_tile_height=max_row_tile_height,
    )
    planned_tiles = _filter_tiles_by_y_range(
        all_planned_tiles,
        tile_y_range,
    )
    tile_shape_safety = _width_row_tile_shape_summary(
        planned_tiles=planned_tiles,
        out_dim_per_pe=out_dim_per_pe,
        split_d2h_rows=tile_split_d2h_rows,
    )
    if not planned_tiles and not allow_unsafe_tile_shapes:
        return _blocked_tile_run(
            output_records=output_records,
            dispatch_mode="dense_gemv_width_tiled",
            blocker="dense_gemv_tile_shape_exceeds_sdk_d2h_limit",
            tile_compile={
                "mode": "dense_gemv_width_tiled",
                "requestedHiddenTileWidth": hidden_tile_width,
                "effectiveHiddenTileWidth": effective_hidden_tile_width,
                "shapeSafety": tile_shape_safety,
            },
            tile_coverage={
                "kind": "width_row_tiles",
                "fullWidth": width,
                "fullHeight": full_height,
                "tileYRange": _tile_y_range_dict(tile_y_range),
                "rowTileHeights": [],
                "requestedHiddenTileWidth": hidden_tile_width,
                "effectiveHiddenTileWidth": effective_hidden_tile_width,
                "tileShapeSafety": tile_shape_safety,
                "expectedTileCount": 0,
                "completedTileCount": 0,
                "coversFullHiddenWidth": False,
                "coversFullRows": False,
                "covered": False,
            },
            weight_input_scope="hidden_width_slice",
            weight_residency_mode="per_tile_h2d_sliced",
        )
    if batch_runtime:
        return _run_dense_gemv_width_tiled_batched(
            kernel=kernel,
            compile_root=compile_root,
            source_root=source_root,
            compile_params=compile_params,
            activation_record=activation_record,
            weight_record=weight_record,
            output_record=output_record,
            output_records=output_records,
            scratch_dir=scratch_dir,
            cs_python=cs_python,
            adapter=adapter,
            cmaddr=cmaddr,
            timeout_seconds=timeout_seconds,
            repo_root=repo_root,
            cslc=cslc,
            hidden_tile_width=hidden_tile_width,
            effective_hidden_tile_width=effective_hidden_tile_width,
            allow_unsafe_tile_shapes=allow_unsafe_tile_shapes,
            reuse_verified_tile_partials=reuse_verified_tile_partials,
            tile_dispatch_budget=tile_dispatch_budget,
            chunks=chunks,
            planned_tiles=planned_tiles,
            full_expected_tile_count=len(all_planned_tiles),
            tile_shape_safety=tile_shape_safety,
            tile_split_d2h_rows=tile_split_d2h_rows,
            max_row_tile_height=max_row_tile_height,
            batch_runtime_step_budget=batch_runtime_step_budget,
            tile_y_range=tile_y_range,
            finalize_from_tile_receipts=finalize_from_tile_receipts,
            worker_id=worker_id,
            receipt_identity=receipt_identity,
            dispatcher=dispatcher,
        )
    compile_receipts: list[dict[str, Any]] = []
    compile_receipts_by_shape: dict[tuple[int, int], dict[str, Any]] = {}
    commands: list[list[str]] = []
    tile_dispatches: list[dict[str, Any]] = []
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    partial_paths: list[Path] = []
    pending_dispatches: list[dict[str, Any]] = []
    reused_tile_count = 0
    new_dispatch_count = 0
    aggregate_started = time.monotonic_ns()
    blocker: str | None = None
    dispatch_exit_code: int | None = 0
    dispatch_timed_out = False
    aggregate = np.zeros((full_height, out_dim_per_pe), dtype=np.float32)
    effective_tile_dispatch_jobs = (
        max(1, int(tile_dispatch_jobs))
        if dispatcher is None
        else 1
    )

    def record_dispatch_result(result: dict[str, Any]) -> str | None:
        nonlocal dispatch_exit_code, dispatch_timed_out
        item = result["item"]
        stdout = str(result["stdout"])
        stderr = str(result["stderr"])
        phase_trace_path = Path(item["phaseTracePath"])
        phase_text = stdout
        if phase_trace_path.is_file():
            phase_text = phase_trace_path.read_text(encoding="utf-8")
        exit_code = int(result["exitCode"])
        timed_out = bool(result["timedOut"])
        elapsed_ns = int(result["wallclockNs"])
        stdout_parts.extend(_tail(stdout, lines=4))
        stderr_parts.extend(_tail(stderr, lines=4))
        phase_events = _parse_phase_events(phase_text)
        partial_path = Path(item["partialPath"])
        partial_record = {
            "path": _relative(partial_path, repo_root),
            "totalBytes": partial_path.stat().st_size
            if partial_path.is_file()
            else 0,
            "sha256": sha256_file(partial_path)
            if partial_path.is_file()
            else "",
            "tilePartialReceiptPath": _relative(
                _tile_partial_receipt_path(partial_path),
                repo_root,
            ),
        }
        width_start = int(item["widthStart"])
        width_count = int(item["width"])
        row_start = int(item["rowStart"])
        row_count = int(item["rowCount"])
        tile_dispatches.append(
            {
                "tileIndex": len(tile_dispatches),
                "widthStart": width_start,
                "width": width_count,
                "rowStart": row_start,
                "rowCount": row_count,
                "activation": item["activation"],
                "weight": item["weight"],
                "output": partial_record,
                "command": item["command"],
                "executionMode": "independent_subprocess",
                "tileDispatchJobs": effective_tile_dispatch_jobs,
                "tileD2HMode": (
                    "row_split_copyback"
                    if item.get("splitD2HRows")
                    else "single_region_copyback"
                ),
                "phaseTracePath": _relative(phase_trace_path, repo_root),
                "exitCode": exit_code,
                "timedOut": timed_out,
                "wallclockNs": elapsed_ns,
                "tileShapeSafety": item["tileShapeSafety"],
                "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
                "reusedVerifiedPartial": False,
                "phaseEvents": phase_events,
                "lastPhaseReached": _last_phase(phase_events),
                "stdoutTail": _tail(stdout),
                "stderrTail": _tail(stderr),
            }
        )
        if timed_out:
            dispatch_exit_code = -1
            dispatch_timed_out = True
            return "dense_gemv_width_tile_dispatch_timed_out"
        if exit_code != 0:
            dispatch_exit_code = exit_code
            return f"dense_gemv_width_tile_dispatch_exit_code_{exit_code}"
        if int(partial_record["totalBytes"]) <= 0:
            dispatch_exit_code = exit_code
            return "dense_gemv_width_tile_output_empty"

        _write_tile_partial_receipt(
            partial_path=partial_path,
            command=item["command"],
            activation=item["activation"],
            weight=item["weight"],
            output=partial_record,
            compile_receipt=item["compileReceipt"],
            tile_shape_safety=item["tileShapeSafety"],
            width_start=width_start,
            width_count=width_count,
            row_start=row_start,
            row_count=row_count,
            receipt_identity=receipt_identity,
        )
        aggregate[
            row_start : row_start + row_count,
            :,
        ] += np.load(partial_path).astype(
            np.float32,
            copy=False,
        ).reshape(row_count, out_dim_per_pe)
        partial_paths.append(partial_path)
        return None

    for tile in planned_tiles:
        width_start = int(tile["widthStart"])
        width_count = int(tile["width"])
        row_start = int(tile["rowStart"])
        row_count = int(tile["rowCount"])
        shape_key = (width_count, row_count)
        tile_compile_dir = (
            compile_root / f"{kernel}_row_tile_w{width_count}_h{row_count}"
        )
        if shape_key in compile_receipts_by_shape:
            compile_receipt = compile_receipts_by_shape[shape_key]
        else:
            compile_receipt, compile_blocker = _ensure_tile_compile(
                cslc=discover_cslc(cslc),
                source_dir=source_root / kernel,
                tile_compile_dir=tile_compile_dir,
                width=width_count,
                tile_height=row_count,
                out_dim_per_pe=out_dim_per_pe,
                in_dim_per_pe=in_dim_per_pe,
                timeout_seconds=timeout_seconds,
                repo_root=repo_root,
            )
            compile_receipts.append(compile_receipt)
            compile_receipts_by_shape[shape_key] = compile_receipt
            if compile_blocker is not None:
                blocker = compile_blocker
                dispatch_exit_code = None
                break
        tile_dir = (
            scratch_dir
            / "width-row-tiles"
            / f"x{width_start:04d}_w{width_count:04d}"
            / f"y{row_start:04d}_h{row_count:04d}"
        )
        activation_path = tile_dir / "in" / "activation.npy"
        weight_path = tile_dir / "in" / "weight.npy"
        partial_path = tile_dir / "out" / "partial.npy"
        phase_trace_path = tile_dir / "phase-trace.log"
        activation_tile = _materialize_tile_input(
            source_record=activation_record,
            target_path=activation_path,
            full_height=full_height,
            width=width,
            row_start=row_start,
            tile_height=row_count,
            repo_root=repo_root,
            width_start=width_start,
            width_count=width_count,
        )
        weight_tile = _materialize_tile_input(
            source_record=weight_record,
            target_path=weight_path,
            full_height=full_height,
            width=width,
            row_start=row_start,
            tile_height=row_count,
            repo_root=repo_root,
            width_start=width_start,
            width_count=width_count,
        )
        weight_tile["weightInputScope"] = "hidden_width_slice"
        weight_tile["weightResidencyMode"] = "per_tile_h2d_sliced"
        command = _dispatch_command(
            cs_python=cs_python,
            adapter=adapter,
            compile_dir=tile_compile_dir,
            width=width_count,
            height=row_count,
            activation_path=activation_path,
            weight_path=weight_path,
            output_path=partial_path,
            in_dim_per_pe=in_dim_per_pe,
            out_dim_per_pe=out_dim_per_pe,
            cmaddr=cmaddr,
            split_d2h_rows=tile_split_d2h_rows and row_count > 1,
            phase_trace_path=phase_trace_path,
        )
        commands.append(command)
        tile_safety = _tile_shape_safety(
            width=width_count,
            height=row_count,
            out_dim_per_pe=out_dim_per_pe,
            split_d2h_rows=tile_split_d2h_rows and row_count > 1,
        )
        reused_output = None
        if reuse_verified_tile_partials:
            reused_output = _load_verified_tile_partial(
                partial_path=partial_path,
                command=command,
                activation=activation_tile,
                weight=weight_tile,
                compile_receipt=compile_receipt,
                tile_shape_safety=tile_safety,
                width_start=width_start,
                width_count=width_count,
                row_start=row_start,
                row_count=row_count,
                receipt_identity=receipt_identity,
            )
        if reused_output is not None:
            tile_dispatches.append(
                {
                    "tileIndex": len(tile_dispatches),
                    "widthStart": width_start,
                    "width": width_count,
                    "rowStart": row_start,
                    "rowCount": row_count,
                    "activation": activation_tile,
                    "weight": weight_tile,
                    "output": reused_output,
                    "command": command,
                    "tileD2HMode": (
                        "row_split_copyback"
                        if tile_safety.get("splitD2HRows")
                        else "single_region_copyback"
                    ),
                    "exitCode": 0,
                    "timedOut": False,
                    "wallclockNs": 0,
                    "tileShapeSafety": tile_safety,
                    "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
                    "reusedVerifiedPartial": True,
                    "phaseEvents": [],
                    "lastPhaseReached": "verified_partial_reused",
                    "stdoutTail": [],
                    "stderrTail": [],
                }
            )
            aggregate[
                row_start : row_start + row_count,
                :,
            ] += np.load(partial_path).astype(
                np.float32,
                copy=False,
            ).reshape(row_count, out_dim_per_pe)
            partial_paths.append(partial_path)
            reused_tile_count += 1
            continue
        if tile_dispatch_budget > 0 and new_dispatch_count >= tile_dispatch_budget:
            blocker = "dense_gemv_width_tile_dispatch_budget_exhausted"
            dispatch_exit_code = None
            break
        partial_path.unlink(missing_ok=True)
        _tile_partial_receipt_path(partial_path).unlink(missing_ok=True)
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        new_dispatch_count += 1
        pending_dispatches.append(
            {
                "widthStart": width_start,
                "width": width_count,
                "rowStart": row_start,
                "rowCount": row_count,
                "activation": activation_tile,
                "weight": weight_tile,
                "partialPath": partial_path,
                "phaseTracePath": phase_trace_path,
                "command": command,
                "compileReceipt": compile_receipt,
                "tileShapeSafety": tile_safety,
                "splitD2HRows": tile_split_d2h_rows and row_count > 1,
            }
        )
        if effective_tile_dispatch_jobs == 1:
            item = pending_dispatches.pop()
            entry_blocker = record_dispatch_result(
                _run_width_tile_dispatch(
                    item=item,
                    timeout_seconds=timeout_seconds,
                    repo_root=repo_root,
                    dispatcher=dispatcher,
                )
            )
            if entry_blocker is not None:
                blocker = entry_blocker
                break
        if blocker is not None:
            break

    if pending_dispatches:
        if len(pending_dispatches) == 1:
            dispatch_results = [
                _run_width_tile_dispatch(
                    item=item,
                    timeout_seconds=timeout_seconds,
                    repo_root=repo_root,
                    dispatcher=dispatcher,
                )
                for item in pending_dispatches
            ]
        else:
            dispatch_results = []
            with ThreadPoolExecutor(
                max_workers=min(effective_tile_dispatch_jobs, len(pending_dispatches))
            ) as executor:
                futures = [
                    executor.submit(
                        _run_width_tile_dispatch,
                        item=item,
                        timeout_seconds=timeout_seconds,
                        repo_root=repo_root,
                        dispatcher=None,
                    )
                    for item in pending_dispatches
                ]
                for future in as_completed(futures):
                    dispatch_results.append(future.result())
        dispatch_results.sort(key=lambda result: _tile_dispatch_key(result["item"]))

        dispatch_blocker: str | None = None
        for result in dispatch_results:
            entry_blocker = record_dispatch_result(result)
            if entry_blocker is not None and dispatch_blocker is None:
                dispatch_blocker = entry_blocker
        if dispatch_blocker is not None:
            blocker = dispatch_blocker

    tile_dispatches.sort(key=_tile_dispatch_key)
    for index, entry in enumerate(tile_dispatches):
        entry["tileIndex"] = index

    if blocker is None:
        logits = aggregate.reshape(-1)[:out_dim].astype(np.float32, copy=False)
        if int(logits.size) != out_dim:
            blocker = "dense_gemv_aggregate_shape_mismatch"
        output_path = Path(
            str(output_record.get("absolutePath") or output_record["path"])
        )
        if not output_path.is_absolute():
            output_path = repo_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
    if blocker is None:
        output_path = Path(
            str(output_record.get("absolutePath") or output_record["path"])
        )
        if not output_path.is_absolute():
            output_path = repo_root / output_path
        np.save(output_path, logits)
        output_record["dispatchMode"] = "dense_gemv_width_tiled"
        output_record["tileHeight"] = 0
        output_record["rowTileHeights"] = sorted(
            {int(tile["rowCount"]) for tile in planned_tiles}
        )
        output_record["requestedHiddenTileWidth"] = hidden_tile_width
        output_record["hiddenTileWidth"] = effective_hidden_tile_width
        output_record["tileCount"] = len(tile_dispatches)
        output_record["aggregatedElements"] = int(logits.size)
        output_record["tileShapeSafety"] = tile_shape_safety
        output_record["unsafeTileShapeAllowed"] = allow_unsafe_tile_shapes
        output_record["reusedTileCount"] = reused_tile_count
        output_record["hostReduction"] = {
            "kind": "sum_hidden_width_tiles",
            "tileCount": len(partial_paths),
            "sourceDtype": "f32",
            "targetDtype": "f32",
            "reductionOrder": "width_start_then_row_start_ascending",
        }
        _hash_output_record(output_record)
        if int(output_record.get("totalBytes") or 0) <= 0:
            blocker = "dense_gemv_aggregate_output_empty"

    aggregate_elapsed_ns = time.monotonic_ns() - aggregate_started
    expected_tile_count = len(planned_tiles)
    partial_artifacts = _tile_partial_artifact_counts(
        tile_root=scratch_dir / "width-row-tiles",
        accepted_count=len(partial_paths),
        reused_count=reused_tile_count,
    )
    first_fresh = _first_fresh_emitter_partial(
        tile_dispatches=tile_dispatches,
        repo_root=repo_root,
    )
    canonical_anchor = _first_current_emitter_partial(
        tile_dispatches=tile_dispatches,
        repo_root=repo_root,
    )
    tile_coverage = {
        "kind": "width_row_tiles",
        "fullWidth": width,
        "fullHeight": full_height,
        "rowTileHeight": 0,
        "rowTileHeights": sorted({int(tile["rowCount"]) for tile in planned_tiles}),
        "requestedHiddenTileWidth": hidden_tile_width,
        "effectiveHiddenTileWidth": effective_hidden_tile_width,
        "tileShapeSafety": tile_shape_safety,
        "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
        "evidenceIntent": (
            "diagnostic_sweep"
            if allow_unsafe_tile_shapes
            else "claim_eligible_tile_aggregate"
        ),
        "receiptIdentity": receipt_identity or {},
        "hiddenWidthChunks": [
            {
                "widthStart": start,
                "width": count,
                "maxRowTileHeight": _safe_row_tile_height(
                    width=count,
                    out_dim_per_pe=out_dim_per_pe,
                    full_height=full_height,
                    allow_unsafe_tile_shapes=allow_unsafe_tile_shapes,
                    split_d2h_rows=tile_split_d2h_rows,
                    max_row_tile_height=max_row_tile_height,
                ),
            }
            for start, count in chunks
        ],
        "expectedTileCount": expected_tile_count,
        "completedTileCount": len(partial_paths),
        "reusedTileCount": reused_tile_count,
        "verifiedReusablePartials": partial_artifacts[
            "verifiedReusablePartials"
        ],
        "verifiedFreshEmitterPartials": partial_artifacts[
            "verifiedFreshEmitterPartials"
        ],
        "verifiedAcceptedPartials": partial_artifacts[
            "verifiedAcceptedPartials"
        ],
        "tilePartialReceiptsOnDisk": partial_artifacts[
            "tilePartialReceiptsOnDisk"
        ],
        "partialArtifacts": partial_artifacts,
        "canonicalTilePartialAnchor": canonical_anchor,
        "firstFreshEmitterPartial": first_fresh,
        "dispatchedTileCount": len(tile_dispatches) - reused_tile_count,
        "dispatchBudget": tile_dispatch_budget,
        "tileDispatchJobs": max(1, int(tile_dispatch_jobs)),
        "maxRowTileHeight": max_row_tile_height,
        "tileD2HMode": (
            "row_split_copyback"
            if tile_split_d2h_rows
            else "single_region_copyback"
        ),
        "dispatchBudgetExhausted": (
            blocker == "dense_gemv_width_tile_dispatch_budget_exhausted"
        ),
        "coversFullHiddenWidth": sum(count for _, count in chunks) == width,
        "coversFullRows": len(partial_paths) == expected_tile_count,
        "covered": blocker is None and len(partial_paths) == expected_tile_count,
    }
    return DenseGemvTileRun(
        output_records=output_records,
        dispatch_command=commands[0] if commands else ["dense_gemv_width_tiled"],
        dispatch_exit_code=dispatch_exit_code,
        dispatch_stdout="\n".join(stdout_parts),
        dispatch_stderr="\n".join(stderr_parts),
        dispatch_timed_out=dispatch_timed_out,
        dispatch_wallclock_ns=aggregate_elapsed_ns,
        blocker=blocker,
        dispatch_mode="dense_gemv_width_tiled",
        tile_compile={
            "mode": "dense_gemv_width_tiled",
            "requestedHiddenTileWidth": hidden_tile_width,
            "effectiveHiddenTileWidth": effective_hidden_tile_width,
            "shapeSafety": tile_shape_safety,
            "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
            "reuseVerifiedTilePartials": reuse_verified_tile_partials,
            "dispatchBudget": tile_dispatch_budget,
            "maxRowTileHeight": max_row_tile_height,
            "tileD2HMode": (
                "row_split_copyback"
                if tile_split_d2h_rows
                else "single_region_copyback"
            ),
            "evidenceIntent": (
                "diagnostic_sweep"
                if allow_unsafe_tile_shapes
                else "claim_eligible_tile_aggregate"
            ),
            "receiptIdentity": receipt_identity or {},
            "widthTileCount": len(chunks),
            "tileDispatchJobs": max(1, int(tile_dispatch_jobs)),
            "receipts": compile_receipts,
        },
        tile_dispatches=tile_dispatches,
        tile_coverage=tile_coverage,
        weight_input_scope="hidden_width_slice",
        weight_residency_mode="per_tile_h2d_sliced",
    )


def run_dense_gemv_row_tiled(
    *,
    kernel: str,
    compile_root: Path,
    source_root: Path,
    compile_params: dict[str, int],
    input_records: list[dict[str, Any]],
    output_records: list[dict[str, Any]],
    scratch_dir: Path,
    cs_python: Path,
    adapter: Path,
    cmaddr: str,
    timeout_seconds: int,
    repo_root: Path,
    cslc: Path | None,
    tile_height: int = 1,
    hidden_tile_width: int | None = None,
    allow_unsafe_tile_shapes: bool = False,
    reuse_verified_tile_partials: bool = False,
    tile_dispatch_budget: int = 0,
    tile_dispatch_jobs: int = 1,
    max_row_tile_height: int = DEFAULT_SPLIT_D2H_ROW_TILE_HEIGHT,
    batch_runtime: bool = False,
    batch_runtime_step_budget: int = 0,
    tile_y_range: tuple[int, int] | None = None,
    finalize_from_tile_receipts: bool = False,
    worker_id: str = "",
    receipt_identity: dict[str, Any] | None = None,
    dispatcher: DispatchFn | None = None,
) -> DenseGemvTileRun | None:
    if kernel not in {"lm_head_gemv", "lm_head_gemv_stable", "lm_head_prefill_stable"}:
        return None
    activation_record = _record_by_symbol(input_records, "activation")
    weight_record = _record_by_symbol(input_records, "weight")
    output_record = _record_by_symbol(output_records, "output")
    if activation_record is None or weight_record is None or output_record is None:
        return None
    width = int(compile_params.get("width") or 0)
    full_height = int(compile_params.get("height") or 0)
    out_dim = int(compile_params.get("out_dim") or 0)
    out_dim_per_pe = int(compile_params.get("out_dim_per_pe") or 0)
    in_dim_per_pe = int(compile_params.get("in_dim_per_pe") or 0)
    if min(width, full_height, out_dim, out_dim_per_pe, in_dim_per_pe) <= 0:
        return None
    if hidden_tile_width is not None:
        return _run_dense_gemv_width_tiled(
            kernel=kernel,
            compile_root=compile_root,
            source_root=source_root,
            compile_params=compile_params,
            activation_record=activation_record,
            weight_record=weight_record,
            output_record=output_record,
            output_records=output_records,
            scratch_dir=scratch_dir,
            cs_python=cs_python,
            adapter=adapter,
            cmaddr=cmaddr,
            timeout_seconds=timeout_seconds,
            repo_root=repo_root,
            cslc=cslc,
            hidden_tile_width=hidden_tile_width,
            allow_unsafe_tile_shapes=allow_unsafe_tile_shapes,
            reuse_verified_tile_partials=reuse_verified_tile_partials,
            tile_dispatch_budget=tile_dispatch_budget,
            tile_dispatch_jobs=tile_dispatch_jobs,
            max_row_tile_height=max_row_tile_height,
            batch_runtime=batch_runtime,
            batch_runtime_step_budget=batch_runtime_step_budget,
            tile_y_range=tile_y_range,
            finalize_from_tile_receipts=finalize_from_tile_receipts,
            worker_id=worker_id,
            receipt_identity=receipt_identity,
            dispatcher=dispatcher,
        )
    tile_height = max(1, min(tile_height, full_height))
    if full_height % tile_height != 0:
        tile_height = 1
    tile_shape_safety = _tile_shape_safety(
        width=width,
        height=tile_height,
        out_dim_per_pe=out_dim_per_pe,
    )
    if not bool(tile_shape_safety["safe"]) and not allow_unsafe_tile_shapes:
        return _blocked_tile_run(
            output_records=output_records,
            dispatch_mode="dense_gemv_row_tiled",
            blocker="dense_gemv_tile_shape_exceeds_sdk_d2h_limit",
            tile_compile={
                "mode": "dense_gemv_row_tiled",
                "rowTileHeight": tile_height,
                "shapeSafety": tile_shape_safety,
                "unsafeTileShapeAllowed": False,
                "evidenceIntent": "claim_eligible_tile_aggregate",
            },
            tile_coverage={
                "kind": "row_tiles",
                "fullWidth": width,
                "fullHeight": full_height,
                "rowTileHeight": tile_height,
                "tileShapeSafety": tile_shape_safety,
                "unsafeTileShapeAllowed": False,
                "evidenceIntent": "claim_eligible_tile_aggregate",
                "expectedTileCount": 0,
                "completedTileCount": 0,
                "coversFullHiddenWidth": False,
                "coversFullRows": False,
                "covered": False,
            },
            weight_input_scope="full_width_row_slice",
            weight_residency_mode="per_tile_h2d_full_width_row_slice",
        )

    tile_compile_dir = compile_root / f"{kernel}_row_tile_h{tile_height}"
    tile_compile, compile_blocker = _ensure_tile_compile(
        cslc=discover_cslc(cslc),
        source_dir=source_root / kernel,
        tile_compile_dir=tile_compile_dir,
        width=width,
        tile_height=tile_height,
        out_dim_per_pe=out_dim_per_pe,
        in_dim_per_pe=in_dim_per_pe,
        timeout_seconds=timeout_seconds,
        repo_root=repo_root,
    )
    tile_compile["shapeSafety"] = tile_shape_safety
    tile_compile["unsafeTileShapeAllowed"] = allow_unsafe_tile_shapes
    tile_compile["evidenceIntent"] = (
        "diagnostic_sweep"
        if allow_unsafe_tile_shapes
        else "claim_eligible_tile_aggregate"
    )
    if compile_blocker is not None:
        return DenseGemvTileRun(
            output_records=output_records,
            dispatch_command=["dense_gemv_row_tiled"],
            dispatch_exit_code=None,
            dispatch_stdout="",
            dispatch_stderr=str(compile_blocker),
            dispatch_timed_out=False,
            dispatch_wallclock_ns=0,
            blocker=compile_blocker,
            dispatch_mode="dense_gemv_row_tiled",
            tile_compile=tile_compile,
            tile_dispatches=[],
            weight_input_scope="full_width_row_slice",
            weight_residency_mode="per_tile_h2d_full_width_row_slice",
        )

    tile_root = scratch_dir / "row-tiles"
    tile_dispatches: list[dict[str, Any]] = []
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    output_chunks: list[Any] = []
    first_command: list[str] = ["dense_gemv_row_tiled"]
    aggregate_started = time.monotonic_ns()
    dispatch_exit_code = 0
    dispatch_timed_out = False
    blocker: str | None = None

    for row_start in range(0, full_height, tile_height):
        tile_dir = tile_root / f"y{row_start:04d}_h{tile_height:04d}"
        activation_path = tile_dir / "in" / "activation.npy"
        weight_path = tile_dir / "in" / "weight.npy"
        tile_output_path = tile_dir / "out" / "output.npy"
        tile_output_path.unlink(missing_ok=True)
        activation_tile = _materialize_tile_input(
            source_record=activation_record,
            target_path=activation_path,
            full_height=full_height,
            width=width,
            row_start=row_start,
            tile_height=tile_height,
            repo_root=repo_root,
        )
        weight_tile = _materialize_tile_input(
            source_record=weight_record,
            target_path=weight_path,
            full_height=full_height,
            width=width,
            row_start=row_start,
            tile_height=tile_height,
            repo_root=repo_root,
        )
        weight_tile["weightInputScope"] = "full_width_row_slice"
        weight_tile["weightResidencyMode"] = "per_tile_h2d_full_width_row_slice"
        command = _dispatch_command(
            cs_python=cs_python,
            adapter=adapter,
            compile_dir=tile_compile_dir,
            width=width,
            height=tile_height,
            activation_path=activation_path,
            weight_path=weight_path,
            output_path=tile_output_path,
            in_dim_per_pe=in_dim_per_pe,
            out_dim_per_pe=out_dim_per_pe,
            cmaddr=cmaddr,
        )
        if len(first_command) == 1:
            first_command = list(command)
        started = time.monotonic_ns()
        if dispatcher is None:
            exit_code, stdout, stderr, timed_out = _run_command(
                command,
                timeout_seconds=timeout_seconds,
                cwd=repo_root,
            )
        else:
            exit_code, stdout, stderr, timed_out = dispatcher(
                command,
                timeout_seconds=timeout_seconds,
            )
        elapsed_ns = time.monotonic_ns() - started
        stdout_parts.extend(_tail(stdout, lines=4))
        stderr_parts.extend(_tail(stderr, lines=4))
        phase_events = _parse_phase_events(stdout)
        tile_output = {
            "path": str(tile_output_path),
            "totalBytes": 0,
            "sha256": "",
        }
        if tile_output_path.is_file():
            tile_output["totalBytes"] = tile_output_path.stat().st_size
            tile_output["sha256"] = sha256_file(tile_output_path)
        tile_dispatches.append(
            {
                "tileIndex": len(tile_dispatches),
                "rowStart": row_start,
                "tileHeight": tile_height,
                "activation": activation_tile,
                "weight": weight_tile,
                "output": tile_output,
                "command": command,
                "exitCode": exit_code,
                "timedOut": timed_out,
                "wallclockNs": elapsed_ns,
                "tileShapeSafety": tile_shape_safety,
                "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
                "phaseEvents": phase_events,
                "lastPhaseReached": _last_phase(phase_events),
                "stdoutTail": _tail(stdout),
                "stderrTail": _tail(stderr),
            }
        )
        if timed_out:
            dispatch_exit_code = -1
            dispatch_timed_out = True
            blocker = "dense_gemv_tile_dispatch_timed_out"
            break
        if exit_code != 0:
            dispatch_exit_code = exit_code
            blocker = f"dense_gemv_tile_dispatch_exit_code_{exit_code}"
            break
        if int(tile_output["totalBytes"]) <= 0:
            dispatch_exit_code = exit_code
            blocker = "dense_gemv_tile_output_empty"
            break
        import numpy as np

        output_chunks.append(np.load(tile_output_path).astype(np.float32, copy=False))

    aggregate_elapsed_ns = time.monotonic_ns() - aggregate_started
    if blocker is None:
        import numpy as np

        aggregate = np.concatenate(output_chunks).astype(np.float32, copy=False)
        aggregate = aggregate[:out_dim]
        if int(aggregate.size) != out_dim:
            blocker = "dense_gemv_aggregate_shape_mismatch"
    if blocker is None:
        output_path = Path(str(output_record.get("absolutePath") or output_record["path"]))
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
        np.save(output_path, aggregate)
        output_record["dispatchMode"] = "dense_gemv_row_tiled"
        output_record["tileHeight"] = tile_height
        output_record["tileCount"] = len(tile_dispatches)
        output_record["aggregatedElements"] = int(aggregate.size)
        output_record["tileShapeSafety"] = tile_shape_safety
        output_record["unsafeTileShapeAllowed"] = allow_unsafe_tile_shapes
        _hash_output_record(output_record)
        if int(output_record.get("totalBytes") or 0) <= 0:
            blocker = "dense_gemv_aggregate_output_empty"

    expected_tile_count = len(range(0, full_height, tile_height))
    tile_coverage = {
        "kind": "row_tiles",
        "fullWidth": width,
        "fullHeight": full_height,
        "rowTileHeight": tile_height,
        "tileShapeSafety": tile_shape_safety,
        "unsafeTileShapeAllowed": allow_unsafe_tile_shapes,
        "evidenceIntent": (
            "diagnostic_sweep"
            if allow_unsafe_tile_shapes
            else "claim_eligible_tile_aggregate"
        ),
        "expectedTileCount": expected_tile_count,
        "completedTileCount": len(output_chunks),
        "coversFullHiddenWidth": True,
        "coversFullRows": len(output_chunks) == expected_tile_count,
        "covered": blocker is None and len(output_chunks) == expected_tile_count,
    }
    return DenseGemvTileRun(
        output_records=output_records,
        dispatch_command=first_command,
        dispatch_exit_code=dispatch_exit_code,
        dispatch_stdout="\n".join(stdout_parts),
        dispatch_stderr="\n".join(stderr_parts),
        dispatch_timed_out=dispatch_timed_out,
        dispatch_wallclock_ns=aggregate_elapsed_ns,
        blocker=blocker,
        dispatch_mode="dense_gemv_row_tiled",
        tile_compile=tile_compile,
        tile_dispatches=tile_dispatches,
        tile_coverage=tile_coverage,
        weight_input_scope="full_width_row_slice",
        weight_residency_mode="per_tile_h2d_full_width_row_slice",
    )
