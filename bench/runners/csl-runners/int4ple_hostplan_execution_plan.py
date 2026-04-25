#!/usr/bin/env python3
"""Build a concrete multi-target runtime execution plan for INT4 PLE HostPlans."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_EXPORT_NAME_RE = re.compile(
    r"""@export_name\(
        \s*"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"\s*,\s*
        (?P<type>[^,\)]+(?:\([^\)]*\)[^,\)]*)?)
        (?:\s*,\s*(?P<mutable>true|false))?
        \s*\)""",
    re.VERBOSE,
)

_PE_PROGRAM_VAR_RE = re.compile(
    r"""var\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*
        \[\s*(?P<size_expr>[^\]]+?)\s*\]
        \s*(?P<elem_type>[A-Za-z_][A-Za-z0-9_]*)""",
    re.VERBOSE,
)

_PE_PROGRAM_ZEROS_RE = re.compile(
    r"""var\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*
        @zeros\(\s*
        \[\s*(?P<size_expr>[^\]]+?)\s*\]
        \s*(?P<elem_type>[A-Za-z_][A-Za-z0-9_]*)\s*
        \)""",
    re.VERBOSE,
)

_PE_PROGRAM_CONST_OR_PARAM_RE = re.compile(
    r"""(?P<kind>const|param)\s+
        (?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*
        [A-Za-z_][A-Za-z0-9_]*\s*=\s*
        (?P<expr>[^;\n]+?)\s*;""",
    re.VERBOSE,
)

_PE_PROGRAM_PTR_RE = re.compile(
    r"""var\s+(?P<ptr>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*
        \[\s*\*\s*\]\s*(?P<elem_type>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*
        &(?P<backing>[A-Za-z_][A-Za-z0-9_]*)\s*;""",
    re.VERBOSE,
)

_PE_PROGRAM_EXPORT_SYMBOL_RE = re.compile(
    r"""@export_symbol\(\s*
        (?P<ptr>[A-Za-z_][A-Za-z0-9_]*)\s*,\s*
        "(?P<symbol>[A-Za-z_][A-Za-z0-9_]*)"\s*
        \)""",
    re.VERBOSE,
)


_ELEMENTWISE_PHASE_VARIANT_KERNELS = frozenset({"rmsnorm", "residual", "gelu"})
_SUPPORTED_ELEMENTWISE_PHASES = frozenset({"prefill", "decode"})
_SUMMA_TARGETS = frozenset({"tiled", "lm_head_prefill_stable"})


def _resolve_phase_variant_target(
    *,
    kernel_name: str,
    phase: str,
    available_targets: dict[str, Any],
    launch_index: int,
    blockers: list[str],
) -> str | None:
    """Remap an elementwise launch to its phase-specific compile target.

    rmsnorm/residual/gelu are compiled once per phase: the `_prefill` variant
    carries `width=attention_tokens` and the `_decode` variant carries
    `width=1`. Legacy elementwise launches without a phase pass through to the
    base target; launches with a phase must resolve to the matching variant.

    Non-elementwise kernels pass through unchanged.
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
    variant = f"{kernel_name}_{phase}"
    if variant not in available_targets:
        blockers.append(
            f"launch[{launch_index}].phase_variant_target_missing:{variant}"
        )
        return None
    return variant


def _target_by_name(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    targets = (plan.get("inputs") or {}).get("compileTargets") or []
    return {
        str(target.get("name")): target
        for target in targets
        if isinstance(target, dict) and target.get("name")
    }


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
    try:
        source = layout_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    exports: list[dict[str, Any]] = []
    for match in _EXPORT_NAME_RE.finditer(source):
        raw_type = match.group("type").strip()
        is_function = raw_type.startswith("fn") or "fn(" in raw_type
        exports.append(
            {
                "name": match.group("name"),
                "type": raw_type,
                "kind": "device_function" if is_function else "device_variable",
                "mutable": (match.group("mutable") == "true"),
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
    try:
        source = pe_program_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}, {}
    decls: dict[str, dict[str, Any]] = {}
    for pattern in (_PE_PROGRAM_VAR_RE, _PE_PROGRAM_ZEROS_RE):
        for match in pattern.finditer(source):
            name = match.group("name")
            if name in decls:
                continue
            decls[name] = {
                "sizeExpr": match.group("size_expr").strip(),
                "elemType": match.group("elem_type"),
            }
    pointers: dict[str, str] = {}
    for match in _PE_PROGRAM_PTR_RE.finditer(source):
        pointers[match.group("ptr")] = match.group("backing")
    for match in _PE_PROGRAM_EXPORT_SYMBOL_RE.finditer(source):
        symbol = match.group("symbol")
        backing = pointers.get(match.group("ptr"), "")
        backing_decl = decls.get(backing)
        if backing_decl is not None and symbol not in decls:
            decls[symbol] = {
                **backing_decl,
                "backingVariable": backing,
                "exportPointer": match.group("ptr"),
            }
    compile_time: dict[str, int] = {}
    for match in _PE_PROGRAM_CONST_OR_PARAM_RE.finditer(source):
        resolved = _resolve_size_expr(match.group("expr").strip(), compile_time)
        if resolved is not None:
            compile_time[match.group("name")] = resolved
    return decls, compile_time


def _memcpy_data_type(elem_type: str) -> str:
    if elem_type in {"f16", "u16", "i16"}:
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
    compile_params: dict[str, int],
    runtime_config: dict[str, Any],
    item: dict[str, Any],
    weight_item: dict[str, Any] | None,
    source_transform: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if target_name not in _SUMMA_TARGETS:
        return source_transform
    params = _summa_params(compile_params)
    if params is None:
        return source_transform
    symbol_key = symbol.lower()
    if symbol_key == "a" and role == "activation":
        source_cols = _int_field(item.get("matrixCols")) or _model_hidden_dim(runtime_config)
        if source_cols is None or source_cols <= 0:
            return source_transform
        return {
            "kind": "logical_matrix_to_summa_tiles",
            "matrixRole": "a",
            "sourceDtype": "f32",
            "targetDtype": "f32",
            "sourceCols": source_cols,
            **params,
        }
    if symbol_key == "b" and role == "weight" and weight_item is not None:
        shape = _normalized_shape(weight_item.get("shape") or [])
        if len(shape) < 2:
            return source_transform
        nested = source_transform or {
            "kind": "none",
            "sourceDtype": str(weight_item.get("dtype") or ""),
            "targetDtype": "f32",
        }
        return {
            "kind": "weight_matrix_to_summa_tiles",
            "matrixRole": "b",
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
    compile_params: dict[str, int],
    item: dict[str, Any],
) -> dict[str, Any] | None:
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
        "sourceDtype": "f32",
        "targetDtype": "f32",
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
        "lm_head_gemv_stable",
        "sample",
    }:
        height = 1
    if target_name in {"tiled", "lm_head_prefill_stable"}:
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
    compile_params: dict[str, int],
    pe_program_arrays: dict[str, dict[str, Any]],
    pe_program_compile_time: dict[str, int],
    target_geometry: dict[str, int],
    runtime_config: dict[str, Any],
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
    source_transform = _summa_source_transform(
        symbol=symbol,
        role=role,
        target_name=target_name,
        compile_params=compile_params,
        runtime_config=runtime_config,
        item=item,
        weight_item=weight_item,
        source_transform=source_transform,
    )
    output_transform = _summa_output_transform(
        symbol=symbol,
        target_name=target_name,
        compile_params=compile_params,
        item=item,
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
    }
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
    if output_transform is not None:
        materialization["outputTransform"] = output_transform
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
        if not exports:
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
                        compile_params=compile_params,
                        pe_program_arrays=pe_program_arrays,
                        pe_program_compile_time=pe_program_compile_time,
                        target_geometry=target_geometry,
                        runtime_config=runtime_config,
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
                        compile_params=compile_params,
                        pe_program_arrays=pe_program_arrays,
                        pe_program_compile_time=pe_program_compile_time,
                        target_geometry=target_geometry,
                        runtime_config=runtime_config,
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
