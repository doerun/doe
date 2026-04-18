#!/usr/bin/env python3
"""Blocking gate for CSL fixture mirror canonicity."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.lib.bench_utils import detect_repo_root, load_json


@dataclass(frozen=True)
class ByteIdenticalMirror:
    mirror_id: str
    canonical_path: str
    mirror_path: str


@dataclass(frozen=True)
class PathContextMirror:
    mirror_id: str
    canonical_path: str
    mirror_path: str
    ignored_json_pointers: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeOnlyFixture:
    fixture_id: str
    path: str


@dataclass(frozen=True)
class MirrorRegistry:
    byte_identical_mirrors: tuple[ByteIdenticalMirror, ...]
    path_context_mirrors: tuple[PathContextMirror, ...]
    runtime_only_fixtures: tuple[RuntimeOnlyFixture, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="", help="Repository root. Auto-detected when omitted.")
    parser.add_argument(
        "--registry",
        default="config/csl-fixture-mirrors.json",
        help="Path (relative to root) of the CSL fixture mirror registry.",
    )
    return parser.parse_args()


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def require_array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def parse_byte_identical_mirror(value: Any, index: int) -> ByteIdenticalMirror:
    obj = require_object(value, f"byteIdenticalMirrors[{index}]")
    return ByteIdenticalMirror(
        mirror_id=require_string(obj.get("id"), f"byteIdenticalMirrors[{index}].id"),
        canonical_path=require_string(
            obj.get("canonicalPath"), f"byteIdenticalMirrors[{index}].canonicalPath"
        ),
        mirror_path=require_string(obj.get("mirrorPath"), f"byteIdenticalMirrors[{index}].mirrorPath"),
    )


def parse_path_context_mirror(value: Any, index: int) -> PathContextMirror:
    obj = require_object(value, f"pathContextMirrors[{index}]")
    pointer_values = require_array(
        obj.get("ignoredJsonPointers"), f"pathContextMirrors[{index}].ignoredJsonPointers"
    )
    pointers = tuple(
        require_string(pointer, f"pathContextMirrors[{index}].ignoredJsonPointers[{pointer_index}]")
        for pointer_index, pointer in enumerate(pointer_values)
    )
    return PathContextMirror(
        mirror_id=require_string(obj.get("id"), f"pathContextMirrors[{index}].id"),
        canonical_path=require_string(
            obj.get("canonicalPath"), f"pathContextMirrors[{index}].canonicalPath"
        ),
        mirror_path=require_string(obj.get("mirrorPath"), f"pathContextMirrors[{index}].mirrorPath"),
        ignored_json_pointers=pointers,
    )


def parse_runtime_only_fixture(value: Any, index: int) -> RuntimeOnlyFixture:
    obj = require_object(value, f"runtimeOnlyFixtures[{index}]")
    return RuntimeOnlyFixture(
        fixture_id=require_string(obj.get("id"), f"runtimeOnlyFixtures[{index}].id"),
        path=require_string(obj.get("path"), f"runtimeOnlyFixtures[{index}].path"),
    )


def load_registry(root: Path, registry_rel: str) -> MirrorRegistry:
    registry_path = root / registry_rel
    if not registry_path.exists():
        raise ValueError(f"missing CSL fixture mirror registry: {registry_rel}")
    payload = require_object(load_json(registry_path), registry_rel)
    schema_version = payload.get("schemaVersion")
    if schema_version != 1:
        raise ValueError(f"{registry_rel}: schemaVersion must be 1")

    return MirrorRegistry(
        byte_identical_mirrors=tuple(
            parse_byte_identical_mirror(entry, index)
            for index, entry in enumerate(require_array(payload.get("byteIdenticalMirrors"), "byteIdenticalMirrors"))
        ),
        path_context_mirrors=tuple(
            parse_path_context_mirror(entry, index)
            for index, entry in enumerate(require_array(payload.get("pathContextMirrors"), "pathContextMirrors"))
        ),
        runtime_only_fixtures=tuple(
            parse_runtime_only_fixture(entry, index)
            for index, entry in enumerate(require_array(payload.get("runtimeOnlyFixtures"), "runtimeOnlyFixtures"))
        ),
    )


def load_schema_target_data_paths(root: Path) -> set[str]:
    payload = require_object(load_json(root / "config" / "schema-targets.json"), "config/schema-targets.json")
    targets = require_array(payload.get("targets"), "config/schema-targets.json.targets")
    data_paths: set[str] = set()
    for index, target in enumerate(targets):
        target_obj = require_object(target, f"config/schema-targets.json.targets[{index}]")
        data_paths.add(require_string(target_obj.get("data"), f"config/schema-targets.json.targets[{index}].data"))
    return data_paths


def validate_canonical_schema_registration(
    schema_target_data_paths: set[str],
    registry: MirrorRegistry,
) -> list[str]:
    failures: list[str] = []
    canonical_paths = [
        *(mirror.canonical_path for mirror in registry.byte_identical_mirrors),
        *(mirror.canonical_path for mirror in registry.path_context_mirrors),
    ]
    for canonical_path in sorted(set(canonical_paths)):
        if canonical_path not in schema_target_data_paths:
            failures.append(
                f"{canonical_path}: canonical CSL fixture must be registered in config/schema-targets.json"
            )
    return failures


def validate_runtime_fixture_coverage(root: Path, registry: MirrorRegistry) -> list[str]:
    declared_paths = {
        *(mirror.mirror_path for mirror in registry.byte_identical_mirrors),
        *(mirror.mirror_path for mirror in registry.path_context_mirrors),
        *(fixture.path for fixture in registry.runtime_only_fixtures),
    }
    runtime_fixture_paths = {
        str(path.relative_to(root))
        for path in (root / "runtime" / "zig" / "examples").glob("doe-wgsl-*.json")
        if path.is_file()
    }

    failures: list[str] = []
    for path in sorted(runtime_fixture_paths - declared_paths):
        failures.append(f"{path}: runtime CSL fixture is not declared in config/csl-fixture-mirrors.json")
    for path in sorted(declared_paths - runtime_fixture_paths):
        failures.append(f"{path}: declared runtime CSL fixture is missing")
    return failures


def validate_byte_identical(root: Path, mirror: ByteIdenticalMirror) -> list[str]:
    failures: list[str] = []
    canonical_path = root / mirror.canonical_path
    runtime_path = root / mirror.mirror_path
    if not canonical_path.exists():
        return [f"[{mirror.mirror_id}] missing canonical fixture: {mirror.canonical_path}"]
    if not runtime_path.exists():
        return [f"[{mirror.mirror_id}] missing runtime mirror: {mirror.mirror_path}"]

    try:
        canonical_bytes = canonical_path.read_bytes()
        runtime_bytes = runtime_path.read_bytes()
    except OSError as exc:
        return [f"[{mirror.mirror_id}] fixture read failed: {exc}"]

    if canonical_bytes != runtime_bytes:
        failures.append(
            f"[{mirror.mirror_id}] mirror bytes differ: {mirror.canonical_path} != {mirror.mirror_path}"
        )
    return failures


def decode_json_pointer(pointer: str) -> list[str]:
    if not pointer.startswith("/") or pointer == "":
        raise ValueError("JSON pointer must start with '/' and cannot target the document root")

    tokens: list[str] = []
    for raw_token in pointer[1:].split("/"):
        token_chars: list[str] = []
        index = 0
        while index < len(raw_token):
            char = raw_token[index]
            if char != "~":
                token_chars.append(char)
                index += 1
                continue
            if index + 1 >= len(raw_token) or raw_token[index + 1] not in ("0", "1"):
                raise ValueError(f"invalid JSON pointer escape in {pointer!r}")
            token_chars.append("~" if raw_token[index + 1] == "0" else "/")
            index += 2
        tokens.append("".join(token_chars))
    return tokens


def descend_json_pointer(value: Any, token: str, pointer: str) -> Any:
    if isinstance(value, dict):
        if token not in value:
            raise ValueError(f"{pointer}: missing object key {token!r}")
        return value[token]
    if isinstance(value, list):
        if not token.isdigit():
            raise ValueError(f"{pointer}: array index token must be a non-negative integer")
        index = int(token)
        if index >= len(value):
            raise ValueError(f"{pointer}: array index {index} out of range")
        return value[index]
    raise ValueError(f"{pointer}: cannot descend through {type(value).__name__}")


def remove_json_pointer(value: Any, pointer: str) -> None:
    tokens = decode_json_pointer(pointer)
    parent = value
    for token in tokens[:-1]:
        parent = descend_json_pointer(parent, token, pointer)

    last_token = tokens[-1]
    if isinstance(parent, dict):
        if last_token not in parent:
            raise ValueError(f"{pointer}: missing object key {last_token!r}")
        del parent[last_token]
        return
    if isinstance(parent, list):
        if not last_token.isdigit():
            raise ValueError(f"{pointer}: array index token must be a non-negative integer")
        index = int(last_token)
        if index >= len(parent):
            raise ValueError(f"{pointer}: array index {index} out of range")
        del parent[index]
        return
    raise ValueError(f"{pointer}: cannot delete from {type(parent).__name__}")


def load_json_fixture(path: Path, label: str) -> Any:
    try:
        return load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: JSON parse failed: {exc}") from exc


def validate_path_context(root: Path, mirror: PathContextMirror) -> list[str]:
    canonical_path = root / mirror.canonical_path
    runtime_path = root / mirror.mirror_path
    if not canonical_path.exists():
        return [f"[{mirror.mirror_id}] missing canonical fixture: {mirror.canonical_path}"]
    if not runtime_path.exists():
        return [f"[{mirror.mirror_id}] missing runtime mirror: {mirror.mirror_path}"]

    try:
        canonical_payload = load_json_fixture(canonical_path, mirror.canonical_path)
        runtime_payload = load_json_fixture(runtime_path, mirror.mirror_path)
    except ValueError as exc:
        return [f"[{mirror.mirror_id}] {exc}"]

    canonical_normalized = copy.deepcopy(canonical_payload)
    runtime_normalized = copy.deepcopy(runtime_payload)
    for pointer in mirror.ignored_json_pointers:
        try:
            remove_json_pointer(canonical_normalized, pointer)
            remove_json_pointer(runtime_normalized, pointer)
        except ValueError as exc:
            return [f"[{mirror.mirror_id}] {exc}"]

    if canonical_normalized != runtime_normalized:
        pointers = ", ".join(mirror.ignored_json_pointers)
        return [
            f"[{mirror.mirror_id}] normalized mirror differs after ignoring path-context fields: {pointers}"
        ]
    return []


def validate_runtime_only_fixtures(root: Path, registry: MirrorRegistry) -> list[str]:
    failures: list[str] = []
    for fixture in registry.runtime_only_fixtures:
        if not (root / fixture.path).exists():
            failures.append(f"[{fixture.fixture_id}] missing runtime-only fixture: {fixture.path}")
    return failures


def main() -> int:
    args = parse_args()
    try:
        root = detect_repo_root(args.root)
        registry = load_registry(root, args.registry)
        schema_target_data_paths = load_schema_target_data_paths(root)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: csl fixture mirror gate setup failed: {exc}")
        return 1

    failures: list[str] = []
    failures.extend(validate_canonical_schema_registration(schema_target_data_paths, registry))
    failures.extend(validate_runtime_fixture_coverage(root, registry))
    failures.extend(validate_runtime_only_fixtures(root, registry))
    for mirror in registry.byte_identical_mirrors:
        failures.extend(validate_byte_identical(root, mirror))
    for mirror in registry.path_context_mirrors:
        failures.extend(validate_path_context(root, mirror))

    if failures:
        print("FAIL: csl fixture mirror gate")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PASS: csl fixture mirror gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
