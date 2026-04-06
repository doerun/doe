#!/usr/bin/env python3
"""Helpers for neutral benchmark IR and normalized plan materialization."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import jsonschema

from bench.lib import synthetic_assets


REPO_ROOT = Path(__file__).resolve().parents[2]
IR_SCHEMA_PATH = REPO_ROOT / "bench" / "ir" / "benchmark_ir.schema.json"
PLAN_SCHEMA_PATH = REPO_ROOT / "bench" / "plans" / "normalized_plan.schema.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2) + "\n"


def write_json(path: Path, payload: Any) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json_text(payload)
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.write_text(rendered, encoding="utf-8")
    return True


def canonical_json_text(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def json_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_text(payload).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_schema(path: Path, payload: Any) -> None:
    schema = load_json(path)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) if first.absolute_path else "<root>"
        raise ValueError(f"{path}: {location}: {first.message}")


def validate_ir_document(ir_doc: Any) -> None:
    _validate_schema(IR_SCHEMA_PATH, ir_doc)


def validate_plan_document(plan_doc: Any) -> None:
    _validate_schema(PLAN_SCHEMA_PATH, plan_doc)


def _command_kind(command: dict[str, Any]) -> str:
    kind = command.get("kind") or command.get("command") or command.get("command_kind")
    return str(kind) if kind is not None else ""


def _normalize_command(command: dict[str, Any]) -> dict[str, Any]:
    kind = _command_kind(command)
    if not kind:
        raise ValueError("missing command kind in IR workload")
    if kind == "repeat":
        count = command.get("count")
        if not isinstance(count, int) or count < 0:
            raise ValueError("repeat command requires non-negative integer count")
        nested = command.get("commands") or command.get("steps")
        if not isinstance(nested, list):
            raise ValueError("repeat command requires commands/steps array")
        flattened: list[dict[str, Any]] = []
        for _ in range(count):
            flattened.extend(_expand_commands(nested))
        return {"kind": "repeat", "count": count, "commands": flattened}

    normalized = OrderedDict()
    normalized["kind"] = kind
    for key, value in command.items():
        if key in {"kind", "command", "command_kind"}:
            continue
        normalized[key] = value
    return dict(normalized)


def _expand_commands(commands: list[Any]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for command in commands:
        if not isinstance(command, dict):
            raise ValueError("IR command entries must be objects")
        normalized = _normalize_command(command)
        if normalized.get("kind") == "repeat":
            expanded.extend(normalized["commands"])
        else:
            expanded.append(normalized)
    return expanded


def _count_commands(commands: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"buffer_write": 0, "buffer_load": 0, "kernel_dispatch": 0}
    for command in commands:
        kind = str(command.get("kind", ""))
        if kind in counts:
            counts[kind] += 1
    return counts


def _normalize_binding_buffer_type(binding: dict[str, Any]) -> str:
    raw = str(
        binding.get("buffer_type")
        or binding.get("bufferType")
        or binding.get("type")
        or ""
    ).strip().lower()
    if raw in {"readonly", "read_only_storage", "read-only-storage", "readonly_storage"}:
        return "readonly"
    if raw == "uniform":
        return "uniform"
    return "storage"


def _synthetic_readonly_buffer_policy(ir_doc: dict[str, Any]) -> dict[str, Any] | None:
    shared = ir_doc.get("shared")
    if not isinstance(shared, dict):
        return None
    policy = shared.get("syntheticReadonlyBufferPolicy")
    if not isinstance(policy, dict):
        return None
    return {
        "cacheNamespace": str(policy.get("cacheNamespace", "")).strip(),
        "generator": synthetic_assets.normalize_generator(policy.get("generator")),
        "seed": synthetic_assets.normalize_seed(policy.get("seed")),
        "scale": synthetic_assets.normalize_scale(policy.get("scale", 1.0)),
    }


def _inject_synthetic_buffer_loads(
    *,
    ir_doc: dict[str, Any],
    scenario: dict[str, Any],
    commands: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    policy = _synthetic_readonly_buffer_policy(ir_doc)
    if policy is None:
        return commands
    if not policy["cacheNamespace"]:
        raise ValueError("syntheticReadonlyBufferPolicy.cacheNamespace must be non-empty")

    written_handles: set[int] = set()
    loaded_handles: set[int] = set()
    binding_roles: dict[int, set[str]] = {}
    first_use_index: dict[int, int] = {}
    max_size_by_handle: dict[int, int] = {}
    for index, command in enumerate(commands):
        kind = _command_kind(command)
        if kind == "buffer_write":
            written_handles.add(int(command.get("handle", 0)))
            continue
        if kind == "buffer_load":
            loaded_handles.add(int(command.get("handle", 0)))
            continue
        if kind != "kernel_dispatch":
            continue
        raw_bindings = command.get("bindings")
        if not isinstance(raw_bindings, list):
            continue
        for binding in raw_bindings:
            if not isinstance(binding, dict):
                raise ValueError("kernel_dispatch bindings must be objects")
            handle = int(
                binding.get("resource_handle")
                or binding.get("resourceHandle")
                or binding.get("handle")
                or 0
            )
            if handle <= 0:
                raise ValueError("kernel_dispatch bindings must provide a positive resource_handle")
            buffer_size = int(binding.get("buffer_size") or binding.get("bufferSize") or 0)
            if buffer_size <= 0:
                raise ValueError(f"kernel_dispatch binding handle={handle} must provide buffer_size > 0")
            binding_roles.setdefault(handle, set()).add(_normalize_binding_buffer_type(binding))
            first_use_index.setdefault(handle, index)
            max_size_by_handle[handle] = max(max_size_by_handle.get(handle, 0), buffer_size)

    insert_before: dict[int, list[dict[str, Any]]] = {}
    scenario_id = str(scenario.get("id", "")).strip() or "scenario"
    for handle in sorted(binding_roles.keys()):
        roles = binding_roles[handle]
        if roles != {"readonly"}:
            continue
        if handle in written_handles or handle in loaded_handles:
            continue
        buffer_size = max_size_by_handle[handle]
        seed = synthetic_assets.mix_seed(policy["seed"], handle)
        load_command = synthetic_assets.build_buffer_load_command(
            handle=handle,
            buffer_size=buffer_size,
            cache_namespace=policy["cacheNamespace"],
            generator=policy["generator"],
            seed=seed,
            scale=policy["scale"],
            asset_key=f"{scenario_id}:handle-{handle}",
        )
        insert_before.setdefault(first_use_index[handle], []).append(load_command)

    if not insert_before:
        return commands

    materialized: list[dict[str, Any]] = []
    for index, command in enumerate(commands):
        materialized.extend(insert_before.get(index, ()))
        materialized.append(command)
    return materialized


def load_ir_document(ir_path: Path) -> dict[str, Any]:
    payload = load_json(ir_path)
    if not isinstance(payload, dict):
        raise ValueError(f"invalid IR object: {ir_path}")
    validate_ir_document(payload)
    return payload


def load_ir_scenario(ir_path: Path, scenario_id: str) -> dict[str, Any]:
    ir_doc = load_ir_document(ir_path)
    scenarios = ir_doc.get("scenarios", [])
    if not isinstance(scenarios, list):
        raise ValueError(f"{ir_path}: scenarios must be an array")
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        if scenario.get("id") == scenario_id:
            return scenario
    raise ValueError(f"{ir_path}: missing IR scenario {scenario_id!r}")


def materialize_plan(ir_path: Path, scenario_id: str) -> dict[str, Any]:
    ir_doc = load_ir_document(ir_path)
    scenario = load_ir_scenario(ir_path, scenario_id)
    commands = _inject_synthetic_buffer_loads(
        ir_doc=ir_doc,
        scenario=scenario,
        commands=_expand_commands(scenario["commands"]),
    )
    counts = _count_commands(commands)
    ir_hash = json_sha256(ir_doc)
    compatibility_hash = json_sha256(commands)

    plan = OrderedDict()
    plan["schemaVersion"] = 1
    plan["planKind"] = ir_doc.get("kind", "benchmark_ir")
    plan["workloadId"] = scenario_id
    scenario_ir_path = scenario.get("irPath")
    if isinstance(scenario_ir_path, str) and scenario_ir_path:
        plan["irPath"] = scenario_ir_path
    else:
        try:
            plan["irPath"] = str(ir_path.relative_to(REPO_ROOT))
        except ValueError:
            plan["irPath"] = str(ir_path)
    plan["irScenario"] = scenario_id
    plan["description"] = scenario.get("description", "")
    plan["planPath"] = scenario.get("planPath", "")
    plan["commandsPath"] = scenario.get("commandsPath", "")
    plan["commandCount"] = len(commands)
    plan["bufferWriteCount"] = counts["buffer_write"]
    plan["bufferLoadCount"] = counts["buffer_load"]
    plan["dispatchCount"] = counts["kernel_dispatch"]
    plan["sourceIrSha256"] = ir_hash
    plan["compatibilityCommandsSha256"] = compatibility_hash
    plan["commands"] = commands
    plan["planSha256"] = json_sha256(plan)

    validate_plan_document(plan)
    return plan


def materialize_plan_artifacts(ir_path: Path, scenario_id: str) -> dict[str, Any]:
    plan = materialize_plan(ir_path, scenario_id)
    return {
        "plan": plan,
        "commands": plan["commands"],
        "planPath": plan["planPath"],
        "commandsPath": plan["commandsPath"],
        "planSha256": plan["planSha256"],
        "irPath": plan["irPath"],
        "irScenario": plan["irScenario"],
        "commandCount": plan["commandCount"],
        "bufferWriteCount": plan["bufferWriteCount"],
        "bufferLoadCount": plan["bufferLoadCount"],
        "dispatchCount": plan["dispatchCount"],
        "sourceIrSha256": plan["sourceIrSha256"],
        "compatibilityCommandsSha256": plan["compatibilityCommandsSha256"],
    }
