#!/usr/bin/env python3
"""Build a concrete multi-target runtime execution plan for INT4 PLE HostPlans."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from int4ple_binding_metadata import (
    binding_metadata_by_symbol,
    compile_params_from_target,
    pe_arrays_from_metadata,
    target_phase,
)

_ELEMENTWISE_PHASE_VARIANT_KERNELS = frozenset({
    "rmsnorm",
    "residual",
    "gelu",
    "gelu_gated",
    "silu_gated",
    "sigmoid_gated",
})
_SUPPORTED_ELEMENTWISE_PHASES = frozenset({"prefill", "decode"})
_SUMMA_TARGETS = frozenset({"tiled", "tiled_31b", "ple_proj"})
PREFILL_Q4K_GEMV_PATTERN = "prefill_q4k_gemv"
_ROW_PARALLEL_TARGETS = frozenset({
    "rmsnorm_prefill",
    "residual_prefill",
    "gelu_prefill",
    "gelu_gated_prefill",
    "silu_gated_prefill",
    "sigmoid_gated_prefill",
})
_ROPE_TARGETS = frozenset({"rope", "rope_partial"})
_ATTENTION_TILED_TARGETS = frozenset({
    "attn_small",
    "attn_head256",
    "attn_head512",
})


def _resolve_phase_variant_target(
    *,
    kernel_name: str,
    phase: str,
    available_targets: dict[str, Any],
    launch_index: int,
    blockers: list[str],
    targets_metadata: dict[tuple[str, str], str] | None = None,
) -> str | None:
    """Remap an elementwise launch to its phase-specific compile target.

    rmsnorm/residual/gelu are compiled once per phase: the `_prefill` variant
    carries `width=attention_tokens` and the `_decode` variant carries
    `width=1`. Legacy elementwise launches without a phase pass through to the
    base target; launches with a phase must resolve to the matching variant.

    Non-elementwise kernels pass through unchanged.

    When `targets_metadata` (loaded from `compile/targets.metadata.json`) is
    provided, the (baseKernel, phase) → target name lookup uses the
    Zig-emitted truth instead of the legacy `f"{kernel_name}_{phase}"`
    suffix convention.
    """
    if kernel_name not in _ELEMENTWISE_PHASE_VARIANT_KERNELS:
        return kernel_name
    if not phase:
        return kernel_name
    if phase not in _SUPPORTED_ELEMENTWISE_PHASES:
        blockers.append(
            f"launch[{launch_index}].phase_variant_unsupported:"
            f"{kernel_name}:{phase}"
        )
        return None
    variant: str | None = None
    if targets_metadata is not None:
        variant = targets_metadata.get((kernel_name, phase))
    if variant is None:
        variant = f"{kernel_name}_{phase}"
    if variant not in available_targets:
        blockers.append(
            f"launch[{launch_index}].phase_variant_target_missing:{variant}"
        )
        return None
    return variant


def _load_targets_metadata(compile_root: Path) -> dict[tuple[str, str], str]:
    metadata_path = compile_root / "targets.metadata.json"
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    by_base_phase: dict[tuple[str, str], str] = {}
    for entry in payload.get("targets") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        base = str(entry.get("baseKernel") or "")
        phase = entry.get("phase")
        if not name or not base or not isinstance(phase, str) or not phase:
            continue
        by_base_phase[(base, phase)] = name
    return by_base_phase


def _target_by_name(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    targets = (plan.get("inputs") or {}).get("compileTargets") or []
    return {
        str(target.get("name")): target
        for target in targets
        if isinstance(target, dict) and target.get("name")
    }


def _target_pattern(target: dict[str, Any]) -> str:
    pattern = target.get("pattern")
    return str(pattern) if isinstance(pattern, str) and pattern else ""


def _runtime_scheduler(scheduler: dict[str, Any]) -> dict[str, Any]:
    host_plan = scheduler.get("hostPlan") or {}
    if isinstance(host_plan, dict):
        runtime_scheduler = host_plan.get("runtimeScheduler")
        if isinstance(runtime_scheduler, dict):
            return runtime_scheduler
    return {}


def _layout_path(compile_root: Path, target: dict[str, Any]) -> Path:
    raw = target.get("layout") or ""
    path = Path(str(raw))
    return path if path.is_absolute() else (compile_root / path)


def _compile_dir(compile_root: Path, target_name: str) -> Path:
    return compile_root / "compiled" / target_name


def _pe_program_path(compile_root: Path, target: dict[str, Any]) -> Path:
    raw = target.get("peProgram") or ""
    path = Path(str(raw))
    return path if path.is_absolute() else (compile_root / path)


def _parse_layout_exports(layout_path: Path) -> list[dict[str, Any]]:
    metadata_path = layout_path.with_suffix(".metadata.json")
    if metadata_path.is_file():
        return _layout_exports_from_metadata(metadata_path)
    return []


def _layout_exports_from_metadata(metadata_path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    exports: list[dict[str, Any]] = []
    for entry in payload.get("exports") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        type_str = str(entry.get("type") or "")
        kind = str(entry.get("kind") or "")
        if not name or not type_str or kind not in {"device_variable", "device_function"}:
            continue
        exports.append(
            {
                "name": name,
                "type": type_str,
                "kind": kind,
                "mutable": bool(entry.get("mutable") or False),
            }
        )
    return exports


def _resolve_size_expr(size_expr: str, params: dict[str, int]) -> int | None:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[+\-*()]", size_expr)
    substituted: list[str] = []
    for token in tokens:
        if token.isidentifier():
            if token not in params:
                return None
            substituted.append(str(params[token]))
        elif token.isdigit() or token in "+-*()":
            substituted.append(token)
        else:
            return None
    try:
        value = eval("".join(substituted), {"__builtins__": {}}, {})
    except Exception:
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _parse_pe_program_arrays(pe_program_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    metadata_path = pe_program_path.with_suffix(".metadata.json")
    if metadata_path.is_file():
        decls = _decls_from_metadata(metadata_path)
        return decls, _compile_time_from_metadata(metadata_path)
    return {}, {}


def _decls_from_metadata(metadata_path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    decls: dict[str, dict[str, Any]] = {}
    for entry in payload.get("variables") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        size_expr = str(entry.get("sizeExpr") or "")
        elem_type = str(entry.get("elemType") or "")
        if not name or not size_expr or not elem_type:
            continue
        decls[name] = {"sizeExpr": size_expr, "elemType": elem_type}
    for entry in payload.get("exports") or []:
        if not isinstance(entry, dict):
            continue
        symbol = str(entry.get("symbol") or "")
        backing = str(entry.get("backing") or "")
        size_expr = str(entry.get("sizeExpr") or "")
        elem_type = str(entry.get("elemType") or "")
        pointer = str(entry.get("pointer") or "")
        if not symbol or not size_expr or not elem_type or symbol in decls:
            continue
        decls[symbol] = {
            "sizeExpr": size_expr,
            "elemType": elem_type,
            "backingVariable": backing,
            "exportPointer": pointer,
        }
    return decls


def _compile_time_from_metadata(metadata_path: Path) -> dict[str, int]:
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    compile_time: dict[str, int] = {}
    for entry in payload.get("compileTimeConstants") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        expr = str(entry.get("expr") or "")
        if not name or not expr:
            continue
        resolved = _resolve_size_expr(expr, compile_time)
        if resolved is not None:
            compile_time[name] = resolved
    return compile_time


def _memcpy_data_type(elem_type: str) -> str:
    if elem_type in {"u16", "i16"}:
        return "MEMCPY_16BIT"
    return "MEMCPY_32BIT"


def _dtype_for_elem_type(elem_type: str) -> str:
    if elem_type == "u8":
        return "u32"
    if elem_type == "f16":
        return "f16"
    if elem_type in {"u16", "i16"}:
        return "u16"
    if elem_type in {"u32", "i32"}:
        return "u32"
    return "f32"


def _dtype_byte_width(dtype: str) -> int:
    if dtype in {"f16", "u16"}:
        return 2
    return 4


def _model_hidden_dim(runtime_config: dict[str, Any]) -> int:
    model = runtime_config.get("modelConfig") or {}
    try:
        return int(model.get("hiddenDim") or 0)
    except (TypeError, ValueError):
        return 0


def _model_ple_width(runtime_config: dict[str, Any]) -> int:
    model = runtime_config.get("modelConfig") or {}
    try:
        return int(model.get("pleWidth") or 0)
    except (TypeError, ValueError):
        return 0


def _int_field(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _summa_params(compile_params: dict[str, int]) -> dict[str, int] | None:
    p = _int_field(compile_params.get("P"))
    mt = _int_field(compile_params.get("Mt"))
    kt = _int_field(compile_params.get("Kt"))
    nt = _int_field(compile_params.get("Nt"))
    if p is None or mt is None or kt is None or nt is None:
        return None
    return {
        "gridWidth": p,
        "gridHeight": p,
        "tileRows": mt,
        "tileReduction": kt,
        "tileCols": nt,
        "paddedRows": p * mt,
        "paddedReduction": p * kt,
        "paddedCols": p * nt,
    }


def _summa_source_transform(
    *,
    symbol: str,
    role: str,
    target_name: str,
    target_pattern: str,
    compile_params: dict[str, int],
    runtime_config: dict[str, Any],
    item: dict[str, Any],
    dtype: str,
    weight_item: dict[str, Any] | None,
    source_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if target_pattern and target_pattern != "tiled_matmul":
        return source_transform
    if target_name not in _SUMMA_TARGETS:
        return source_transform
    params = _summa_params(compile_params)
    if params is None:
        return source_transform
    symbol_key = symbol.lower()
    if symbol_key == "a" and role == "activation":
        source_cols = _int_field(item.get("matrixCols"))
        if source_cols is None and target_name == "ple_proj":
            source_cols = _model_ple_width(runtime_config)
        if source_cols is None:
            source_cols = _model_hidden_dim(runtime_config)
        if source_cols is None or source_cols <= 0:
            return source_transform
        return {
            "kind": "logical_matrix_to_summa_tiles",
            "matrixRole": "a",
            "sourceDtype": dtype,
            "targetDtype": dtype,
            "sourceCols": source_cols,
            **params,
        }
    if symbol_key == "b" and role == "weight" and weight_item is not None:
        shape = _normalized_shape(weight_item.get("shape") or [])
        if len(shape) < 2:
            return source_transform
        if (source_transform or {}).get("kind") == "weight_matrix_to_summa_tiles":
            source_transform = source_transform.get("sourceTransform")
        nested = source_transform or {
            "kind": "none",
            "sourceDtype": str(weight_item.get("dtype") or ""),
            "targetDtype": "f32",
        }
        return {
            "kind": "weight_matrix_to_summa_tiles",
            "matrixRole": "b",
            "targetDtype": dtype,
            "sourceRows": shape[0],
            "sourceCols": shape[1],
            "sourceTransform": nested,
            **params,
        }
    return source_transform


def _summa_output_transform(
    *,
    symbol: str,
    target_name: str,
    target_pattern: str,
    compile_params: dict[str, int],
    item: dict[str, Any],
    dtype: str,
) -> dict[str, Any] | None:
    if target_pattern and target_pattern != "tiled_matmul":
        return None
    if target_name not in _SUMMA_TARGETS or symbol.lower() != "c":
        return None
    params = _summa_params(compile_params)
    output_cols = _int_field(item.get("matrixCols"))
    if params is None or output_cols is None:
        return None
    return {
        "kind": "summa_tiles_to_logical_matrix",
        "matrixRole": "c",
        "rowsFromInput": "a",
        "cols": output_cols,
        "sourceDtype": dtype,
        "targetDtype": dtype,
        **params,
    }


def _row_parallel_source_transform(
    *,
    symbol: str,
    role: str,
    target_name: str,
    target_geometry: dict[str, int],
    elements_per_pe: int,
    dtype: str,
    source_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if source_transform is not None:
        return source_transform
    if target_name not in _ROW_PARALLEL_TARGETS:
        return source_transform
    if role != "activation" or symbol not in {"input", "residual", "gate"}:
        return source_transform
    pe_count = int(target_geometry.get("peCount") or 0)
    if pe_count <= 1 or elements_per_pe <= 0:
        return source_transform
    return {
        "kind": "logical_matrix_to_pe_rows",
        "matrixRole": symbol,
        "sourceCols": elements_per_pe,
        "targetRows": pe_count,
        "sourceDtype": dtype,
        "targetDtype": dtype,
    }


def _row_parallel_output_transform(
    *,
    symbol: str,
    role: str,
    target_name: str,
    elements_per_pe: int,
    dtype: str,
    output_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if output_transform is not None:
        return output_transform
    if target_name not in _ROW_PARALLEL_TARGETS:
        return output_transform
    if role != "activation" or symbol not in {"output", "input"}:
        return output_transform
    if elements_per_pe <= 0:
        return output_transform
    return {
        "kind": "pe_rows_to_logical_matrix",
        "matrixRole": symbol,
        "rowsFromInput": "input",
        "cols": elements_per_pe,
        "sourceDtype": dtype,
        "targetDtype": dtype,
    }


def _rope_source_transform(
    *,
    symbol: str,
    role: str,
    target_name: str,
    compile_params: dict[str, int],
    item: dict[str, Any],
    dtype: str,
    source_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if source_transform is not None:
        return source_transform
    if target_name not in _ROPE_TARGETS:
        return source_transform
    if role != "activation" or symbol != "input":
        return source_transform
    source_cols = _int_field(item.get("matrixCols"))
    head_dim = _int_field(compile_params.get("head_dim"))
    target_rows = _int_field(compile_params.get("width"))
    if source_cols is None or head_dim is None or target_rows is None:
        return source_transform
    if min(source_cols, head_dim, target_rows) <= 0:
        return source_transform
    return {
        "kind": "logical_matrix_to_rope_pe_heads",
        "matrixRole": "input",
        "sourceCols": source_cols,
        "headDim": head_dim,
        "targetRows": target_rows,
        "sourceDtype": dtype,
        "targetDtype": dtype,
    }


def _rope_output_transform(
    *,
    symbol: str,
    role: str,
    target_name: str,
    compile_params: dict[str, int],
    item: dict[str, Any],
    dtype: str,
    output_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if output_transform is not None:
        return output_transform
    if target_name not in _ROPE_TARGETS:
        return output_transform
    if role != "activation" or symbol != "input":
        return output_transform
    cols = _int_field(item.get("matrixCols"))
    head_dim = _int_field(compile_params.get("head_dim"))
    target_rows = _int_field(compile_params.get("width"))
    if cols is None or head_dim is None or target_rows is None:
        return output_transform
    if min(cols, head_dim, target_rows) <= 0:
        return output_transform
    return {
        "kind": "rope_pe_heads_to_logical_matrix",
        "matrixRole": "input",
        "rowsFromInput": "input",
        "cols": cols,
        "headDim": head_dim,
        "targetRows": target_rows,
        "sourceDtype": dtype,
        "targetDtype": dtype,
    }


def _attention_tiled_params(
    compile_params: dict[str, int],
) -> dict[str, int] | None:
    width = _int_field(compile_params.get("width"))
    head_dim = _int_field(compile_params.get("head_dim"))
    q_len_per_pe = _int_field(compile_params.get("q_len_per_pe"))
    block_size = _int_field(compile_params.get("block_size"))
    if width is None or head_dim is None or q_len_per_pe is None or block_size is None:
        return None
    if min(width, head_dim, q_len_per_pe, block_size) <= 0:
        return None
    return {
        "targetRows": width,
        "headDim": head_dim,
        "queryRowsPerPe": q_len_per_pe,
        "kvRowsPerPe": block_size,
    }


def _attention_tiled_source_transform(
    *,
    symbol: str,
    role: str,
    target_name: str,
    compile_params: dict[str, int],
    item: dict[str, Any],
    dtype: str,
    source_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if source_transform is not None:
        return source_transform
    if target_name not in _ATTENTION_TILED_TARGETS:
        return source_transform
    if role != "activation":
        return source_transform
    symbol_key = symbol.lower()
    if symbol_key not in {"query", "key", "val", "value"}:
        return source_transform
    params = _attention_tiled_params(compile_params)
    source_cols = _int_field(item.get("matrixCols"))
    if params is None or source_cols is None or source_cols <= 0:
        return source_transform
    is_query = symbol_key == "query"
    return {
        "kind": (
            "logical_matrix_to_attention_query_rows"
            if is_query
            else "logical_matrix_to_attention_kv_rows"
        ),
        "matrixRole": symbol_key,
        "sourceCols": source_cols,
        "headDim": params["headDim"],
        "targetRows": params["targetRows"],
        "rowsPerPe": (
            params["queryRowsPerPe"] if is_query else params["kvRowsPerPe"]
        ),
        "sourceDtype": dtype,
        "targetDtype": dtype,
    }


def _attention_tiled_output_transform(
    *,
    symbol: str,
    role: str,
    target_name: str,
    compile_params: dict[str, int],
    item: dict[str, Any],
    dtype: str,
    output_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if output_transform is not None:
        return output_transform
    if target_name not in _ATTENTION_TILED_TARGETS:
        return output_transform
    if role != "activation" or symbol.lower() != "output":
        return output_transform
    params = _attention_tiled_params(compile_params)
    cols = _int_field(item.get("matrixCols"))
    if params is None or cols is None or cols <= 0:
        return output_transform
    return {
        "kind": "attention_query_rows_to_logical_matrix",
        "matrixRole": "output",
        "rowsFromInput": "query",
        "cols": cols,
        "headDim": params["headDim"],
        "targetRows": params["targetRows"],
        "rowsPerPe": params["queryRowsPerPe"],
        "sourceDtype": dtype,
        "targetDtype": dtype,
    }


def _dense_gemv_params(compile_params: dict[str, int]) -> dict[str, int] | None:
    width = _int_field(compile_params.get("width"))
    height = _int_field(compile_params.get("height"))
    out_dim = _int_field(compile_params.get("out_dim"))
    out_dim_per_pe = _int_field(compile_params.get("out_dim_per_pe"))
    in_dim_per_pe = _int_field(compile_params.get("in_dim_per_pe"))
    if None in {width, height, out_dim, out_dim_per_pe, in_dim_per_pe}:
        return None
    return {
        "width": int(width),
        "height": int(height),
        "outDim": int(out_dim),
        "outDimPerPe": int(out_dim_per_pe),
        "inDimPerPe": int(in_dim_per_pe),
    }


def _dense_gemv_source_transform(
    *,
    symbol: str,
    role: str,
    target_name: str,
    compile_params: dict[str, int],
    runtime_config: dict[str, Any],
    weight_item: dict[str, Any] | None,
    source_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if target_name != "lm_head_prefill":
        return source_transform
    params = _dense_gemv_params(compile_params)
    if params is None:
        return source_transform
    symbol_key = symbol.lower()
    if symbol_key == "activation" and role == "activation":
        hidden_dim = _model_hidden_dim(runtime_config)
        if hidden_dim <= 0:
            return source_transform
        return {
            "kind": "logical_vector_to_dense_gemv_activation_shards",
            "sourceDtype": "f16",
            "targetDtype": "f16",
            "sourceElements": hidden_dim,
            **params,
        }
    if symbol_key == "weight" and role == "weight" and weight_item is not None:
        shape = _normalized_shape(weight_item.get("shape") or [])
        if len(shape) < 2:
            return source_transform
        return {
            "kind": "tied_f16_embedding_to_dense_gemv_shards",
            "sourceDtype": str(weight_item.get("dtype") or ""),
            "targetDtype": "f16",
            "sourceRows": shape[0],
            "sourceCols": shape[1],
            "logicalCols": _model_hidden_dim(runtime_config),
            **params,
        }
    return source_transform


def _dense_gemv_output_transform(
    *,
    symbol: str,
    target_name: str,
    compile_params: dict[str, int],
) -> dict[str, Any] | None:
    if target_name != "lm_head_prefill" or symbol.lower() != "output":
        return None
    params = _dense_gemv_params(compile_params)
    if params is None:
        return None
    return {
        "kind": "dense_gemv_row_shards_to_logits",
        "sourceDtype": "f32",
        "targetDtype": "f32",
        **params,
    }


def _prefill_q4k_gemv_params(
    compile_params: dict[str, int],
) -> dict[str, int] | None:
    in_dim_per_pe = int(compile_params.get("in_dim_per_pe") or 0)
    out_dim_per_pe = int(compile_params.get("out_dim_per_pe") or 0)
    num_blocks_per_row = int(compile_params.get("num_blocks_per_row") or 0)
    output_pe_rows = int(
        compile_params.get("output_pe_rows") or compile_params.get("height") or 0
    )
    if min(in_dim_per_pe, out_dim_per_pe, num_blocks_per_row, output_pe_rows) <= 0:
        return None
    return {
        "inDimPerPe": in_dim_per_pe,
        "outDimPerPe": out_dim_per_pe,
        "numBlocksPerRow": num_blocks_per_row,
        "outputPeRows": output_pe_rows,
    }


def _prefill_q4k_gemv_source_transform(
    *,
    symbol: str,
    role: str,
    target_pattern: str,
    compile_params: dict[str, int],
    runtime_config: dict[str, Any],
    item: dict[str, Any],
    dtype: str,
    weight_item: dict[str, Any] | None,
    source_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if target_pattern != PREFILL_Q4K_GEMV_PATTERN:
        return source_transform
    params = _prefill_q4k_gemv_params(compile_params)
    if params is None:
        return source_transform
    symbol_key = symbol.lower()
    if symbol_key in {"activation", "a"} and role == "activation":
        source_cols = _int_field(item.get("matrixCols"))
        if source_cols is None:
            source_cols = _model_hidden_dim(runtime_config)
        if source_cols is None or source_cols <= 0:
            return source_transform
        return {
            "kind": "logical_matrix_to_prefill_q4k_gemv_activation_shards",
            "sourceDtype": dtype,
            "targetDtype": "f16",
            "sourceCols": source_cols,
            **params,
        }
    if symbol_key in {"weight", "b"} and role == "weight" and weight_item is not None:
        shape = _normalized_shape(weight_item.get("shape") or [])
        if len(shape) < 2:
            return source_transform
        return {
            "kind": "q4km_rowwise_to_prefill_q4k_gemv_weight_tiles",
            "sourceDtype": str(weight_item.get("dtype") or ""),
            "targetDtype": "u8_q4k",
            "sourceRows": shape[0],
            "sourceCols": shape[1],
            **params,
        }
    return source_transform


def _prefill_q4k_gemv_output_transform(
    *,
    symbol: str,
    target_pattern: str,
    compile_params: dict[str, int],
    item: dict[str, Any],
    dtype: str,
) -> dict[str, Any] | None:
    if target_pattern != PREFILL_Q4K_GEMV_PATTERN:
        return None
    if symbol.lower() not in {"output", "c"}:
        return None
    params = _prefill_q4k_gemv_params(compile_params)
    output_cols = _int_field(item.get("matrixCols"))
    if params is None or output_cols is None:
        return None
    return {
        "kind": "prefill_q4k_gemv_row_tiles_to_logical_matrix",
        "cols": output_cols,
        "sourceDtype": dtype,
        "targetDtype": dtype,
        **params,
    }


def _memcpy_element_count(elem_type: str, raw_element_count: int) -> int:
    if elem_type == "u8":
        return max(1, (raw_element_count + 3) // 4)
    return raw_element_count


def _target_geometry(
    target_name: str,
    compile_params: dict[str, int],
    runtime_config: dict[str, Any],
) -> dict[str, int]:
    runtime_pe_count = _grid_pe_count(runtime_config)
    width = int(compile_params.get("width") or 0)
    height = int(compile_params.get("height") or 0)
    if target_name in {
        "rope",
        "rmsnorm",
        "rmsnorm_prefill",
        "rmsnorm_decode",
        "final_norm_stable",
        "attn_head256",
        "attn_head512",
        "attn_decode",
        "gemv",
        "q4_widetile",
        "q4_decode_gemv",
        "sample",
    }:
        height = 1
    if target_name == "tiled":
        tiled_p = int(compile_params.get("P") or 0)
        width = tiled_p
        height = tiled_p
    if width <= 0:
        width = 1
    if height <= 0:
        height = 1
    pe_count = width * height
    return {
        "width": width,
        "height": height,
        "peCount": pe_count,
        "runtimePeCount": runtime_pe_count or pe_count,
    }


def _weight_span_byte_length(weight_item: dict[str, Any] | None) -> int | None:
    if weight_item is None:
        return None
    spans = weight_item.get("spans") or []
    if isinstance(spans, list) and spans:
        total = 0
        for span in spans:
            if not isinstance(span, dict):
                return None
            try:
                total += int(span.get("size") or 0)
            except (TypeError, ValueError):
                return None
        if total > 0:
            return total
    try:
        raw = int(weight_item.get("byteSize") or 0)
    except (TypeError, ValueError):
        raw = 0
    return raw or None


def _binding_materialization(
    *,
    item: dict[str, Any],
    target_name: str,
    target_pattern: str,
    compile_params: dict[str, int],
    pe_program_arrays: dict[str, dict[str, Any]],
    pe_program_compile_time: dict[str, int],
    target_geometry: dict[str, int],
    runtime_config: dict[str, Any],
    binding_metadata: dict[str, Any] | None = None,
    target_phase_name: str = "base",
) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "")
    role = str(item.get("role") or "")
    buffer = str(item.get("buffer") or "")
    weight_item = _weight_index(runtime_config).get(buffer.removeprefix("weight:"))
    state_item = _state_index(runtime_config).get(_state_root_name(buffer))
    compile_time = dict(pe_program_compile_time)
    compile_time.update(compile_params)
    compile_time.setdefault("chunk_size", 1024)
    decl = pe_program_arrays.get(symbol)
    if decl is not None:
        raw_elements_per_pe = _resolve_size_expr(str(decl["sizeExpr"]), compile_time)
        elem_type = str(decl["elemType"])
        elements_per_pe = (
            None
            if raw_elements_per_pe is None
            else _memcpy_element_count(elem_type, raw_elements_per_pe)
        )
    else:
        elements_per_pe = None
        elem_type = "u32" if role in {"tokenized_prompt", "generated_tokens", "position"} else "f32"
    if elements_per_pe is None:
        capacity = _buffer_capacity(
            buffer=buffer,
            role=role,
            runtime_config=runtime_config,
            weight_item=weight_item,
            state_item=state_item,
            decode_steps=_decode_step_count(_runtime_scheduler({"hostPlan": {"runtimeScheduler": {}}})),
        )
        planned_elements = capacity.get("plannedElementCount")
        if isinstance(planned_elements, int) and planned_elements > 0:
            elements_per_pe = max(
                1,
                planned_elements // max(1, target_geometry["peCount"]),
            )
        else:
            elements_per_pe = 1
    dtype = _dtype_for_elem_type(elem_type)
    if weight_item is not None:
        raw_source_transform = weight_item.get("sourceTransform")
        source_transform = (
            raw_source_transform
            if isinstance(raw_source_transform, dict)
            else None
        )
        if dtype == "f32" and str(weight_item.get("dtype") or "") == "f16":
            source_transform = {
                "kind": "f16_to_f32",
                "sourceDtype": "f16",
                "targetDtype": "f32",
            }
        elif dtype == "f32" and str(weight_item.get("dtype") or "") == "bf16":
            source_transform = {
                "kind": "bf16_to_f32",
                "sourceDtype": "bf16",
                "targetDtype": "f32",
            }
        elif dtype == "f32" and str(weight_item.get("dtype") or "") == "u8_q4k":
            source_transform = {
                "kind": "q4km_rowwise_to_f32",
                "sourceDtype": "u8_q4k",
                "targetDtype": "f32",
            }
        elif dtype == "f16" and str(weight_item.get("dtype") or "") == "f16":
            source_transform = {
                "kind": "f16_passthrough",
                "sourceDtype": "f16",
                "targetDtype": "f16",
            }
        elif dtype == "f16" and str(weight_item.get("dtype") or "") == "bf16":
            source_transform = {
                "kind": "bf16_to_f16",
                "sourceDtype": "bf16",
                "targetDtype": "f16",
            }
        elif dtype == "f16" and str(weight_item.get("dtype") or "") == "u8_q4k":
            source_transform = {
                "kind": "q4km_rowwise_to_f32",
                "sourceDtype": "u8_q4k",
                "targetDtype": "f32",
            }
        elif dtype == "u32" and str(weight_item.get("dtype") or "") == "u8_q4k":
            source_transform = {
                "kind": "u8_bytes_to_u32_words",
                "sourceDtype": "u8_q4k",
                "targetDtype": "u32",
            }
        span_byte_length = _weight_span_byte_length(weight_item)
    else:
        source_transform = None
        span_byte_length = None
    metadata_staging = (binding_metadata or {}).get("stagingTransform")
    source_transform = _summa_source_transform(
        symbol=symbol,
        role=role,
        target_name=target_name,
        target_pattern=target_pattern,
        compile_params=compile_params,
        runtime_config=runtime_config,
        item=item,
        dtype=dtype,
        weight_item=weight_item,
        source_transform=source_transform,
    )
    source_transform = _prefill_q4k_gemv_source_transform(
        symbol=symbol,
        role=role,
        target_pattern=target_pattern,
        compile_params=compile_params,
        runtime_config=runtime_config,
        item=item,
        dtype=dtype,
        weight_item=weight_item,
        source_transform=source_transform,
    )
    source_transform = _dense_gemv_source_transform(
        symbol=symbol,
        role=role,
        target_name=target_name,
        compile_params=compile_params,
        runtime_config=runtime_config,
        weight_item=weight_item,
        source_transform=source_transform,
    )
    source_transform = _row_parallel_source_transform(
        symbol=symbol,
        role=role,
        target_name=target_name,
        target_geometry=target_geometry,
        elements_per_pe=elements_per_pe,
        dtype=dtype,
        source_transform=source_transform,
    )
    source_transform = _rope_source_transform(
        symbol=symbol,
        role=role,
        target_name=target_name,
        compile_params=compile_params,
        item=item,
        dtype=dtype,
        source_transform=source_transform,
    )
    source_transform = _attention_tiled_source_transform(
        symbol=symbol,
        role=role,
        target_name=target_name,
        compile_params=compile_params,
        item=item,
        dtype=dtype,
        source_transform=source_transform,
    )
    if source_transform is None and isinstance(metadata_staging, dict):
        source_transform = metadata_staging
    output_transform = _summa_output_transform(
        symbol=symbol,
        target_name=target_name,
        target_pattern=target_pattern,
        compile_params=compile_params,
        item=item,
        dtype=dtype,
    )
    prefill_q4k_output_transform = _prefill_q4k_gemv_output_transform(
        symbol=symbol,
        target_pattern=target_pattern,
        compile_params=compile_params,
        item=item,
        dtype=dtype,
    )
    if prefill_q4k_output_transform is not None:
        output_transform = prefill_q4k_output_transform
    metadata_detile = (binding_metadata or {}).get("detileTransform")
    if output_transform is None and isinstance(metadata_detile, dict):
        output_transform = metadata_detile
    dense_output_transform = _dense_gemv_output_transform(
        symbol=symbol,
        target_name=target_name,
        compile_params=compile_params,
    )
    if dense_output_transform is not None:
        output_transform = dense_output_transform
    output_transform = _rope_output_transform(
        symbol=symbol,
        role=role,
        target_name=target_name,
        compile_params=compile_params,
        item=item,
        dtype=dtype,
        output_transform=output_transform,
    )
    output_transform = _attention_tiled_output_transform(
        symbol=symbol,
        role=role,
        target_name=target_name,
        compile_params=compile_params,
        item=item,
        dtype=dtype,
        output_transform=output_transform,
    )
    output_transform = _row_parallel_output_transform(
        symbol=symbol,
        role=role,
        target_name=target_name,
        elements_per_pe=elements_per_pe,
        dtype=dtype,
        output_transform=output_transform,
    )
    element_byte_width = _dtype_byte_width(dtype)
    planned_elements = elements_per_pe * target_geometry["peCount"]
    planned_bytes = planned_elements * element_byte_width
    if span_byte_length is not None and role == "weight":
        planned_bytes = span_byte_length
    materialization = {
        "buffer": buffer,
        "symbol": symbol,
        "role": role,
        "targetName": target_name,
        "targetGeometry": target_geometry,
        "dtype": dtype,
        "elemType": elem_type,
        "memcpyDataType": _memcpy_data_type(elem_type),
        "elementsPerPe": elements_per_pe,
        "elementByteWidth": element_byte_width,
        "plannedElementCount": planned_elements,
        "plannedByteLength": planned_bytes,
        "storageClass": _buffer_storage_class(buffer, role),
        "targetPhase": target_phase_name,
    }
    if binding_metadata:
        if isinstance(binding_metadata.get("bindingShape"), dict):
            materialization["bindingShape"] = binding_metadata["bindingShape"]
        if isinstance(binding_metadata.get("perPeShape"), dict):
            materialization["perPeShape"] = binding_metadata["perPeShape"]
        if binding_metadata.get("weightSource") is not None:
            materialization["weightSource"] = binding_metadata.get("weightSource")
    if weight_item is not None:
        materialization["weightMapping"] = {
            "weightKey": weight_item.get("weightKey") or weight_item.get("tensor"),
            "path": weight_item.get("path") or weight_item.get("shard"),
            "sha256": weight_item.get("sha256"),
            "byteOffset": int(weight_item.get("byteOffset") or weight_item.get("offsetBytes") or 0),
            "byteSize": int(weight_item.get("byteSize") or 0),
            "dtype": weight_item.get("dtype"),
            "shape": weight_item.get("shape") or [],
            "spans": weight_item.get("spans") or [],
        }
    if source_transform is not None:
        materialization["sourceTransform"] = source_transform
        materialization["stagingTransform"] = source_transform
    if output_transform is not None:
        materialization["outputTransform"] = output_transform
        materialization["detileTransform"] = output_transform
    if state_item is not None:
        materialization["stateOwnership"] = {
            "stateRoot": state_item.get("name"),
            "stateKind": state_item.get("kind"),
            "bytesPerPe": int(state_item.get("bytesPerPe") or 0),
        }
    return materialization



def _choose_launch_function(function_names: set[str]) -> str:
    if "compute" in function_names:
        return "compute"
    if len(function_names) == 1:
        return next(iter(function_names))
    return "pending_runtime_function_resolution"


def _buffers_by_launch(items: list[dict[str, Any]], key: str) -> dict[int, list[dict[str, Any]]]:
    by_launch: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        launch_index = item.get(key)
        if not isinstance(launch_index, int):
            continue
        by_launch.setdefault(launch_index, []).append(item)
    return by_launch


def _compile_params(compile_dir: Path) -> dict[str, int]:
    out_path = compile_dir / "out.json"
    if not out_path.is_file():
        return {}
    try:
        value = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    params = value.get("params") or {}
    if not isinstance(params, dict):
        return {}
    parsed: dict[str, int] = {}
    for key, raw in params.items():
        try:
            parsed[str(key)] = int(raw)
        except (TypeError, ValueError):
            continue
    return parsed


def _target_grid(compile_params: dict[str, int]) -> dict[str, int] | None:
    width = int(compile_params.get("width") or compile_params.get("P") or 0)
    height = int(compile_params.get("height") or compile_params.get("P") or 0)
    if width <= 0 or height <= 0:
        return None
    return {"width": width, "height": height, "peCount": width * height}


def _product(values: list[Any]) -> int | None:
    result = 1
    seen = False
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        result *= parsed
        seen = True
    return result if seen else None


def _normalized_shape(values: list[Any]) -> list[int]:
    parsed: list[int] = []
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            return []
        if item <= 0:
            return []
        parsed.append(item)
    return parsed


def _weight_index(runtime_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in runtime_config.get("weightMappings") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("weightKey") or item.get("tensor")
        if not isinstance(key, str) or not key:
            continue
        result[key] = item
    return result


def _state_index(runtime_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in runtime_config.get("stateBuffers") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            result[name] = item
    return result


def _state_root_name(buffer: str) -> str:
    if not buffer.startswith("state:"):
        return ""
    return buffer.removeprefix("state:").split(":", 1)[0]


def _grid_pe_count(runtime_config: dict[str, Any]) -> int | None:
    grid = (runtime_config.get("memoryPlan") or {}).get("grid") or {}
    try:
        width = int(grid.get("width") or 0)
        height = int(grid.get("height") or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width * height


def _decode_step_count(runtime_scheduler: dict[str, Any]) -> int:
    transcript = runtime_scheduler.get("transcriptCaptureSchedule") or {}
    try:
        return int(transcript.get("expectedActualDecodeSteps") or 0)
    except (TypeError, ValueError):
        return 0


def _buffer_storage_class(buffer: str, role: str) -> str:
    if buffer.startswith("weight:") or role == "weight":
        return "external_weight"
    if buffer.startswith("state:") or role in {"kv_cache", "position", "position_encoding", "uniform"}:
        return "persistent_state"
    if buffer.startswith("input:") or role == "tokenized_prompt":
        return "shared_input"
    if role == "generated_tokens":
        return "captured_output"
    if role == "logits":
        return "captured_output" if buffer.startswith("logits:") else "intermediate"
    return "intermediate"


def _buffer_dtype(
    *,
    role: str,
    weight_item: dict[str, Any] | None,
    state_item: dict[str, Any] | None,
) -> str:
    if weight_item is not None:
        return str(weight_item.get("dtype") or "unknown")
    if role in {"tokenized_prompt", "generated_tokens", "position"}:
        return "u32"
    if role == "weight":
        return "unknown"
    if role == "kv_cache":
        return "opaque"
    if role == "position_encoding":
        return "f32"
    if state_item is not None and str(state_item.get("kind") or "") == "position":
        return "u32"
    return "f32"


def _buffer_capacity(
    *,
    buffer: str,
    role: str,
    runtime_config: dict[str, Any],
    weight_item: dict[str, Any] | None,
    state_item: dict[str, Any] | None,
    decode_steps: int,
) -> dict[str, Any]:
    model = runtime_config.get("modelConfig") or {}
    try:
        hidden_dim = int(model.get("hiddenDim") or 0)
    except (TypeError, ValueError):
        hidden_dim = 0
    try:
        vocab_size = int(model.get("vocabSize") or model.get("pleVocabSize") or 0)
    except (TypeError, ValueError):
        vocab_size = 0
    try:
        max_seq_len = int(model.get("maxSeqLen") or 0)
    except (TypeError, ValueError):
        max_seq_len = 0
    grid_pe_count = _grid_pe_count(runtime_config)

    planned_elements: int | None = None
    planned_shape: list[int] = []
    planned_bytes: int | None = None
    capacity_source = "unknown"

    if weight_item is not None:
        planned_shape = _normalized_shape(weight_item.get("shape") or [])
        planned_elements = _product(planned_shape)
        try:
            planned_bytes = int(weight_item.get("byteSize") or 0) or None
        except (TypeError, ValueError):
            planned_bytes = None
        capacity_source = "runtime_weight_mapping"
    elif role == "activation":
        planned_elements = hidden_dim or None
        planned_shape = [hidden_dim] if hidden_dim > 0 else []
        planned_bytes = planned_elements * 4 if planned_elements is not None else None
        capacity_source = "model_hidden_dim"
    elif role == "logits":
        planned_elements = vocab_size or None
        planned_shape = [vocab_size] if vocab_size > 0 else []
        planned_bytes = planned_elements * 4 if planned_elements is not None else None
        capacity_source = "model_vocab_size"
    elif role == "generated_tokens":
        planned_elements = 1
        planned_shape = [1]
        planned_bytes = 4
        capacity_source = "single_generated_token"
    elif role == "tokenized_prompt":
        planned_elements = max_seq_len or None
        planned_shape = [max_seq_len] if max_seq_len > 0 else []
        planned_bytes = planned_elements * 4 if planned_elements is not None else None
        capacity_source = "model_max_seq_len"
    elif role in {"position", "uniform"}:
        planned_elements = 1
        planned_shape = [1]
        planned_bytes = 4
        capacity_source = "scalar_runtime_state"
    elif role == "position_encoding":
        planned_elements = max_seq_len or None
        planned_shape = [max_seq_len] if max_seq_len > 0 else []
        planned_bytes = planned_elements * 4 if planned_elements is not None else None
        capacity_source = "rope_table_seq_len"
    elif state_item is not None:
        try:
            bytes_per_pe = int(state_item.get("bytesPerPe") or 0)
        except (TypeError, ValueError):
            bytes_per_pe = 0
        if bytes_per_pe > 0 and grid_pe_count is not None:
            planned_bytes = bytes_per_pe * grid_pe_count
            capacity_source = "runtime_state_bytes_per_pe"
        elif buffer.startswith("state:kv_cache"):
            planned_elements = decode_steps or max_seq_len or None
            planned_shape = [planned_elements] if planned_elements is not None else []
            capacity_source = "decode_or_seq_capacity"
        elif str(state_item.get("kind") or "") == "position":
            planned_elements = 1
            planned_shape = [1]
            planned_bytes = 4
            capacity_source = "position_state_scalar"

    return {
        "plannedElementCount": planned_elements,
        "plannedShape": planned_shape,
        "plannedByteLength": planned_bytes,
        "capacitySource": capacity_source,
    }


def _append_unique(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)


def _buffer_plan(
    *,
    runtime_config: dict[str, Any],
    runtime_scheduler: dict[str, Any],
    launches: list[dict[str, Any]],
    executor_validator: dict[str, Any],
) -> dict[str, Any]:
    weights = _weight_index(runtime_config)
    states = _state_index(runtime_config)
    decode_steps = _decode_step_count(runtime_scheduler)
    buffers: dict[str, dict[str, Any]] = {}

    def ensure(buffer: str, role: str) -> dict[str, Any]:
        weight_item = weights.get(buffer.removeprefix("weight:")) if buffer.startswith("weight:") else None
        state_item = states.get(_state_root_name(buffer))
        entry = buffers.get(buffer)
        if entry is None:
            capacity = _buffer_capacity(
                buffer=buffer,
                role=role,
                runtime_config=runtime_config,
                weight_item=weight_item,
                state_item=state_item,
                decode_steps=decode_steps,
            )
            entry = {
                "buffer": buffer,
                "role": role,
                "dtype": _buffer_dtype(
                    role=role,
                    weight_item=weight_item,
                    state_item=state_item,
                ),
                "storageClass": _buffer_storage_class(buffer, role),
                "producerLaunchIndices": [],
                "consumerLaunchIndices": [],
                "producerTargetNames": [],
                "consumerTargetNames": [],
                "transcriptEmitterLaunchIndices": [],
                **capacity,
            }
            if weight_item is not None:
                entry["weightKey"] = weight_item.get("weightKey") or weight_item.get("tensor")
                entry["weightPath"] = weight_item.get("path") or weight_item.get("shard") or ""
                entry["weightSha256"] = weight_item.get("sha256") or ""
            if state_item is not None:
                entry["stateRoot"] = state_item.get("name")
                entry["stateKind"] = state_item.get("kind")
            buffers[buffer] = entry
        return entry

    ensure("input:prompt_token_ids", "tokenized_prompt")

    for launch in launches:
        if not isinstance(launch, dict):
            continue
        launch_index = int(launch.get("launchIndex") or 0)
        target_name = str(launch.get("kernelName") or "")
        for item in launch.get("inputs") or []:
            if not isinstance(item, dict):
                continue
            buffer = str(item.get("buffer") or "")
            role = str(item.get("role") or "")
            if not buffer or not role:
                continue
            entry = ensure(buffer, role)
            _append_unique(entry["consumerLaunchIndices"], launch_index)
            _append_unique(entry["consumerTargetNames"], target_name)
        for item in launch.get("outputs") or []:
            if not isinstance(item, dict):
                continue
            buffer = str(item.get("buffer") or "")
            role = str(item.get("role") or "")
            if not buffer or not role:
                continue
            entry = ensure(buffer, role)
            _append_unique(entry["producerLaunchIndices"], launch_index)
            _append_unique(entry["producerTargetNames"], target_name)

    transcript = runtime_scheduler.get("transcriptCaptureSchedule") or {}
    for emitter in transcript.get("emitters") or []:
        if not isinstance(emitter, dict):
            continue
        launch_index = emitter.get("launchIndex")
        buffer = str(emitter.get("buffer") or "")
        if buffer:
            entry = ensure(
                buffer,
                "generated_tokens"
                if emitter.get("kind") == "generated_token"
                else "logits",
            )
            if isinstance(launch_index, int):
                _append_unique(entry["transcriptEmitterLaunchIndices"], launch_index)
        logits_buffer = str(emitter.get("logitsBuffer") or "")
        if logits_buffer:
            entry = ensure(logits_buffer, "logits")
            if isinstance(launch_index, int):
                _append_unique(entry["transcriptEmitterLaunchIndices"], launch_index)

    serialized = sorted(buffers.values(), key=lambda item: item["buffer"])
    return {
        "sharedPromptBuffer": "input:prompt_token_ids",
        "declaredStateRoots": sorted(states.keys()),
        "producedBufferCount": int(executor_validator.get("producedBufferCount") or 0),
        "bufferCount": len(serialized),
        "activationBufferCount": sum(1 for item in serialized if item["role"] == "activation"),
        "logitBufferCount": sum(1 for item in serialized if item["role"] == "logits"),
        "tokenBufferCount": sum(1 for item in serialized if item["role"] == "generated_tokens"),
        "persistentStateBufferCount": sum(
            1 for item in serialized if item["storageClass"] == "persistent_state"
        ),
        "externalWeightBufferCount": sum(
            1 for item in serialized if item["storageClass"] == "external_weight"
        ),
        "buffers": serialized,
    }


def build_hostplan_execution_plan(
    *,
    plan: dict[str, Any],
    compile_root: Path,
    runtime_config: dict[str, Any],
    scheduler: dict[str, Any],
    executor_validator: dict[str, Any],
) -> dict[str, Any]:
    runtime_scheduler = _runtime_scheduler(scheduler)
    launches = runtime_scheduler.get("launches") or []
    blockers: list[str] = []

    if executor_validator.get("status") != "passed":
        blockers.append(
            f"executor_validator_not_passed:{executor_validator.get('status')}"
        )
    if runtime_scheduler.get("status") != "bound":
        blockers.append(f"runtime_scheduler_not_bound:{runtime_scheduler.get('status')}")
    if not isinstance(launches, list) or not launches:
        blockers.append("runtime_scheduler_launches_missing")
        launches = []

    targets = _target_by_name(plan)
    kv_by_launch = _buffers_by_launch(
        (runtime_scheduler.get("kvCacheSchedule") or {}).get("operations") or [],
        "launchIndex",
    )
    emitters_by_launch = _buffers_by_launch(
        (runtime_scheduler.get("transcriptCaptureSchedule") or {}).get("emitters") or [],
        "launchIndex",
    )

    targets_metadata = _load_targets_metadata(compile_root)
    target_sessions: dict[str, dict[str, Any]] = {}
    launch_records: list[dict[str, Any]] = []

    for launch in launches:
        if not isinstance(launch, dict):
            continue
        launch_index = int(launch.get("launchIndex") or len(launch_records))
        base_kernel_name = str(launch.get("kernelName") or "")
        target_name = _resolve_phase_variant_target(
            kernel_name=base_kernel_name,
            phase=str(launch.get("phase") or ""),
            available_targets=targets,
            launch_index=launch_index,
            blockers=blockers,
            targets_metadata=targets_metadata,
        )
        if target_name is None:
            continue
        target = targets.get(target_name)
        if target is None:
            blockers.append(f"launch[{launch_index}].target_missing:{target_name}")
            continue
        layout_path = _layout_path(compile_root, target)
        compile_dir = _compile_dir(compile_root, target_name)
        pe_program_path = _pe_program_path(compile_root, target)
        compile_params = _compile_params(compile_dir)
        compile_params.update(compile_params_from_target(target))
        target_pattern = _target_pattern(target) or str(launch.get("kernelPattern") or "")
        binding_metadata = binding_metadata_by_symbol(target)
        target_phase_name = target_phase(target)
        if binding_metadata:
            variable_exports = set(binding_metadata)
            function_exports = {"compute"}
            pe_program_arrays = pe_arrays_from_metadata(binding_metadata)
            pe_program_compile_time = {}
        else:
            exports = _parse_layout_exports(layout_path)
            pe_program_arrays, pe_program_compile_time = _parse_pe_program_arrays(
                pe_program_path
            )
            variable_exports = {
                str(item["name"])
                for item in exports
                if item.get("kind") == "device_variable"
            }
            function_exports = {
                str(item["name"])
                for item in exports
                if item.get("kind") == "device_function"
            }
        launch_function = _choose_launch_function(function_exports)
        target_geometry = _target_geometry(target_name, compile_params, runtime_config)
        if not variable_exports:
            blockers.append(f"target[{target_name}].layout_exports_missing")
        if launch_function == "pending_runtime_function_resolution":
            blockers.append(f"target[{target_name}].launch_function_unresolved")

        if target_name not in target_sessions:
            target_sessions[target_name] = {
                "targetName": target_name,
                "compileDir": str(compile_dir),
                "compileParams": compile_params,
                "layoutPath": str(layout_path),
                "launchFunction": launch_function,
                "targetGeometry": target_geometry,
                "exportedVariables": sorted(variable_exports),
                "exportedFunctions": sorted(function_exports),
                "grid": target_geometry,
                "launchCount": 0,
                "requiredInputSymbols": set(),
                "requiredOutputSymbols": set(),
            }
        session = target_sessions[target_name]
        session["launchCount"] += 1

        inputs = launch.get("inputs") or []
        outputs = launch.get("outputs") or []
        input_bindings: list[dict[str, Any]] = []
        output_bindings: list[dict[str, Any]] = []
        for item in inputs:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "")
            if symbol not in variable_exports:
                blockers.append(
                    f"launch[{launch_index}].input_symbol_not_exported:{target_name}.{symbol}"
                )
            session["requiredInputSymbols"].add(symbol)
            input_bindings.append(
                {
                    "symbol": symbol,
                    "buffer": item.get("buffer"),
                    "role": item.get("role"),
                    "access": item.get("access"),
                    "materialization": _binding_materialization(
                        item=item,
                        target_name=target_name,
                        target_pattern=target_pattern,
                        compile_params=compile_params,
                        pe_program_arrays=pe_program_arrays,
                        pe_program_compile_time=pe_program_compile_time,
                        target_geometry=target_geometry,
                        runtime_config=runtime_config,
                        binding_metadata=binding_metadata.get(symbol),
                        target_phase_name=target_phase_name,
                    ),
                }
            )
        for item in outputs:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "")
            if symbol not in variable_exports:
                blockers.append(
                    f"launch[{launch_index}].output_symbol_not_exported:{target_name}.{symbol}"
                )
            session["requiredOutputSymbols"].add(symbol)
            output_bindings.append(
                {
                    "symbol": symbol,
                    "buffer": item.get("buffer"),
                    "role": item.get("role"),
                    "access": item.get("access"),
                    "materialization": _binding_materialization(
                        item=item,
                        target_name=target_name,
                        target_pattern=target_pattern,
                        compile_params=compile_params,
                        pe_program_arrays=pe_program_arrays,
                        pe_program_compile_time=pe_program_compile_time,
                        target_geometry=target_geometry,
                        runtime_config=runtime_config,
                        binding_metadata=binding_metadata.get(symbol),
                        target_phase_name=target_phase_name,
                    ),
                }
            )

        kv_ops = kv_by_launch.get(launch_index, [])
        emitters = emitters_by_launch.get(launch_index, [])
        launch_records.append(
            {
                "launchIndex": launch_index,
                "hostPlanLaunchIndex": launch.get("hostPlanLaunchIndex"),
                "runtimeLaunchIndex": launch.get("runtimeLaunchIndex"),
                "phase": launch.get("phase"),
                "decodeStepIndex": launch.get("decodeStepIndex"),
                "kernelName": base_kernel_name,
                "kernelPattern": target_pattern,
                "targetName": target_name,
                "compileDir": str(compile_dir),
                "compileParams": compile_params,
                "layoutPath": str(layout_path),
                "launchFunction": launch_function,
                "targetGeometry": target_geometry,
                "inputBindings": input_bindings,
                "outputBindings": output_bindings,
                "kvOperationCount": len(kv_ops),
                "transcriptEmitterCount": len(emitters),
                "runtimeActions": [
                    {
                        "kind": "resolve_symbols",
                        "deviceFunction": launch_function,
                        "inputSymbolCount": len(input_bindings),
                        "outputSymbolCount": len(output_bindings),
                    },
                    {
                        "kind": "bind_inputs",
                        "count": len(input_bindings),
                    },
                    {
                        "kind": "launch",
                        "functionName": launch_function,
                    },
                    {
                        "kind": "capture_outputs",
                        "count": len(output_bindings),
                    },
                ],
            }
        )

    serialized_sessions = []
    for session in target_sessions.values():
        serialized_sessions.append(
            {
                **session,
                "requiredInputSymbols": sorted(session["requiredInputSymbols"]),
                "requiredOutputSymbols": sorted(session["requiredOutputSymbols"]),
            }
        )
    serialized_sessions.sort(key=lambda item: str(item["targetName"]))

    return {
        "schemaVersion": 1,
        "artifactKind": "int4ple_hostplan_execution_plan",
        "status": "planned" if not blockers else "blocked",
        "blockers": blockers,
        "targetSessionCount": len(serialized_sessions),
        "launchCount": len(launch_records),
        "targetSessions": serialized_sessions,
        "launches": launch_records,
        "bufferPlan": _buffer_plan(
            runtime_config=runtime_config,
            runtime_scheduler=runtime_scheduler,
            launches=launches,
            executor_validator=executor_validator,
        ),
    }
