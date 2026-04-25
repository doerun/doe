#!/usr/bin/env python3
"""Structured HostPlan compile-target binding metadata helpers."""

from __future__ import annotations

from typing import Any


def target_phase(target: dict[str, Any]) -> str:
    metadata = target.get("metadata")
    if not isinstance(metadata, dict):
        return "base"
    phase = metadata.get("targetPhase")
    return str(phase) if isinstance(phase, str) and phase else "base"


def binding_metadata_by_symbol(target: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = target.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    bindings = metadata.get("bindings")
    if not isinstance(bindings, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in bindings:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        if isinstance(symbol, str) and symbol:
            result[symbol] = item
    return result


def compile_params_from_target(target: dict[str, Any]) -> dict[str, int]:
    raw = target.get("compileParams")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, int] = {}
    for key, value in raw.items():
        try:
            result[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return result


def pe_arrays_from_metadata(
    metadata_by_symbol: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for symbol, item in metadata_by_symbol.items():
        per_pe_shape = item.get("perPeShape")
        if not isinstance(per_pe_shape, dict):
            continue
        elements = per_pe_shape.get("elements")
        elem_type = item.get("elemType")
        if isinstance(elements, str) and elements and isinstance(elem_type, str):
            result[symbol] = {
                "sizeExpr": elements,
                "elemType": elem_type,
                "metadataSource": "zig_compile_target_metadata",
            }
    return result
