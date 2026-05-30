#!/usr/bin/env python3
"""Tests for native command graph receipts and replay checks."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import jsonschema

from bench.tools import build_native_command_graph_receipt as build_graph
from bench.tools import replay_native_command_graph_receipt as replay_graph


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_RECEIPT_PATH = REPO_ROOT / "examples" / "run-receipt.sample.json"
COMMANDS_PATH = REPO_ROOT / "examples" / "kernel_dispatch_commands.json"
SCHEMA_PATH = REPO_ROOT / "config" / "native-command-graph-receipt.schema.json"
SAMPLE_PATH = REPO_ROOT / "examples" / "native-command-graph-receipt.sample.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_native_command_graph_receipt_binds_commands_and_runtime_identity() -> None:
    commands = json.loads(COMMANDS_PATH.read_text(encoding="utf-8"))
    receipt = build_graph.build_receipt(
        run_receipt=_load(RUN_RECEIPT_PATH),
        run_receipt_path=RUN_RECEIPT_PATH,
        commands=commands,
        commands_path=COMMANDS_PATH,
    )

    jsonschema.Draft202012Validator(_load(SCHEMA_PATH)).validate(receipt)
    assert receipt["runReceiptPath"] == "examples/run-receipt.sample.json"
    assert receipt["commandsPath"] == "examples/kernel_dispatch_commands.json"
    assert receipt["summary"]["commandCount"] == len(commands)
    assert receipt["summary"]["submitCount"] == 1
    assert receipt["summary"]["dispatchCount"] == 2
    assert receipt["summary"]["copyCount"] == 1
    assert receipt["runtimeIdentity"]["executionBackend"] == "doe_vulkan"
    assert replay_graph.check_receipt(receipt) == []


def test_native_command_graph_sample_replays() -> None:
    sample = _load(SAMPLE_PATH)

    jsonschema.Draft202012Validator(_load(SCHEMA_PATH)).validate(sample)
    assert replay_graph.check_receipt(sample) == []
    assert replay_graph.check_receipt(sample, REPO_ROOT) == []


def test_native_command_graph_receipt_records_submit_and_bind_group_identity() -> None:
    commands = [
        {
            "kind": "kernel_dispatch",
            "kernel": "skin_mesh",
            "x": 1,
            "bind_group_handle": 7,
            "submitId": 2,
        },
        {
            "kind": "texture_copy",
            "src_handle": 1024,
            "dst_handle": 2048,
            "bindGroups": ["frame", {"id": "material"}],
            "submit_id": 3,
            "bytes": 512,
        },
    ]
    receipt = build_graph.build_receipt(
        run_receipt=_load(RUN_RECEIPT_PATH),
        run_receipt_path=RUN_RECEIPT_PATH,
        commands=commands,
        commands_path=COMMANDS_PATH,
    )

    jsonschema.Draft202012Validator(_load(SCHEMA_PATH)).validate(receipt)
    assert receipt["summary"]["submitCount"] == 2
    assert receipt["graph"]["bindGroups"] == [
        "bind-group:7",
        "bind-group:frame",
        "bind-group:material",
    ]
    assert receipt["graph"]["commands"][0]["submitId"] == 2
    assert receipt["graph"]["commands"][0]["bindGroupRefs"] == ["bind-group:7"]
    assert receipt["graph"]["commands"][1]["submitId"] == 3
    assert receipt["graph"]["commands"][1]["bindGroupRefs"] == [
        "bind-group:frame",
        "bind-group:material",
    ]
    assert replay_graph.check_receipt(receipt) == []


def test_native_command_graph_replay_rejects_row_hash_drift() -> None:
    receipt = build_graph.build_receipt(
        run_receipt=_load(RUN_RECEIPT_PATH),
        run_receipt_path=RUN_RECEIPT_PATH,
        commands=json.loads(COMMANDS_PATH.read_text(encoding="utf-8")),
        commands_path=COMMANDS_PATH,
    )
    receipt["graph"]["commands"][0]["kind"] = "mutated"

    failures = replay_graph.check_receipt(receipt)

    assert failures[0]["code"] == "row_hash_mismatch"
    assert failures[0]["path"] == "graph.commands[0].rowHash"


def test_native_command_graph_replay_rejects_sequence_drift() -> None:
    receipt = build_graph.build_receipt(
        run_receipt=_load(RUN_RECEIPT_PATH),
        run_receipt_path=RUN_RECEIPT_PATH,
        commands=json.loads(COMMANDS_PATH.read_text(encoding="utf-8")),
        commands_path=COMMANDS_PATH,
    )
    receipt["graph"]["commands"][1]["seq"] = 7

    codes = {item["code"] for item in replay_graph.check_receipt(receipt)}

    assert "sequence_mismatch" in codes
    assert "row_hash_mismatch" in codes


def test_native_command_graph_replay_rejects_bind_group_summary_drift() -> None:
    receipt = build_graph.build_receipt(
        run_receipt=_load(RUN_RECEIPT_PATH),
        run_receipt_path=RUN_RECEIPT_PATH,
        commands=[
            {
                "kind": "kernel_dispatch",
                "kernel": "skin_mesh",
                "bindGroup": "frame",
                "submitId": 1,
            },
        ],
        commands_path=COMMANDS_PATH,
    )
    receipt["graph"]["bindGroups"] = []
    receipt["summary"]["submitCount"] = 0

    codes = {item["code"] for item in replay_graph.check_receipt(receipt)}

    assert "bind_group_set_mismatch" in codes
    assert "submit_count_mismatch" in codes


def test_native_command_graph_replay_rejects_unsafe_linked_paths() -> None:
    receipt = build_graph.build_receipt(
        run_receipt=_load(RUN_RECEIPT_PATH),
        run_receipt_path=RUN_RECEIPT_PATH,
        commands=json.loads(COMMANDS_PATH.read_text(encoding="utf-8")),
        commands_path=COMMANDS_PATH,
    )
    receipt["runReceiptPath"] = "../run-receipt.sample.json"
    receipt["commandsPath"] = "/tmp/kernel_dispatch_commands.json"

    failures = replay_graph.check_receipt(receipt, REPO_ROOT)

    assert {
        "code": "unsafe_run_receipt_path",
        "path": "runReceiptPath",
        "message": "runReceiptPath must be repo-relative",
    } in failures
    assert {
        "code": "unsafe_commands_path",
        "path": "commandsPath",
        "message": "commandsPath must be repo-relative",
    } in failures


def test_native_command_graph_replay_rejects_linked_file_hash_drift() -> None:
    receipt = build_graph.build_receipt(
        run_receipt=_load(RUN_RECEIPT_PATH),
        run_receipt_path=RUN_RECEIPT_PATH,
        commands=json.loads(COMMANDS_PATH.read_text(encoding="utf-8")),
        commands_path=COMMANDS_PATH,
    )
    receipt["commandsSha256"] = "0" * 64

    assert {
        "code": "commands_hash_mismatch",
        "path": "commandsSha256",
        "message": f"expected {build_graph.sha256_file(COMMANDS_PATH)}, got {'0' * 64}",
    } in replay_graph.check_receipt(receipt, REPO_ROOT)


def test_native_command_graph_cli_writes_replayable_receipt() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "command-graph.json"
        receipt = build_graph.build_receipt(
            run_receipt=_load(RUN_RECEIPT_PATH),
            run_receipt_path=RUN_RECEIPT_PATH,
            commands=json.loads(COMMANDS_PATH.read_text(encoding="utf-8")),
            commands_path=COMMANDS_PATH,
        )
        out.write_text(json.dumps(receipt), encoding="utf-8")
        assert replay_graph.check_receipt(json.loads(out.read_text(encoding="utf-8"))) == []
