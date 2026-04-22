#!/usr/bin/env python3
"""Build HostPlan host I/O layout metadata for INT4 PLE transcript runs."""

from __future__ import annotations

import hashlib
import json
from math import ceil
from pathlib import Path
from typing import Any

DTYPE_BYTES = {
    "bytes": 1,
    "f16": 2,
    "float32": 4,
    "u8_q4k": 1,
    "u8_q8": 1,
    "uint32": 4,
}

REQUIRED_ROLES = [
    "weight",
    "state",
    "tokenized_prompt",
    "logits_output",
    "generated_tokens_output",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(value: Any) -> str:
    data = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data + b"\n").hexdigest()


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return str(path.resolve())


def product(values: list[int]) -> int:
    total = 1
    for value in values:
        total *= int(value)
    return total


def grid(runtime_config: dict[str, Any]) -> dict[str, int]:
    raw = (runtime_config.get("memoryPlan") or {}).get("grid") or {}
    width = int(raw.get("width", 1))
    height = int(raw.get("height", 1))
    return {"width": max(width, 1), "height": max(height, 1)}


def full_roi(pe_grid: dict[str, int]) -> dict[str, int]:
    pe_count = pe_grid["width"] * pe_grid["height"]
    return {
        "x": 0,
        "y": 0,
        "width": pe_grid["width"],
        "height": pe_grid["height"],
        "peStart": 0,
        "peEnd": max(pe_count - 1, 0),
    }


def mapping_roi(mapping: dict[str, Any], pe_grid: dict[str, int]) -> dict[str, int]:
    roi = full_roi(pe_grid)
    pe_range = mapping.get("peRange") or []
    if len(pe_range) == 2:
        roi["peStart"] = int(pe_range[0])
        roi["peEnd"] = int(pe_range[1])
    return roi


def per_pe(total: int, pe_grid: dict[str, int]) -> int:
    pe_count = max(pe_grid["width"] * pe_grid["height"], 1)
    return int(ceil(max(total, 0) / pe_count))


def bytes_for_tensor(
    *,
    dtype: str,
    shape: list[int],
    declared_bytes: int | None = None,
) -> tuple[int, int]:
    total_elements = product(shape) if shape else 0
    if declared_bytes is not None:
        return total_elements, int(declared_bytes)
    return total_elements, total_elements * DTYPE_BYTES[dtype]


def weight_entry(
    mapping: dict[str, Any],
    pe_grid: dict[str, int],
) -> dict[str, Any]:
    dtype = str(mapping["dtype"])
    shape = [int(value) for value in mapping.get("shape") or []]
    declared_bytes = mapping.get("byteSize")
    total_elements, total_bytes = bytes_for_tensor(
        dtype=dtype,
        shape=shape,
        declared_bytes=int(declared_bytes)
        if isinstance(declared_bytes, int)
        else None,
    )
    name = str(mapping.get("weightKey") or mapping["tensor"])
    return {
        "name": f"weight:{name}",
        "bufferRole": "weight",
        "hostAction": "memcpy_h2d",
        "dtype": dtype,
        "peGrid": pe_grid,
        "roi": mapping_roi(mapping, pe_grid),
        "order": "row_major_pe_range",
        "elementsPerPe": per_pe(total_elements, pe_grid),
        "bytesPerPe": per_pe(total_bytes, pe_grid),
        "totalElements": total_elements,
        "totalBytes": total_bytes,
        "sourceIdentity": {
            "kind": "rdrr_weight_shard",
            "path": mapping["path"],
            "sha256": mapping["sha256"],
            "tensor": mapping["tensor"],
            "offsetBytes": int(mapping["offsetBytes"]),
            "synthetic": False,
        },
    }


def state_entry(
    state: dict[str, Any],
    pe_grid: dict[str, int],
) -> dict[str, Any]:
    bytes_per_pe = int(state["bytesPerPe"])
    pe_count = pe_grid["width"] * pe_grid["height"]
    return {
        "name": f"state:{state['name']}",
        "bufferRole": "state",
        "hostAction": "allocate_device",
        "dtype": "bytes",
        "peGrid": pe_grid,
        "roi": full_roi(pe_grid),
        "order": "row_major_pe_range",
        "elementsPerPe": bytes_per_pe,
        "bytesPerPe": bytes_per_pe,
        "totalElements": bytes_per_pe * pe_count,
        "totalBytes": bytes_per_pe * pe_count,
        "sourceIdentity": {
            "kind": "runtime_state_buffer",
            "source": str(state["kind"]),
            "synthetic": False,
        },
    }


def tokenized_prompt_entry(
    export: dict[str, Any],
    pe_grid: dict[str, int],
) -> dict[str, Any]:
    tokenized = export["tokenizedPrompt"]
    token_count = int(tokenized["tokenCount"])
    total_bytes = token_count * DTYPE_BYTES["uint32"]
    return {
        "name": "input:tokenized_prompt",
        "bufferRole": "tokenized_prompt",
        "hostAction": "memcpy_h2d",
        "dtype": "uint32",
        "peGrid": pe_grid,
        "roi": full_roi(pe_grid),
        "order": "host_linear",
        "elementsPerPe": per_pe(token_count, pe_grid),
        "bytesPerPe": per_pe(total_bytes, pe_grid),
        "totalElements": token_count,
        "totalBytes": total_bytes,
        "sourceIdentity": {
            "kind": "tokenized_prompt",
            "path": tokenized["path"],
            "sha256": tokenized["sha256"],
            "synthetic": False,
        },
    }


