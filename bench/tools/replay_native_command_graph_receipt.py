#!/usr/bin/env python3
"""Replay-check native command graph receipts by recomputing the hash chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

try:
    from .build_native_command_graph_receipt import ROOT_HASH, stable_hash
except ImportError:  # pragma: no cover - script execution path
    from build_native_command_graph_receipt import ROOT_HASH, stable_hash


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, help="Native command graph receipt.")
    parser.add_argument(
        "--verify-files-root",
        default="",
        help="Resolve relative run/commands paths under this root and verify sha256 values.",
    )
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def resolve_path(path_text: str, verify_files_root: Path) -> Path:
    return verify_files_root.joinpath(*PurePosixPath(path_text).parts)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_linked_file(
    receipt: dict[str, Any],
    *,
    path_field: str,
    hash_field: str,
    unsafe_code: str,
    missing_code: str,
    mismatch_code: str,
    verify_files_root: Path | None,
) -> list[dict[str, str]]:
    if verify_files_root is None:
        return []
    path_text = receipt.get(path_field)
    if not isinstance(path_text, str) or not path_text:
        return [failure(missing_code, path_field, f"{path_field} is required")]
    if not safe_repo_path(path_text):
        return [failure(unsafe_code, path_field, f"{path_field} must be repo-relative")]
    expected_hash = receipt.get(hash_field)
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        return [failure(mismatch_code, hash_field, f"{hash_field} must be sha256 hex")]
    resolved = resolve_path(path_text, verify_files_root)
    if not resolved.is_file():
        return [failure(missing_code, path_field, f"file not found: {path_text}")]
    actual_hash = sha256_file(resolved)
    if actual_hash != expected_hash:
        return [failure(mismatch_code, hash_field, f"expected {actual_hash}, got {expected_hash}")]
    return []


def check_receipt(
    receipt: dict[str, Any],
    verify_files_root: Path | None = None,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    failures.extend(
        check_linked_file(
            receipt,
            path_field="runReceiptPath",
            hash_field="runReceiptSha256",
            unsafe_code="unsafe_run_receipt_path",
            missing_code="run_receipt_missing",
            mismatch_code="run_receipt_hash_mismatch",
            verify_files_root=verify_files_root,
        )
    )
    failures.extend(
        check_linked_file(
            receipt,
            path_field="commandsPath",
            hash_field="commandsSha256",
            unsafe_code="unsafe_commands_path",
            missing_code="commands_file_missing",
            mismatch_code="commands_hash_mismatch",
            verify_files_root=verify_files_root,
        )
    )
    commands = receipt.get("graph", {}).get("commands", [])
    if not isinstance(commands, list):
        failures.append(failure("missing_commands", "graph.commands", "commands must be an array"))
        return failures

    previous = ROOT_HASH
    submit_ids: set[int] = set()
    bind_groups: set[str] = set()
    for index, row in enumerate(commands):
        if not isinstance(row, dict):
            failures.append(failure("invalid_command_row", f"graph.commands[{index}]", "command row must be object"))
            continue
        if row.get("seq") != index:
            failures.append(failure("sequence_mismatch", f"graph.commands[{index}].seq", f"expected seq {index}"))
        if isinstance(row.get("submitId"), int):
            submit_ids.add(row["submitId"])
        row_bind_groups = row.get("bindGroupRefs", [])
        if isinstance(row_bind_groups, list):
            bind_groups.update(ref for ref in row_bind_groups if isinstance(ref, str))
        row_without_hash = {key: value for key, value in row.items() if key != "rowHash"}
        expected_hash = stable_hash(row_without_hash, previous)
        if row.get("rowHash") != expected_hash:
            failures.append(failure("row_hash_mismatch", f"graph.commands[{index}].rowHash", f"expected {expected_hash}"))
        previous = expected_hash

    trace_chain = receipt.get("traceChain", {})
    if not isinstance(trace_chain, dict) or trace_chain.get("terminalHash") != previous:
        failures.append(failure("terminal_hash_mismatch", "traceChain.terminalHash", f"expected {previous}"))
    summary = receipt.get("summary", {})
    if isinstance(summary, dict) and summary.get("commandCount") != len(commands):
        failures.append(failure("command_count_mismatch", "summary.commandCount", f"expected {len(commands)}"))
    if isinstance(summary, dict) and summary.get("submitCount") != len(submit_ids):
        failures.append(failure("submit_count_mismatch", "summary.submitCount", f"expected {len(submit_ids)}"))
    graph = receipt.get("graph", {})
    if isinstance(graph, dict) and graph.get("bindGroups") != sorted(bind_groups):
        failures.append(failure("bind_group_set_mismatch", "graph.bindGroups", f"expected {sorted(bind_groups)}"))
    return failures


def main() -> int:
    args = parse_args()
    verify_files_root = Path(args.verify_files_root).resolve() if args.verify_files_root else None
    failures = check_receipt(load_json(Path(args.receipt)), verify_files_root)
    report = {
        "schemaVersion": 1,
        "artifactKind": "native_command_graph_replay_check",
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: native command graph replay")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: native command graph replay")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
