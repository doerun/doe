#!/usr/bin/env python3
"""Per-kernel manifest-shape dispatch runner with Doppler-probe inputs (rung 3).

Mitigates "Per-kernel manifest-shape dispatch (rung 3)" from
docs/cerebras-north-star.md (Manifest-shape simfabric proof plan):

  > Extend bench/runners/csl-runners/multi_token_decode_orchestrator.py
  > (or a new sibling manifest_kernel_probe_runner.py) to dispatch one
  > kernel at manifest shape with manifest-shape inputs, against
  > per-kernel Doppler probes from
  > bench/fixtures/tsir-real-doppler-transcripts/. Receipt:
  > bench/out/r3-1-31b-manifest-simfabric-per-kernel/<kernel>.json.

Differences from rung-4 (`bench/tools/run_manifest_shape_layout_receipt.py`):

  - Inputs come from the per-kernel Doppler probe transcripts and the
    bootstrap input fixtures they cite (not zero-filled). The probe
    values are tiled/broadcast across the manifest-shape buffer; the
    receipt records the broadcast strategy + probe identity.
  - Receipt is `doe_manifest_shape_per_kernel_dispatch_receipt`,
    `receiptClass: manifest_shape_per_kernel_dispatch`.
  - Records `dispatchWallclockNs` so callers can derive the rung-2
    throughput calibration constant (`bytesPerCycle` =
    grandTotalOutputBytes / dispatchWallclockNs * cycles_per_ns).

Comparison to a Doppler reference oracle is **not** done here — that's
rung 6/8/9 (parity rungs against the frozen-Doppler reference fixture
behind `bench/tools/validate_frozen_doppler_reference.py`). This rung's
purpose is calibration + per-kernel dispatch plumbing with non-zero
inputs.

Usage:

  python3 bench/runners/csl-runners/manifest_kernel_probe_runner.py \\
    --host-plan bench/out/r3-1-31b-manifest-fullgraph-compile-steps/host-plan.json \\
    --compile-root bench/out/r3-1-31b-manifest-fullgraph-compile-steps/compile \\
    --probe-dir bench/fixtures/tsir-real-doppler-transcripts \\
    --out-dir bench/out/r3-1-31b-manifest-simfabric-per-kernel
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._receipt_hash_guard import (  # noqa: E402
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
)
from bench.tools.predict_simfabric_wallclock import (  # noqa: E402
    SizeExprError,
    evaluate_size_expr,
)
from bench.tools.run_manifest_shape_layout_receipt import (  # noqa: E402
    ELEM_BYTES,
    LayoutReceiptError,
    build_dispatch_command,
    classify_exports,
    run_dispatch_subprocess,
)


CS_PYTHON_SINGULARITY = (
    REPO_ROOT / "runtime/zig/tools/cs_python_singularity.sh"
)
CHAIN_STEP_ADAPTER = (
    REPO_ROOT / "bench/runners/csl-runners/chain_step_adapter.py"
)
DEFAULT_HOST_PLAN = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/host-plan.json"
)
DEFAULT_COMPILE_ROOT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/compile"
)
DEFAULT_PROBE_DIR = (
    REPO_ROOT / "bench/fixtures/tsir-real-doppler-transcripts"
)
DEFAULT_OUT_DIR = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-simfabric-per-kernel"
)

PROBE_TRANSCRIPT_ALIASES = {
    "attn_decode_sliding": "attn_decode",
    "gelu_decode": "gelu",
    "gelu_prefill": "gelu",
    "kv_write_shared": "kv_write",
    "lm_head_gemv_stable": "lm_head_gemv",
    "lm_head_prefill_stable": "lm_head_gemv",
    "o_gate": "silu_gated",
    "ple_proj": "tiled",
    "ple_rmsnorm": "rmsnorm",
    "residual_decode": "residual",
    "residual_prefill": "residual",
    "rmsnorm_decode": "rmsnorm",
    "rmsnorm_prefill": "rmsnorm",
}

ZERO_DEFAULT_H2D_INPUTS_BY_KERNEL = {
    "lm_head_gemv_stable": {"activation", "weight"},
    "lm_head_prefill_stable": {"activation", "weight"},
}

_LAYOUT_PARAM_DEFAULT_RE = re.compile(
    r"\bparam\s+([A-Za-z_][A-Za-z0-9_]*)\s*:[^=;]+=\s*([0-9]+)\s*;"
)
_COMPILED_ELF_RE = re.compile(r"out_([0-9]+)_([0-9]+)\.elf$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host-plan", type=Path, default=DEFAULT_HOST_PLAN)
    p.add_argument("--compile-root", type=Path, default=DEFAULT_COMPILE_ROOT)
    p.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help=(
            "Optional separate root for per-kernel CSL source + "
            "pe_program.metadata.json. Defaults to --compile-root. The "
            "steps-mode driver lays source under "
            "<compile-root>/<kernel>/ and binaries under "
            "<compile-root>/compiled/<kernel>/, so callers pass "
            "--source-root <compile-root> and "
            "--compile-root <compile-root>/compiled."
        ),
    )
    p.add_argument("--probe-dir", type=Path, default=DEFAULT_PROBE_DIR)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument(
        "--kernel",
        action="append",
        default=None,
        help="Restrict to one or more named kernels.",
    )
    p.add_argument(
        "--cmaddr",
        default="",
        help="Optional CM endpoint for hardware dispatch.",
    )
    p.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="Per-kernel subprocess timeout.",
    )
    p.add_argument(
        "--cs-python", type=Path, default=CS_PYTHON_SINGULARITY
    )
    p.add_argument("--adapter", type=Path, default=CHAIN_STEP_ADAPTER)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Materialize probe-broadcast inputs and assemble the dispatch "
            "command without spawning cs_python."
        ),
    )
    p.add_argument(
        "--jobs",
        type=int,
        default=1,
        help=(
            "Number of independent per-kernel dispatch workers. Each worker "
            "uses its own scratch/<kernel>/ directory and receipt JSON."
        ),
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Reuse existing non-dry-run dispatch receipts whose hostPlanHash "
            "matches the current host plan. Dry-run receipts are not reused "
            "for non-dry-run dispatch."
        ),
    )
    p.add_argument(
        "--reuse-blocked",
        action="store_true",
        help=(
            "With --resume, reuse existing blocked non-dry-run receipts too. "
            "This refreshes summaries while preserving explicit blockers "
            "instead of rerunning those kernels."
        ),
    )
    p.add_argument(
        "--schedule",
        choices=["host-plan", "heavy-first"],
        default="host-plan",
        help=(
            "Kernel launch order. heavy-first uses metadata-estimated "
            "manifest-shape input/output bytes so large kernels do not sit "
            "behind smaller probes when --jobs is used."
        ),
    )
    return p.parse_args()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _try_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _tail(text: str, lines: int = 20) -> list[str]:
    return text.splitlines()[-lines:] if text else []


def find_probe_transcript(
    *, kernel: str, probe_dir: Path
) -> Path | None:
    """Locate the Doppler transcript for a kernel, if any.

    Naming convention: `<kernel>.doppler-transcript.json`. Aliases
    (e.g. `rms_norm` ↔ `rmsnorm`) are normalized by stripping
    underscores before matching, so either spelling resolves to the
    same fixture when one exists.
    """
    direct = probe_dir / f"{kernel}.doppler-transcript.json"
    if direct.is_file():
        return direct
    alias = PROBE_TRANSCRIPT_ALIASES.get(kernel)
    if alias:
        alias_path = probe_dir / f"{alias}.doppler-transcript.json"
        if alias_path.is_file():
            return alias_path
    canonical = kernel.replace("_", "")
    for entry in probe_dir.glob("*.doppler-transcript.json"):
        stem = entry.name[: -len(".doppler-transcript.json")]
        if stem.replace("_", "") == canonical:
            return entry
    return None


def load_probe_inputs(
    transcript_path: Path,
) -> tuple[dict[str, list[float | int]], dict[str, Any]]:
    """Resolve transcript → bootstrap input fixture → per-symbol values.

    Returns (input_values_by_symbol, probe_metadata). The metadata is
    stamped on the receipt's `probe` block.
    """
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    source = transcript.get("source") or {}
    fixture_rel = source.get("fixturePath")
    if not isinstance(fixture_rel, str) or not fixture_rel:
        return {}, {
            "fixturePath": _try_relative(transcript_path),
            "fixtureHash": _sha256_file(transcript_path),
            "kernelRef": transcript.get("kernelRef"),
            "inputFixturePath": None,
            "inputFixtureHash": None,
            "broadcastStrategy": "absent_input_fixture",
        }
    input_path = (REPO_ROOT / fixture_rel).resolve()
    if not input_path.is_file():
        return {}, {
            "fixturePath": _try_relative(transcript_path),
            "fixtureHash": _sha256_file(transcript_path),
            "kernelRef": transcript.get("kernelRef"),
            "inputFixturePath": fixture_rel,
            "inputFixtureHash": None,
            "broadcastStrategy": "input_fixture_missing",
        }
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    inputs_block = raw.get("inputs") or {}
    by_symbol: dict[str, list[float | int]] = {}
    for symbol, body in inputs_block.items():
        if not isinstance(body, dict):
            continue
        values = body.get("values")
        if isinstance(values, list):
            by_symbol[symbol] = list(values)
    return by_symbol, {
        "fixturePath": _try_relative(transcript_path),
        "fixtureHash": _sha256_file(transcript_path),
        "kernelRef": transcript.get("kernelRef"),
        "inputFixturePath": fixture_rel,
        "inputFixtureHash": _sha256_file(input_path),
        "broadcastStrategy": "tile_to_manifest_shape",
    }


def materialize_probe_input(
    *,
    target_path: Path,
    pe_count: int,
    per_pe_chunk: int,
    elem_type: str,
    probe_values: list[float | int] | None,
) -> tuple[int, str]:
    """Write a manifest-shape `.npy` initialized from probe values.

    When `probe_values` is None or empty, the buffer is zero-filled
    (matches rung-4 behavior for that symbol). Otherwise probe values
    are tiled to fill the (pe_count * per_pe_chunk) buffer. Returns
    (byte_length, broadcast_strategy_for_this_symbol).
    """
    import numpy as np

    dtype_map = {
        "f32": np.float32,
        "u32": np.uint32,
        "i32": np.int32,
        "f16": np.float16,
        "u16": np.uint16,
        "i16": np.int16,
        "u8": np.uint8,
        "i8": np.int8,
    }
    dtype = dtype_map.get(elem_type, np.float32)
    total = pe_count * per_pe_chunk
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not probe_values:
        arr = np.zeros(total, dtype=dtype)
        strategy = "zero"
    else:
        source_arr = np.asarray(probe_values, dtype=dtype)
        if source_arr.size == 0:
            arr = np.zeros(total, dtype=dtype)
            strategy = "zero"
        elif source_arr.size >= total:
            arr = source_arr[:total].astype(dtype, copy=False)
            strategy = "truncate"
        else:
            reps = (total + source_arr.size - 1) // source_arr.size
            arr = np.tile(source_arr, reps)[:total].astype(
                dtype, copy=False
            )
            strategy = "tile"
    np.save(target_path, arr)
    return target_path.stat().st_size, strategy


def _adapter_dtype_token(elem_type: str) -> str:
    if elem_type in ("f32", "u32", "f16", "u8"):
        return elem_type
    if elem_type == "i32":
        return "u32"
    raise LayoutReceiptError(
        f"chain_step_adapter does not support elemType {elem_type!r} yet "
        "(wired: f32, u32, f16, u8)."
    )


def _infer_grid_from_compile_dir(compile_dir: Path) -> dict[str, int]:
    bin_dir = compile_dir / "bin"
    if not bin_dir.is_dir():
        return {}
    max_x = -1
    max_y = -1
    for entry in bin_dir.iterdir():
        match = _COMPILED_ELF_RE.match(entry.name)
        if match is None:
            continue
        max_x = max(max_x, int(match.group(1)))
        max_y = max(max_y, int(match.group(2)))
    inferred: dict[str, int] = {}
    if max_x >= 0:
        inferred["width"] = max_x + 1
    if max_y >= 0:
        inferred["height"] = max_y + 1
    return inferred


def _merge_layout_param_defaults(
    bindings: dict[str, int], layout_path: Path
) -> None:
    if not layout_path.is_file():
        return
    text = layout_path.read_text(encoding="utf-8")
    for match in _LAYOUT_PARAM_DEFAULT_RE.finditer(text):
        name = match.group(1)
        if name not in bindings:
            bindings[name] = int(match.group(2))


def _merge_metadata_integer_constants(
    bindings: dict[str, int], metadata: dict[str, Any]
) -> None:
    constants = list(metadata.get("compileTimeConstants") or [])
    changed = True
    while changed:
        changed = False
        for entry in constants:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            expr = entry.get("expr")
            if (
                not isinstance(name, str)
                or not name
                or name in bindings
                or not isinstance(expr, str)
            ):
                continue
            try:
                value = evaluate_size_expr(expr, bindings)
            except SizeExprError:
                continue
            bindings[name] = int(value)
            changed = True


def _compile_bindings(
    *,
    target: dict[str, Any],
    metadata: dict[str, Any],
    compile_dir: Path,
    layout_path: Path,
) -> dict[str, int]:
    bindings = {
        str(k): int(v)
        for k, v in (target.get("compileParams") or {}).items()
        if isinstance(v, (int, float))
    }
    for name, value in _infer_grid_from_compile_dir(compile_dir).items():
        bindings.setdefault(name, value)
    _merge_layout_param_defaults(bindings, layout_path)
    bindings.setdefault("height", 1)
    _merge_metadata_integer_constants(bindings, metadata)
    return bindings


def _metadata_path_for_kernel(
    *,
    kernel: str,
    source_root: Path,
) -> Path:
    metadata_path = source_root / kernel / "pe_program.metadata.json"
    if metadata_path.is_file():
        return metadata_path
    for suffix in ("_decode", "_prefill"):
        if kernel.endswith(suffix):
            base_kernel = kernel[: -len(suffix)]
            base_path = source_root / base_kernel / "pe_program.metadata.json"
            if base_path.is_file():
                return base_path
    return metadata_path


def _layout_path_for_kernel(
    *,
    kernel: str,
    source_root: Path,
) -> Path:
    layout_path = source_root / kernel / "layout.csl"
    if layout_path.is_file():
        return layout_path
    for suffix in ("_decode", "_prefill"):
        if kernel.endswith(suffix):
            base_kernel = kernel[: -len(suffix)]
            base_path = source_root / base_kernel / "layout.csl"
            if base_path.is_file():
                return base_path
    return layout_path


def estimate_target_io_bytes(
    *,
    target: dict[str, Any],
    compile_root: Path,
    source_root: Path,
) -> int:
    kernel = str(target.get("name") or "")
    if not kernel:
        return 0
    metadata_path = _metadata_path_for_kernel(
        kernel=kernel,
        source_root=source_root,
    )
    if not metadata_path.is_file():
        return 0
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        bindings = _compile_bindings(
            target=target,
            metadata=metadata,
            compile_dir=compile_root / kernel,
            layout_path=_layout_path_for_kernel(
                kernel=kernel,
                source_root=source_root,
            ),
        )
        width = int(bindings.get("width") or 0)
        height = int(bindings.get("height") or 1)
        pe_count = max(1, width * height)
        total = 0
        for export in metadata.get("exports") or []:
            if not isinstance(export, dict):
                continue
            chunk = int(
                evaluate_size_expr(export.get("sizeExpr", ""), bindings)
            )
            elem_type = str(export.get("elemType", "f32"))
            total += pe_count * chunk * ELEM_BYTES.get(elem_type, 4)
        return total
    except (OSError, ValueError, SizeExprError, json.JSONDecodeError):
        return 0


def order_targets(
    *,
    targets: list[dict[str, Any]],
    schedule: str,
    compile_root: Path,
    source_root: Path,
) -> list[dict[str, Any]]:
    if schedule != "heavy-first":
        return list(targets)
    indexed = list(enumerate(targets))
    indexed.sort(
        key=lambda item: (
            estimate_target_io_bytes(
                target=item[1],
                compile_root=compile_root,
                source_root=source_root,
            ),
            -item[0],
        ),
        reverse=True,
    )
    return [target for _, target in indexed]


def load_reusable_receipt(
    *,
    kernel: str,
    out_dir: Path,
    host_plan_hash: str,
    dry_run: bool,
    reuse_blocked: bool = False,
) -> dict[str, Any] | None:
    path = out_dir / f"{kernel}.json"
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if receipt.get("kernel") != kernel:
        return None
    if receipt.get("hostPlanHash") != host_plan_hash:
        return None
    blocker = receipt.get("blocker")
    if dry_run:
        return receipt if blocker == "dry_run" else None
    if blocker == "dry_run":
        return None
    if receipt.get("verdict") == "bound":
        return receipt
    if receipt.get("dispatchTimedOut") is True:
        return receipt
    if reuse_blocked and receipt.get("verdict") == "blocked":
        return receipt
    return None


def _hash_output_files(records: list[dict[str, Any]]) -> None:
    for record in records:
        path = Path(record.pop("absolutePath", record["path"]))
        if not path.is_file():
            record["totalBytes"] = 0
            record["sha256"] = ""
            continue
        record["totalBytes"] = path.stat().st_size
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                h.update(chunk)
        record["sha256"] = h.hexdigest()


def _materialize_inputs(
    *,
    kernel: str,
    target: dict[str, Any],
    metadata: dict[str, Any],
    probe_inputs: dict[str, list[float | int]],
    scratch_dir: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
    list[str],
    int,
    dict[str, str],
]:
    """Like rung-4 but uses probe-broadcast inputs for symbols with a
    probe entry. Returns the rung-4 quintuple plus a per-symbol
    broadcast-strategy map for the probe block."""
    bindings = dict(target.get("compileParams") or {})
    width = int(bindings.get("width") or 0)
    height = int(bindings.get("height") or 1)
    pe_count = max(1, width * height)
    inputs_meta, outputs_meta = classify_exports(
        list(metadata.get("exports") or []),
        kernel_name=kernel,
    )

    input_records: list[dict[str, Any]] = []
    output_records: list[dict[str, Any]] = []
    input_specs: list[str] = []
    output_specs: list[str] = []
    per_symbol_strategy: dict[str, str] = {}

    chunk_size_default = 0
    for export in inputs_meta:
        try:
            chunk = int(evaluate_size_expr(
                export.get("sizeExpr", ""), bindings
            ))
        except SizeExprError as err:
            raise LayoutReceiptError(
                f"kernel {kernel!r}: unable to evaluate sizeExpr for input "
                f"symbol {export.get('symbol')!r}: {err}"
            ) from err
        if chunk_size_default == 0:
            chunk_size_default = chunk
        elem_type = export.get("elemType", "f32")
        elem_bytes = ELEM_BYTES.get(elem_type, 4)
        symbol = export.get("symbol", "")
        path = scratch_dir / "in" / f"{symbol}.npy"
        zero_default_h2d = symbol in ZERO_DEFAULT_H2D_INPUTS_BY_KERNEL.get(
            kernel, set()
        )
        probe_vals = None if zero_default_h2d else probe_inputs.get(symbol)
        byte_len, strategy = materialize_probe_input(
            target_path=path,
            pe_count=pe_count,
            per_pe_chunk=chunk,
            elem_type=elem_type,
            probe_values=probe_vals,
        )
        if zero_default_h2d:
            strategy = "zero_default_h2d"
        per_symbol_strategy[symbol] = strategy
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for piece in iter(lambda: handle.read(1 << 20), b""):
                h.update(piece)
        total_elems = pe_count * chunk
        input_records.append(
            {
                "symbol": symbol,
                "path": _try_relative(path),
                "elemType": elem_type,
                "elemBytes": elem_bytes,
                "perPeChunk": chunk,
                "totalElements": total_elems,
                "totalBytes": total_elems * elem_bytes,
                "sha256": h.hexdigest(),
                "probeStrategy": strategy,
            }
        )
        adapter_dtype = _adapter_dtype_token(elem_type)
        input_specs.append(
            f"{symbol}:{path}:{adapter_dtype}:{chunk}"
        )

    for export in outputs_meta:
        try:
            chunk = int(evaluate_size_expr(
                export.get("sizeExpr", ""), bindings
            ))
        except SizeExprError as err:
            raise LayoutReceiptError(
                f"kernel {kernel!r}: unable to evaluate sizeExpr for output "
                f"symbol {export.get('symbol')!r}: {err}"
            ) from err
        if chunk_size_default == 0:
            chunk_size_default = chunk
        elem_type = export.get("elemType", "f32")
        elem_bytes = ELEM_BYTES.get(elem_type, 4)
        symbol = export.get("symbol", "")
        path = scratch_dir / "out" / f"{symbol}.npy"
        path.parent.mkdir(parents=True, exist_ok=True)
        total_elems = pe_count * chunk
        output_records.append(
            {
                "symbol": symbol,
                "path": _try_relative(path),
                "elemType": elem_type,
                "elemBytes": elem_bytes,
                "perPeChunk": chunk,
                "totalElements": total_elems,
                "totalBytes": 0,
                "sha256": "",
                "absolutePath": str(path),
            }
        )
        adapter_dtype = _adapter_dtype_token(elem_type)
        output_specs.append(
            f"{symbol}:{path}:{adapter_dtype}:{chunk}"
        )

    return (
        input_records,
        output_records,
        input_specs,
        output_specs,
        chunk_size_default or 1,
        per_symbol_strategy,
    )


def build_kernel_receipt(
    *,
    kernel: str,
    compile_dir: Path,
    compile_params: dict[str, int],
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    probe: dict[str, Any],
    dispatch_command: list[str],
    dispatch_exit_code: int | None,
    dispatch_stdout: str,
    dispatch_stderr: str,
    dispatch_timed_out: bool,
    dispatch_wallclock_ns: int | None,
    host_plan_path: Path,
    host_plan_hash: str,
    cmaddr: str,
    blocker: str | None,
) -> dict[str, Any]:
    total_input_bytes = sum(int(r.get("totalBytes", 0)) for r in inputs)
    total_output_bytes = sum(int(r.get("totalBytes", 0)) for r in outputs)
    aggregate = hashlib.sha256()
    for record in outputs:
        digest = record.get("sha256")
        if isinstance(digest, str) and digest:
            aggregate.update(digest.encode("ascii"))
    output_digest = aggregate.hexdigest() if outputs else ""

    if blocker is None:
        if dispatch_exit_code != 0 or dispatch_timed_out:
            blocker = (
                "dispatch_timed_out"
                if dispatch_timed_out
                else f"dispatch_exit_code_{dispatch_exit_code}"
            )
        elif total_output_bytes == 0 and outputs:
            blocker = "outputs_empty_after_dispatch"

    verdict = "blocked" if blocker else "bound"

    return {
        "schemaVersion": 1,
        "artifactKind": "doe_manifest_shape_per_kernel_dispatch_receipt",
        "receiptClass": "manifest_shape_per_kernel_dispatch",
        "comparisonMode": "no_oracle",
        "kernel": kernel,
        "compileDir": _try_relative(compile_dir),
        "compileParams": dict(compile_params),
        "hostPlanPath": _try_relative(host_plan_path),
        "hostPlanHash": host_plan_hash,
        "cmaddr": cmaddr or "",
        "executionTarget": "system" if cmaddr else "simfabric",
        "probe": probe,
        "inputs": list(inputs),
        "outputs": list(outputs),
        "totalInputBytes": total_input_bytes,
        "totalOutputBytes": total_output_bytes,
        "outputDigest": output_digest,
        "dispatchExitCode": dispatch_exit_code,
        "dispatchTimedOut": dispatch_timed_out,
        "dispatchWallclockNs": dispatch_wallclock_ns,
        "subprocess": {
            "command": list(dispatch_command),
            "stdoutTail": _tail(dispatch_stdout),
            "stderrTail": _tail(dispatch_stderr),
        },
        "verdict": verdict,
        "blocker": blocker,
        "claim": {
            "scope": (
                "Per-kernel manifest-shape dispatch with Doppler-probe "
                "inputs (tiled to manifest shape). Records bytes-in / "
                "bytes-out, dispatch exit code, and wall-clock so "
                "downstream rung-2 calibration can derive the "
                "throughput constant."
            ),
            "notWhat": (
                "Not a parity claim against the frozen Doppler "
                "reference; that's rung 6/8/9 once the rung-5 fixture "
                "lands. Probe inputs are tiled across the manifest-"
                "shape buffer — values are not numerically meaningful "
                "for kernels whose probe shape is much smaller than "
                "manifest shape."
            ),
        },
    }


def run_one_kernel(
    *,
    kernel: str,
    target: dict[str, Any],
    compile_root: Path,
    source_root: Path | None = None,
    probe_dir: Path,
    host_plan_path: Path,
    host_plan_hash: str,
    out_dir: Path,
    cmaddr: str,
    timeout_seconds: int,
    cs_python: Path,
    adapter: Path,
    dry_run: bool,
    dispatcher: Callable[..., tuple[int, str, str, bool]] | None = None,
) -> dict[str, Any]:
    effective_source_root = source_root if source_root is not None else compile_root
    metadata_path = _metadata_path_for_kernel(
        kernel=kernel,
        source_root=effective_source_root,
    )
    if not metadata_path.is_file():
        return build_kernel_receipt(
            kernel=kernel,
            compile_dir=compile_root / kernel,
            compile_params={
                str(k): int(v)
                for k, v in (target.get("compileParams") or {}).items()
            },
            inputs=[],
            outputs=[],
            probe={"broadcastStrategy": "absent"},
            dispatch_command=[],
            dispatch_exit_code=None,
            dispatch_stdout="",
            dispatch_stderr="",
            dispatch_timed_out=False,
            dispatch_wallclock_ns=None,
            host_plan_path=host_plan_path,
            host_plan_hash=host_plan_hash,
            cmaddr=cmaddr,
            blocker=f"metadata_missing: {metadata_path}",
        )

    transcript_path = find_probe_transcript(
        kernel=kernel, probe_dir=probe_dir
    )
    if transcript_path is None:
        return build_kernel_receipt(
            kernel=kernel,
            compile_dir=compile_root / kernel,
            compile_params={
                str(k): int(v)
                for k, v in (target.get("compileParams") or {}).items()
            },
            inputs=[],
            outputs=[],
            probe={"broadcastStrategy": "absent"},
            dispatch_command=[],
            dispatch_exit_code=None,
            dispatch_stdout="",
            dispatch_stderr="",
            dispatch_timed_out=False,
            dispatch_wallclock_ns=None,
            host_plan_path=host_plan_path,
            host_plan_hash=host_plan_hash,
            cmaddr=cmaddr,
            blocker="probe_fixture_absent",
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    compile_dir = compile_root / kernel
    layout_path = _layout_path_for_kernel(
        kernel=kernel,
        source_root=effective_source_root,
    )
    compile_params = _compile_bindings(
        target=target,
        metadata=metadata,
        compile_dir=compile_dir,
        layout_path=layout_path,
    )
    width = int(compile_params.get("width") or 0)
    height = int(compile_params.get("height") or 1)

    probe_inputs, probe_metadata = load_probe_inputs(transcript_path)

    scratch_dir = out_dir / "scratch" / kernel
    scratch_dir.mkdir(parents=True, exist_ok=True)

    try:
        (
            input_records,
            output_records,
            input_specs,
            output_specs,
            chunk_default,
            per_symbol_strategy,
        ) = _materialize_inputs(
            kernel=kernel,
            target={"compileParams": compile_params},
            metadata=metadata,
            probe_inputs=probe_inputs,
            scratch_dir=scratch_dir,
        )
    except LayoutReceiptError as err:
        return build_kernel_receipt(
            kernel=kernel,
            compile_dir=compile_root / kernel,
            compile_params=compile_params,
            inputs=[],
            outputs=[],
            probe=probe_metadata,
            dispatch_command=[],
            dispatch_exit_code=None,
            dispatch_stdout="",
            dispatch_stderr=str(err),
            dispatch_timed_out=False,
            dispatch_wallclock_ns=None,
            host_plan_path=host_plan_path,
            host_plan_hash=host_plan_hash,
            cmaddr=cmaddr,
            blocker=f"input_synthesis_failed: {err}",
        )

    probe_metadata["perSymbolStrategy"] = per_symbol_strategy

    command = build_dispatch_command(
        cs_python=cs_python,
        adapter=adapter,
        compile_dir=compile_dir,
        width=width,
        height=height,
        chunk_size=chunk_default,
        input_specs=input_specs,
        output_specs=output_specs,
        cmaddr=cmaddr,
    )

    if dry_run:
        for record in output_records:
            record.pop("absolutePath", None)
        return build_kernel_receipt(
            kernel=kernel,
            compile_dir=compile_dir,
            compile_params=compile_params,
            inputs=input_records,
            outputs=output_records,
            probe=probe_metadata,
            dispatch_command=command,
            dispatch_exit_code=None,
            dispatch_stdout="",
            dispatch_stderr="",
            dispatch_timed_out=False,
            dispatch_wallclock_ns=None,
            host_plan_path=host_plan_path,
            host_plan_hash=host_plan_hash,
            cmaddr=cmaddr,
            blocker="dry_run",
        )

    blocker: str | None = None
    if not cs_python.is_file():
        blocker = f"cs_python_unavailable: {cs_python}"
    elif not adapter.is_file():
        blocker = f"chain_step_adapter_missing: {adapter}"
    elif not (compile_dir / "bin").is_dir():
        blocker = f"compile_bin_missing: {compile_dir}/bin"

    if blocker is not None:
        for record in output_records:
            record.pop("absolutePath", None)
        return build_kernel_receipt(
            kernel=kernel,
            compile_dir=compile_dir,
            compile_params=compile_params,
            inputs=input_records,
            outputs=output_records,
            probe=probe_metadata,
            dispatch_command=command,
            dispatch_exit_code=None,
            dispatch_stdout="",
            dispatch_stderr="",
            dispatch_timed_out=False,
            dispatch_wallclock_ns=None,
            host_plan_path=host_plan_path,
            host_plan_hash=host_plan_hash,
            cmaddr=cmaddr,
            blocker=blocker,
        )

    runner = dispatcher or run_dispatch_subprocess
    started = time.monotonic_ns()
    exit_code, stdout, stderr, timed_out = runner(
        command, timeout_seconds=timeout_seconds
    )
    elapsed_ns = time.monotonic_ns() - started

    _hash_output_files(output_records)

    return build_kernel_receipt(
        kernel=kernel,
        compile_dir=compile_dir,
        compile_params=compile_params,
        inputs=input_records,
        outputs=output_records,
        probe=probe_metadata,
        dispatch_command=command,
        dispatch_exit_code=exit_code,
        dispatch_stdout=stdout,
        dispatch_stderr=stderr,
        dispatch_timed_out=timed_out,
        dispatch_wallclock_ns=elapsed_ns,
        host_plan_path=host_plan_path,
        host_plan_hash=host_plan_hash,
        cmaddr=cmaddr,
        blocker=None,
    )


def write_kernel_receipt(
    *, receipt: dict[str, Any], out_dir: Path
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    path = out_dir / f"{receipt['kernel']}.json"
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_summary(
    *,
    out_dir: Path,
    receipts: list[dict[str, Any]],
    host_plan_path: Path,
    host_plan_hash: str,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schemaVersion": 1,
        "artifactKind": "doe_manifest_shape_per_kernel_dispatch_summary",
        "receiptClass": "manifest_shape_per_kernel_dispatch_summary",
        "hostPlanPath": _try_relative(host_plan_path),
        "hostPlanHash": host_plan_hash,
        "kernels": [
            {
                "kernel": r["kernel"],
                "verdict": r["verdict"],
                "blocker": r["blocker"],
                "dispatchExitCode": r["dispatchExitCode"],
                "dispatchTimedOut": r["dispatchTimedOut"],
                "dispatchWallclockNs": r["dispatchWallclockNs"],
                "totalInputBytes": r["totalInputBytes"],
                "totalOutputBytes": r["totalOutputBytes"],
                "outputDigest": r["outputDigest"],
                "probeFixturePath": (r.get("probe") or {}).get(
                    "fixturePath"
                ),
            }
            for r in receipts
        ],
        "totals": {
            "kernelCount": len(receipts),
            "boundCount": sum(
                1 for r in receipts if r["verdict"] == "bound"
            ),
            "blockedCount": sum(
                1 for r in receipts if r["verdict"] == "blocked"
            ),
        },
    }
    enforce_receipt_hash_spine(summary, repo_root=REPO_ROOT)
    path = out_dir / "summary.json"
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    args = parse_args()
    if args.jobs < 1:
        sys.stderr.write("manifest_kernel_probe_runner: --jobs must be >= 1\n")
        return 2
    if not args.host_plan.is_file():
        sys.stderr.write(
            f"manifest_kernel_probe_runner: host-plan absent at "
            f"{args.host_plan}\n"
        )
        return 2
    host_plan = json.loads(args.host_plan.read_text(encoding="utf-8"))
    host_plan_hash = _sha256_file(args.host_plan)
    targets = host_plan.get("compileTargets") or []
    if args.kernel:
        kernel_filter = set(args.kernel)
        targets = [t for t in targets if t.get("name") in kernel_filter]
        if not targets:
            sys.stderr.write(
                f"manifest_kernel_probe_runner: no targets matched "
                f"--kernel filter {sorted(kernel_filter)!r}\n"
            )
            return 2
    source_root = args.source_root or args.compile_root
    targets = order_targets(
        targets=[
            target for target in targets
            if isinstance(target, dict) and target.get("name")
        ],
        schedule=args.schedule,
        compile_root=args.compile_root,
        source_root=source_root,
    )

    receipts_by_kernel: dict[str, dict[str, Any]] = {}
    blocked_count = 0
    reused_count = 0

    def run_target(target: dict[str, Any]) -> tuple[str, dict[str, Any], bool]:
        kernel = str(target.get("name") or "")
        if args.resume:
            reusable = load_reusable_receipt(
                kernel=kernel,
                out_dir=args.out_dir,
                host_plan_hash=host_plan_hash,
                dry_run=args.dry_run,
                reuse_blocked=args.reuse_blocked,
            )
            if reusable is not None:
                return kernel, reusable, True
        receipt = run_one_kernel(
            kernel=kernel,
            target=target,
            compile_root=args.compile_root,
            source_root=source_root,
            probe_dir=args.probe_dir,
            host_plan_path=args.host_plan,
            host_plan_hash=host_plan_hash,
            out_dir=args.out_dir,
            cmaddr=args.cmaddr,
            timeout_seconds=args.timeout_seconds,
            cs_python=args.cs_python,
            adapter=args.adapter,
            dry_run=args.dry_run,
        )
        try:
            write_kernel_receipt(receipt=receipt, out_dir=args.out_dir)
        except ReceiptHashSpineError as err:
            raise RuntimeError(
                f"kernel {kernel!r} hash spine rejected emit: {err}"
            ) from err
        return kernel, receipt, False

    try:
        if args.jobs == 1:
            for target in targets:
                kernel, receipt, reused = run_target(target)
                receipts_by_kernel[kernel] = receipt
                if reused:
                    reused_count += 1
                if receipt["verdict"] == "blocked":
                    blocked_count += 1
        else:
            with ThreadPoolExecutor(max_workers=args.jobs) as executor:
                futures = {
                    executor.submit(run_target, target): str(target["name"])
                    for target in targets
                }
                for future in as_completed(futures):
                    kernel, receipt, reused = future.result()
                    receipts_by_kernel[kernel] = receipt
                    if reused:
                        reused_count += 1
                    if receipt["verdict"] == "blocked":
                        blocked_count += 1
    except RuntimeError as err:
        sys.stderr.write(f"manifest_kernel_probe_runner: {err}\n")
        return 2

    receipts = [
        receipts_by_kernel[str(target["name"])]
        for target in targets
        if str(target["name"]) in receipts_by_kernel
    ]

    try:
        write_summary(
            out_dir=args.out_dir,
            receipts=receipts,
            host_plan_path=args.host_plan,
            host_plan_hash=host_plan_hash,
        )
    except ReceiptHashSpineError as err:
        sys.stderr.write(
            f"manifest_kernel_probe_runner: summary hash spine rejected: "
            f"{err}\n"
        )
        return 2

    print(
        f"wrote {len(receipts)} per-kernel receipt(s) to {args.out_dir} "
        f"(blocked={blocked_count}, reused={reused_count}, jobs={args.jobs}, "
        f"schedule={args.schedule})"
    )
    return 1 if blocked_count else 0


if __name__ == "__main__":
    sys.exit(main())