def logits_output_entry(
    export: dict[str, Any],
    pe_grid: dict[str, int],
) -> dict[str, Any]:
    tensor = export["tensorDigest"]
    shape = [int(value) for value in tensor.get("shape") or []]
    total_elements, total_bytes = bytes_for_tensor(
        dtype="float32",
        shape=shape,
        declared_bytes=int(tensor["byteLength"]),
    )
    return {
        "name": "output:final_logits",
        "bufferRole": "logits_output",
        "hostAction": "memcpy_d2h",
        "dtype": "float32",
        "peGrid": pe_grid,
        "roi": full_roi(pe_grid),
        "order": "host_linear",
        "elementsPerPe": per_pe(total_elements, pe_grid),
        "bytesPerPe": per_pe(total_bytes, pe_grid),
        "totalElements": total_elements,
        "totalBytes": total_bytes,
        "sourceIdentity": {
            "kind": "doppler_reference_tensor_contract",
            "path": tensor["path"],
            "sha256": tensor["sha256"],
            "tensor": tensor["name"],
            "synthetic": False,
        },
    }


def generated_tokens_output_entry(
    export: dict[str, Any],
    pe_grid: dict[str, int],
) -> dict[str, Any]:
    generated = (export.get("decodeTranscript") or {}).get("generatedTokenIds")
    if not isinstance(generated, dict):
        generated = {
            "path": "pending",
            "sha256": "pending",
            "tokenCount": 0,
        }
    token_count = int(generated.get("tokenCount") or 0)
    if token_count == 0:
        token_count = int(
            (export.get("decodeTranscript") or {}).get("actualDecodeSteps") or 0
        )
    total_bytes = token_count * DTYPE_BYTES["uint32"]
    return {
        "name": "output:generated_token_ids",
        "bufferRole": "generated_tokens_output",
        "hostAction": "memcpy_d2h",
        "dtype": "uint32",
        "peGrid": pe_grid,
        "roi": full_roi(pe_grid),
        "order": "host_linear",
        "elementsPerPe": per_pe(token_count, pe_grid),
        "bytesPerPe": per_pe(total_bytes, pe_grid),
        "totalElements": token_count,
        "totalBytes": total_bytes,
        "sourceIdentity": {
            "kind": "doppler_reference_generated_tokens_contract",
            "path": generated.get("path", "pending"),
            "sha256": generated.get("sha256", "pending"),
            "synthetic": False,
        },
    }


def build_host_io_layout(
    runtime_config: dict[str, Any],
    export: dict[str, Any],
) -> list[dict[str, Any]]:
    pe_grid = grid(runtime_config)
    entries: list[dict[str, Any]] = []
    entries.extend(
        weight_entry(mapping, pe_grid)
        for mapping in runtime_config.get("weightMappings") or []
    )
    entries.extend(
        state_entry(state, pe_grid)
        for state in runtime_config.get("stateBuffers") or []
    )
    entries.append(tokenized_prompt_entry(export, pe_grid))
    entries.append(logits_output_entry(export, pe_grid))
    entries.append(generated_tokens_output_entry(export, pe_grid))
    return entries


def coverage(
    *,
    runtime_config_path: Path,
    runtime_config: dict[str, Any],
    layout: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    covered = sorted(
        {
            str(entry["bufferRole"])
            for entry in layout
            if str(entry.get("bufferRole", "")) in REQUIRED_ROLES
        }
    )
    missing = [role for role in REQUIRED_ROLES if role not in covered]
    weight_count = len(runtime_config.get("weightMappings") or [])
    state_count = len(runtime_config.get("stateBuffers") or [])
    status = (
        "complete"
        if not missing and weight_count > 0 and state_count > 0
        else "incomplete"
    )
    return {
        "status": status,
        "runtimeConfigPath": rel(runtime_config_path, repo_root),
        "runtimeConfigSha256": sha256_file(runtime_config_path),
        "hostIoLayoutSha256": sha256_json(layout),
        "entryCount": len(layout),
        "requiredRoles": REQUIRED_ROLES,
        "coveredRoles": covered,
        "missingRoles": missing,
        "mappedWeightEntryCount": weight_count,
        "stateBufferEntryCount": state_count,
        "hostInputEntryCount": len(
            [
                entry
                for entry in layout
                if entry["hostAction"] == "memcpy_h2d"
            ]
        ),
        "hostOutputEntryCount": len(
            [
                entry
                for entry in layout
                if entry["hostAction"] == "memcpy_d2h"
            ]
        ),
    }


def attach_host_io_layout(
    runtime_config_path: Path,
    export: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    runtime_config = load_json(runtime_config_path)
    layout = build_host_io_layout(runtime_config, export)
    runtime_config["hostIoLayout"] = layout
    write_json(runtime_config_path, runtime_config)
    return coverage(
        runtime_config_path=runtime_config_path,
        runtime_config=runtime_config,
        layout=layout,
        repo_root=repo_root,
    )
