#!/usr/bin/env python3
"""Blocking spec-diff gate.

Compares named constants defined in `runtime/zig/src/` spec modules
(`spirv_spec.zig`, `vk_constants.zig`, `d3d12_constants.zig`) against the
canonical values declared in the in-tree header files under
`browser/chromium/src/third_party/`. The set of (namespace, field name,
canonical identifier) triples is driven by `config/spec-diff-targets.json`,
validated against `config/spec-diff-targets.schema.json` by the schema gate.

The gate prevents regressions like the 26 latent-bug fixes found by the
original spec-audit pattern (SPIR-V Capability/ImageFormat/Decoration/Builtin,
Vulkan VkStructureType/VkBlendFactor/VkDynamicState, D3D12 RESOURCE_STATE
COPY_DEST/COPY_SOURCE swap) from landing again.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.lib.bench_utils import detect_repo_root, load_json


@dataclass(frozen=True)
class FieldMapping:
    zig_name: str
    canonical_name: str


@dataclass(frozen=True)
class Target:
    target_id: str
    zig_path: str
    zig_namespace: str | None
    header_path: str
    canonical_prefix: str
    fields: tuple[FieldMapping, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="", help="Repository root. Auto-detected when omitted.")
    parser.add_argument(
        "--registry",
        default="config/spec-diff-targets.json",
        help="Path (relative to root) of the target registry.",
    )
    return parser.parse_args()


def load_targets(root: Path, registry_rel: str) -> list[Target]:
    registry_path = root / registry_rel
    if not registry_path.exists():
        raise ValueError(f"missing spec-diff registry: {registry_rel}")
    payload = load_json(registry_path)
    if not isinstance(payload, dict):
        raise ValueError(f"{registry_rel}: registry must be a JSON object")

    headers_obj = payload.get("headers")
    if not isinstance(headers_obj, dict):
        raise ValueError(f"{registry_rel}: headers must be an object")
    header_paths: dict[str, str] = {}
    for header_id, header_value in headers_obj.items():
        if not isinstance(header_value, dict):
            raise ValueError(f"{registry_rel}: header {header_id!r} must be an object")
        path_value = header_value.get("path")
        if not isinstance(path_value, str):
            raise ValueError(f"{registry_rel}: header {header_id!r} missing path string")
        header_paths[header_id] = path_value

    targets_value = payload.get("targets")
    if not isinstance(targets_value, list):
        raise ValueError(f"{registry_rel}: targets must be an array")

    parsed: list[Target] = []
    for index, raw_target in enumerate(targets_value):
        if not isinstance(raw_target, dict):
            raise ValueError(f"{registry_rel}: targets[{index}] must be an object")
        target_id = raw_target.get("id")
        zig_path = raw_target.get("zigPath")
        zig_namespace = raw_target.get("zigNamespace")
        header_id = raw_target.get("header")
        canonical_prefix = raw_target.get("canonicalPrefix", "")
        fields_value = raw_target.get("fields")
        if not isinstance(target_id, str):
            raise ValueError(f"{registry_rel}: targets[{index}] missing id")
        if not isinstance(zig_path, str):
            raise ValueError(f"{registry_rel}: target {target_id!r} missing zigPath")
        if zig_namespace is not None and not isinstance(zig_namespace, str):
            raise ValueError(f"{registry_rel}: target {target_id!r} zigNamespace must be string or null")
        if not isinstance(header_id, str) or header_id not in header_paths:
            raise ValueError(
                f"{registry_rel}: target {target_id!r} header {header_id!r} not declared in headers"
            )
        if not isinstance(canonical_prefix, str):
            raise ValueError(f"{registry_rel}: target {target_id!r} canonicalPrefix must be a string")
        if not isinstance(fields_value, list) or len(fields_value) == 0:
            raise ValueError(f"{registry_rel}: target {target_id!r} fields must be a non-empty array")

        mappings: list[FieldMapping] = []
        for field_index, field_entry in enumerate(fields_value):
            if isinstance(field_entry, str):
                mappings.append(
                    FieldMapping(zig_name=field_entry, canonical_name=canonical_prefix + field_entry)
                )
            elif isinstance(field_entry, dict):
                zig_value = field_entry.get("zig")
                canonical_value = field_entry.get("canonical")
                if not isinstance(zig_value, str) or not isinstance(canonical_value, str):
                    raise ValueError(
                        f"{registry_rel}: target {target_id!r} fields[{field_index}] "
                        "must provide string zig and canonical"
                    )
                mappings.append(
                    FieldMapping(zig_name=zig_value, canonical_name=canonical_prefix + canonical_value)
                )
            else:
                raise ValueError(
                    f"{registry_rel}: target {target_id!r} fields[{field_index}] must be string or object"
                )

        parsed.append(
            Target(
                target_id=target_id,
                zig_path=zig_path,
                zig_namespace=zig_namespace,
                header_path=header_paths[header_id],
                canonical_prefix=canonical_prefix,
                fields=tuple(mappings),
            )
        )
    return parsed


_INTEGER_LITERAL = r"(?:0x[0-9a-fA-F]+|\d+)"
_CANONICAL_RE = re.compile(
    rf"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*({_INTEGER_LITERAL})\b"
)
_ZIG_TOP_LEVEL_RE = re.compile(
    rf"^\s*pub\s+const\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*[^=]+=\s*({_INTEGER_LITERAL})\s*;",
    re.MULTILINE,
)
_ZIG_NAMESPACED_FIELD_RE = re.compile(
    rf"\bpub\s+const\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*[^=]+=\s*({_INTEGER_LITERAL})\s*;"
)


def parse_integer(literal: str) -> int:
    return int(literal, 0)


def extract_canonical_values(header_text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for match in _CANONICAL_RE.finditer(header_text):
        name = match.group(1)
        try:
            literal_value = parse_integer(match.group(2))
        except ValueError:
            continue
        values.setdefault(name, literal_value)
    return values


def strip_line_comments(source: str) -> str:
    return re.sub(r"//[^\n]*", "", source)


def extract_zig_top_level(source: str) -> dict[str, int]:
    cleaned = strip_line_comments(source)
    values: dict[str, int] = {}
    for match in _ZIG_TOP_LEVEL_RE.finditer(cleaned):
        try:
            values[match.group(1)] = parse_integer(match.group(2))
        except ValueError:
            continue
    return values


def extract_zig_namespace_body(source: str, namespace: str) -> str | None:
    start_pattern = re.compile(
        rf"^\s*pub\s+const\s+{re.escape(namespace)}\s*=\s*struct\s*\{{",
        re.MULTILINE,
    )
    start_match = start_pattern.search(source)
    if start_match is None:
        return None
    index = start_match.end()
    depth = 1
    while index < len(source) and depth > 0:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start_match.end() : index]
        index += 1
    return None


def extract_zig_namespaced(source: str, namespace: str) -> dict[str, int] | None:
    cleaned = strip_line_comments(source)
    body = extract_zig_namespace_body(cleaned, namespace)
    if body is None:
        return None
    values: dict[str, int] = {}
    for match in _ZIG_NAMESPACED_FIELD_RE.finditer(body):
        try:
            values[match.group(1)] = parse_integer(match.group(2))
        except ValueError:
            continue
    return values


def format_value(value: int) -> str:
    if value >= 16:
        return f"{value} (0x{value:x})"
    return str(value)


def validate_target(root: Path, target: Target, header_cache: dict[str, dict[str, int]]) -> list[str]:
    failures: list[str] = []
    zig_path = root / target.zig_path
    header_path = root / target.header_path

    if not zig_path.exists():
        failures.append(f"[{target.target_id}] missing zig source: {target.zig_path}")
        return failures
    if not header_path.exists():
        failures.append(f"[{target.target_id}] missing canonical header: {target.header_path}")
        return failures

    try:
        zig_source = zig_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        failures.append(f"[{target.target_id}] zig source read failed: {exc}")
        return failures

    if target.zig_namespace is None:
        zig_values = extract_zig_top_level(zig_source)
    else:
        extracted = extract_zig_namespaced(zig_source, target.zig_namespace)
        if extracted is None:
            failures.append(
                f"[{target.target_id}] zig namespace {target.zig_namespace!r} not found in {target.zig_path}"
            )
            return failures
        zig_values = extracted

    if target.header_path not in header_cache:
        try:
            header_text = header_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            failures.append(f"[{target.target_id}] header read failed: {exc}")
            return failures
        header_cache[target.header_path] = extract_canonical_values(header_text)
    canonical_values = header_cache[target.header_path]

    for field in target.fields:
        if field.zig_name not in zig_values:
            failures.append(
                f"[{target.target_id}] zig constant {field.zig_name!r} not found in {target.zig_path}"
            )
            continue
        if field.canonical_name not in canonical_values:
            failures.append(
                f"[{target.target_id}] canonical constant {field.canonical_name!r} not found in {target.header_path}"
            )
            continue
        zig_value = zig_values[field.zig_name]
        canonical_value = canonical_values[field.canonical_name]
        if zig_value != canonical_value:
            failures.append(
                f"[{target.target_id}] value mismatch for {field.zig_name} (canonical {field.canonical_name}): "
                f"zig={format_value(zig_value)} canonical={format_value(canonical_value)}"
            )
    return failures


def main() -> int:
    args = parse_args()
    try:
        root = detect_repo_root(args.root)
        targets = load_targets(root, args.registry)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1

    header_cache: dict[str, dict[str, int]] = {}
    failures: list[str] = []
    for target in targets:
        failures.extend(validate_target(root, target, header_cache))

    if failures:
        print("FAIL: spec-diff gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
