#!/usr/bin/env python3
"""Deterministic cache-backed synthetic assets for benchmark plans."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_ENV_VAR = "DOE_BENCH_ASSET_CACHE_DIR"
DEFAULT_CACHE_DIR_SUFFIX = "doe/bench_synthetic_assets"
MANIFEST_SCHEMA_VERSION = 1
SPLITMIX64_GAMMA = 0x9E3779B97F4A7C15
SPLITMIX64_MUL0 = 0xBF58476D1CE4E5B9
SPLITMIX64_MUL1 = 0x94D049BB133111EB
U64_MASK = (1 << 64) - 1
I64_MAX = (1 << 63) - 1
F64_UNIT_SCALE = 1.0 / float(1 << 53)
SUPPORTED_GENERATORS = {
    "splitmix64_f16_nonzero_v1",
    "splitmix64_f32_nonzero_v1",
}


def canonical_json_text(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def json_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_text(payload).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_cache_root() -> Path:
    override = os.environ.get(CACHE_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    home = Path.home()
    return home / ".cache" / DEFAULT_CACHE_DIR_SUFFIX


def resolve_asset_path(cache_namespace: str, cache_key: str) -> Path:
    return resolve_cache_root() / cache_namespace / f"{cache_key}.bin"


def resolve_manifest_path(cache_namespace: str, cache_key: str) -> Path:
    return resolve_cache_root() / cache_namespace / f"{cache_key}.json"


def normalize_generator(value: Any) -> str:
    generator = str(value).strip()
    if generator not in SUPPORTED_GENERATORS:
        raise ValueError(
            f"unsupported synthetic asset generator {generator!r}; "
            f"expected one of {sorted(SUPPORTED_GENERATORS)}"
        )
    return generator


def normalize_seed(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("synthetic asset seed must be an integer")
    seed = int(value)
    if seed < 0:
        raise ValueError("synthetic asset seed must be >= 0")
    return seed & U64_MASK


def normalize_scale(value: Any) -> float:
    scale = float(value)
    if not (scale > 0.0):
        raise ValueError("synthetic asset scale must be > 0")
    return scale


def normalize_byte_length(value: Any) -> int:
    byte_length = int(value)
    if byte_length <= 0:
        raise ValueError("synthetic asset byteLength must be > 0")
    return byte_length


def mix_seed(base_seed: int, handle: int) -> int:
    mixed = ((normalize_seed(base_seed) ^ (int(handle) & U64_MASK)) + SPLITMIX64_GAMMA) & U64_MASK
    return mixed & I64_MAX


def synthetic_asset_cache_key(
    *,
    cache_namespace: str,
    generator: str,
    seed: int,
    scale: float,
    byte_length: int,
    handle: int,
    asset_key: str,
) -> str:
    return json_sha256(
        {
            "cacheNamespace": cache_namespace,
            "generator": normalize_generator(generator),
            "seed": normalize_seed(seed),
            "scale": normalize_scale(scale),
            "byteLength": normalize_byte_length(byte_length),
            "handle": int(handle),
            "assetKey": asset_key,
        }
    )


def build_buffer_load_command(
    *,
    handle: int,
    buffer_size: int,
    cache_namespace: str,
    generator: str,
    seed: int,
    scale: float,
    asset_key: str,
) -> dict[str, Any]:
    normalized_generator = normalize_generator(generator)
    normalized_seed = normalize_seed(seed)
    normalized_scale = normalize_scale(scale)
    byte_length = normalize_byte_length(buffer_size)
    return {
        "kind": "buffer_load",
        "handle": int(handle),
        "offset": 0,
        "bufferSize": byte_length,
        "byteLength": byte_length,
        "cacheNamespace": str(cache_namespace),
        "cacheKey": synthetic_asset_cache_key(
            cache_namespace=str(cache_namespace),
            generator=normalized_generator,
            seed=normalized_seed,
            scale=normalized_scale,
            byte_length=byte_length,
            handle=int(handle),
            asset_key=asset_key,
        ),
        "assetKey": asset_key,
        "generator": normalized_generator,
        "seed": normalized_seed,
        "scale": normalized_scale,
    }


def buffer_load_commands_from_plan(plan_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(plan_payload, dict):
        raise ValueError("normalized plan must be a JSON object")
    raw_commands = plan_payload.get("commands")
    if not isinstance(raw_commands, list):
        return []
    commands: list[dict[str, Any]] = []
    for command in raw_commands:
        if isinstance(command, dict) and str(command.get("kind", "")).strip().lower() == "buffer_load":
            commands.append(command)
    return commands


def _splitmix64_next(state: int) -> tuple[int, int]:
    updated = (state + SPLITMIX64_GAMMA) & U64_MASK
    mixed = updated
    mixed = ((mixed ^ (mixed >> 30)) * SPLITMIX64_MUL0) & U64_MASK
    mixed = ((mixed ^ (mixed >> 27)) * SPLITMIX64_MUL1) & U64_MASK
    mixed ^= mixed >> 31
    return updated, mixed & U64_MASK


def _float_from_splitmix(sample: int, *, scale: float, min_abs: float) -> float:
    unit = ((sample >> 11) & ((1 << 53) - 1)) * F64_UNIT_SCALE
    value = ((unit * 2.0) - 1.0) * scale
    if value == 0.0 or abs(value) < min_abs:
        return min_abs if (sample & 1) == 0 else -min_abs
    return value


def _generate_f32_nonzero(*, seed: int, scale: float, byte_length: int) -> bytes:
    if byte_length % 4 != 0:
        raise ValueError("splitmix64_f32_nonzero_v1 requires byteLength divisible by 4")
    count = byte_length // 4
    min_abs = max(scale / 1024.0, 2.0**-20)
    output = bytearray(byte_length)
    state = normalize_seed(seed)
    for index in range(count):
        state, sample = _splitmix64_next(state)
        value = _float_from_splitmix(sample, scale=scale, min_abs=min_abs)
        struct.pack_into("<f", output, index * 4, value)
    return bytes(output)


def _generate_f16_nonzero(*, seed: int, scale: float, byte_length: int) -> bytes:
    if byte_length % 2 != 0:
        raise ValueError("splitmix64_f16_nonzero_v1 requires byteLength divisible by 2")
    count = byte_length // 2
    min_abs = max(scale / 256.0, 2.0**-12)
    output = bytearray(byte_length)
    state = normalize_seed(seed)
    for index in range(count):
        state, sample = _splitmix64_next(state)
        value = _float_from_splitmix(sample, scale=scale, min_abs=min_abs)
        struct.pack_into("<e", output, index * 2, value)
    return bytes(output)


def generate_asset_bytes(*, generator: str, seed: int, scale: float, byte_length: int) -> bytes:
    normalized_generator = normalize_generator(generator)
    normalized_seed = normalize_seed(seed)
    normalized_scale = normalize_scale(scale)
    normalized_byte_length = normalize_byte_length(byte_length)
    if normalized_generator == "splitmix64_f32_nonzero_v1":
        return _generate_f32_nonzero(
            seed=normalized_seed,
            scale=normalized_scale,
            byte_length=normalized_byte_length,
        )
    if normalized_generator == "splitmix64_f16_nonzero_v1":
        return _generate_f16_nonzero(
            seed=normalized_seed,
            scale=normalized_scale,
            byte_length=normalized_byte_length,
        )
    raise AssertionError(f"unsupported generator reached generation path: {normalized_generator}")


def _command_fields(command: dict[str, Any]) -> dict[str, Any]:
    if str(command.get("kind", "")).strip().lower() != "buffer_load":
        raise ValueError("expected a buffer_load command")
    cache_namespace = str(command.get("cacheNamespace", "")).strip()
    cache_key = str(command.get("cacheKey", "")).strip()
    if not cache_namespace or not cache_key:
        raise ValueError("buffer_load requires non-empty cacheNamespace and cacheKey")
    byte_length = normalize_byte_length(command.get("byteLength") or command.get("bufferSize"))
    return {
        "cacheNamespace": cache_namespace,
        "cacheKey": cache_key,
        "assetKey": str(command.get("assetKey", "")).strip() or f"handle-{int(command.get('handle', 0))}",
        "generator": normalize_generator(command.get("generator")),
        "seed": normalize_seed(command.get("seed")),
        "scale": normalize_scale(command.get("scale")),
        "handle": int(command.get("handle", 0)),
        "byteLength": byte_length,
    }


def _manifest_payload(fields: dict[str, Any], payload_sha256: str) -> dict[str, Any]:
    return {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "cacheNamespace": fields["cacheNamespace"],
        "cacheKey": fields["cacheKey"],
        "assetKey": fields["assetKey"],
        "generator": fields["generator"],
        "seed": fields["seed"],
        "scale": fields["scale"],
        "handle": fields["handle"],
        "byteLength": fields["byteLength"],
        "sha256": payload_sha256,
    }


def _validate_existing_asset(asset_path: Path, manifest_path: Path, fields: dict[str, Any]) -> bool:
    if not asset_path.exists() or not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    expected = _manifest_payload(fields, file_sha256(asset_path))
    return manifest == expected and asset_path.stat().st_size == fields["byteLength"]


def _write_atomic(path: Path, payload: bytes | str, *, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=path.parent) as handle:
        tmp_path = Path(handle.name)
        if mode == "wb":
            handle.write(payload if isinstance(payload, bytes) else payload.encode("utf-8"))
        else:
            handle.write((payload if isinstance(payload, str) else payload.decode("utf-8")).encode("utf-8"))
    tmp_path.replace(path)


def ensure_buffer_load_asset(command: dict[str, Any]) -> Path:
    fields = _command_fields(command)
    asset_path = resolve_asset_path(fields["cacheNamespace"], fields["cacheKey"])
    manifest_path = resolve_manifest_path(fields["cacheNamespace"], fields["cacheKey"])
    if _validate_existing_asset(asset_path, manifest_path, fields):
        return asset_path
    payload = generate_asset_bytes(
        generator=fields["generator"],
        seed=fields["seed"],
        scale=fields["scale"],
        byte_length=fields["byteLength"],
    )
    if len(payload) != fields["byteLength"]:
        raise ValueError("generated synthetic asset length does not match byteLength")
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    manifest = _manifest_payload(fields, payload_sha256)
    _write_atomic(asset_path, payload, mode="wb")
    _write_atomic(manifest_path, json.dumps(manifest, indent=2) + "\n", mode="w")
    return asset_path


def ensure_plan_assets(plan_path: Path) -> list[Path]:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    return [ensure_buffer_load_asset(command) for command in buffer_load_commands_from_plan(payload)]


def describe_plan_assets(plan_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    described: list[dict[str, Any]] = []
    for command in buffer_load_commands_from_plan(payload):
        fields = _command_fields(command)
        described.append(
            {
                **fields,
                "assetPath": str(resolve_asset_path(fields["cacheNamespace"], fields["cacheKey"])),
                "manifestPath": str(resolve_manifest_path(fields["cacheNamespace"], fields["cacheKey"])),
            }
        )
    return described


def iter_buffer_load_descriptors(plan_paths: Iterable[Path]) -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    for plan_path in plan_paths:
        descriptors.extend(describe_plan_assets(plan_path))
    return descriptors
