#!/usr/bin/env python3
"""Build deterministic native command graph receipts from run receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_HASH = "0" * 64
SUBMIT_ID_KEYS = ("submitId", "submit_id", "submitIndex", "submit_index", "submit")
BIND_GROUP_SCALAR_KEYS = (
    "bindGroup",
    "bind_group",
    "bindGroupId",
    "bind_group_id",
    "bindGroupHandle",
    "bind_group_handle",
)
BIND_GROUP_ARRAY_KEYS = ("bindGroups", "bind_groups", "bindGroupIds", "bind_group_ids")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-receipt", required=True, help="Native run receipt JSON.")
    parser.add_argument("--commands", required=True, help="Command JSON for the workload.")
    parser.add_argument("--out", required=True, help="Output command graph receipt.")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_or_absolute(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def stable_hash(payload: dict[str, Any], previous: str) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(previous.encode("ascii") + encoded).hexdigest()


def command_kind(command: dict[str, Any]) -> str:
    return str(command.get("kind") or command.get("command_kind") or "unknown")


def submit_id(command: dict[str, Any]) -> int:
    for key in SUBMIT_ID_KEYS:
        if key in command:
            value = int(command[key])
            if value < 0:
                raise ValueError(f"{key} must be non-negative")
            return value
    return 0


def is_bind_group_key(key: str) -> bool:
    return key in BIND_GROUP_SCALAR_KEYS or key in BIND_GROUP_ARRAY_KEYS


def bind_group_ref(value: Any) -> str | None:
    if isinstance(value, (int, str)):
        return f"bind-group:{value}"
    if isinstance(value, dict):
        for key in ("id", "handle", "label"):
            candidate = value.get(key)
            if isinstance(candidate, (int, str)):
                return f"bind-group:{candidate}"
    return None


def collect_bind_group_refs(command: dict[str, Any]) -> list[str]:
    refs: set[str] = set()
    for key in BIND_GROUP_SCALAR_KEYS:
        ref = bind_group_ref(command.get(key))
        if ref:
            refs.add(ref)
    for key in BIND_GROUP_ARRAY_KEYS:
        values = command.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            ref = bind_group_ref(value)
            if ref:
                refs.add(ref)
    return sorted(refs)


def collect_resource_refs(command: dict[str, Any]) -> list[str]:
    refs: set[str] = set()
    for key, value in command.items():
        if is_bind_group_key(key):
            continue
        if key.endswith("_handle") or key.endswith("Handle"):
            refs.add(f"handle:{value}")
        elif key in {"buffer", "src", "dst", "texture", "sampler"} and isinstance(value, (int, str)):
            refs.add(f"{key}:{value}")
    return sorted(refs)


def pipeline_id(command: dict[str, Any]) -> str | None:
    kernel = command.get("kernel") or command.get("kernel_name")
    if isinstance(kernel, str) and kernel:
        return f"kernel:{kernel}"
    mode = command.get("pipelineMode")
    if isinstance(mode, str) and mode:
        return f"pipeline-mode:{mode}"
    return None


def dispatch_shape(kind: str, command: dict[str, Any]) -> dict[str, int] | None:
    if "dispatch" not in kind:
        return None
    return {
        "x": int(command.get("x", command.get("workgroupsX", 1))),
        "y": int(command.get("y", command.get("workgroupsY", 1))),
        "z": int(command.get("z", command.get("workgroupsZ", 1))),
    }


def normalize_command(seq: int, command: dict[str, Any], previous_hash: str) -> tuple[dict[str, Any], str]:
    kind = command_kind(command)
    row = {
        "seq": seq,
        "submitId": submit_id(command),
        "kind": kind,
        "resourceRefs": collect_resource_refs(command),
        "bindGroupRefs": collect_bind_group_refs(command),
        "pipelineId": pipeline_id(command),
        "dispatch": dispatch_shape(kind, command),
        "bytes": int(command["bytes"]) if "bytes" in command else None,
    }
    row_hash = stable_hash(row, previous_hash)
    row["rowHash"] = row_hash
    return row, row_hash


def build_graph(commands: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    buffers: set[str] = set()
    textures: set[str] = set()
    pipelines: set[str] = set()
    bind_groups: set[str] = set()
    terminal = ROOT_HASH
    for seq, command in enumerate(commands):
        row, terminal = normalize_command(seq, command, terminal)
        rows.append(row)
        bind_groups.update(row["bindGroupRefs"])
        for ref in row["resourceRefs"]:
            if command_kind(command).startswith("texture") or "texture" in command_kind(command):
                textures.add(ref)
            else:
                buffers.add(ref)
        if row["pipelineId"]:
            pipelines.add(row["pipelineId"])
    return (
        {
            "buffers": sorted(buffers),
            "textures": sorted(textures),
            "pipelines": sorted(pipelines),
            "bindGroups": sorted(bind_groups),
            "commands": rows,
        },
        {"rootHash": ROOT_HASH, "terminalHash": terminal},
    )


def build_receipt(
    *,
    run_receipt: dict[str, Any],
    run_receipt_path: Path,
    commands: list[dict[str, Any]],
    commands_path: Path,
) -> dict[str, Any]:
    graph, trace_chain = build_graph(commands)
    workload = run_receipt.get("workload", {})
    summary = {
        "commandCount": len(graph["commands"]),
        "submitCount": len({row["submitId"] for row in graph["commands"]}),
        "dispatchCount": sum(1 for row in graph["commands"] if "dispatch" in row["kind"]),
        "drawCount": sum(1 for row in graph["commands"] if row["kind"].startswith("draw")),
        "copyCount": sum(1 for row in graph["commands"] if "copy" in row["kind"]),
        "resourceCount": len(set(graph["buffers"]) | set(graph["textures"]) | set(graph["bindGroups"])),
    }
    return {
        "schemaVersion": 2,
        "artifactKind": "native_command_graph_receipt",
        "runReceiptPath": relative_or_absolute(run_receipt_path),
        "runReceiptSha256": sha256_file(run_receipt_path),
        "commandsPath": relative_or_absolute(commands_path),
        "commandsSha256": sha256_file(commands_path),
        "workload": {
            "id": str(workload.get("id", "unknown")),
            "domain": str(workload.get("domain", "unknown")),
        },
        "runtimeIdentity": run_receipt.get("runtimeIdentity", {}),
        "graph": graph,
        "traceChain": trace_chain,
        "summary": summary,
    }


def main() -> int:
    args = parse_args()
    run_receipt_path = Path(args.run_receipt)
    commands_path = Path(args.commands)
    commands = load_json(commands_path)
    if not isinstance(commands, list) or not all(isinstance(item, dict) for item in commands):
        raise ValueError("commands must be an array of objects")
    receipt = build_receipt(
        run_receipt=load_json(run_receipt_path),
        run_receipt_path=run_receipt_path,
        commands=commands,
        commands_path=commands_path,
    )
    Path(args.out).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
