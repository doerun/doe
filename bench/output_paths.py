#!/usr/bin/env python3
"""Shared helpers for grouped timestamped benchmark artifact paths.

For benchmark artifacts under bench/out, timestamping defaults to folder layout:
bench/out/<group>/<timestamp>/<artifact>.
Ad-hoc/scratch-named artifacts are routed to:
bench/out/scratch/<timestamp>/<artifact>.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


TIMESTAMP_RE = re.compile(r"(?:^|[._-])\d{8}T\d{6}Z(?:[._-]|$)")
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
SCRATCH_NAME_TOKENS = (
    "layoutcheck",
    "contractcheck",
    "tmp.",
    "tmp_",
    ".tmp",
    "scratch",
)
FILE_SUFFIXES = {
    ".json",
    ".html",
    ".md",
    ".txt",
    ".ndjson",
    ".tsv",
    ".log",
    ".csv",
}
SCHEMA_VERSION = 1
DROPIN_PREFIXES = (
    "dropin_report",
    "dropin_symbol_report",
    "dropin_behavior_report",
    "dropin_benchmark_report",
)


def _slugify_token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned


def _sanitize_group(group: str | Path) -> Path:
    candidate = Path(str(group).strip())
    if not str(candidate):
        raise ValueError("group must not be empty")
    if candidate.is_absolute():
        raise ValueError(f"group must be relative: {group}")
    parts: list[str] = []
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(f"group must not traverse parents: {group}")
        slug = _slugify_token(part)
        if not slug:
            raise ValueError(f"group contains no usable path token: {group}")
        parts.append(slug)
    if not parts:
        raise ValueError(f"group contains no usable path token: {group}")
    return Path(*parts)


def utc_timestamp_now() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


def resolve_timestamp(timestamp: str) -> str:
    candidate = timestamp.strip()
    if not candidate:
        return utc_timestamp_now()
    if re.fullmatch(r"\d{8}T\d{6}Z", candidate):
        return candidate
    raise ValueError(
        "invalid timestamp format: expected YYYYMMDDTHHMMSSZ "
        f"(received: {timestamp})"
    )


def is_timestamped_path(path: Path) -> bool:
    name = path.name
    return bool(TIMESTAMP_RE.search(name))


def _is_timestamp_folder(part: str) -> bool:
    return bool(re.fullmatch(r"\d{8}T\d{6}Z", part))


def _is_under_timestamp_folder(path: Path) -> bool:
    return any(_is_timestamp_folder(part) for part in path.parts)


def _bench_out_index(path: Path) -> int | None:
    parts = path.parts
    for idx in range(len(parts) - 1):
        if parts[idx] == "bench" and parts[idx + 1] == "out":
            return idx
    return None


def _is_bench_out_path(path: Path) -> bool:
    return _bench_out_index(path) is not None


def _bench_out_root(path: Path) -> Path | None:
    idx = _bench_out_index(path)
    if idx is None:
        return None
    return Path(*path.parts[: idx + 2])


def _strip_known_prefix(name: str) -> str:
    for prefix in (
        "dawn-vs-doe.",
        "runtime-comparisons.",
        "runtime-comparison.",
        "release-claim-windows.",
        "substantiation_report",
        "test-inventory.",
        "test-dashboard.",
        "perf_report",
        "run_metadata",
    ):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def derive_bench_out_group(path: str | Path) -> Path | None:
    target = Path(path)
    bench_out_root = _bench_out_root(target)
    if bench_out_root is None:
        return None
    try:
        relative_parent = target.parent.relative_to(bench_out_root)
    except ValueError:
        return None
    if relative_parent != Path("."):
        return relative_parent

    name = target.stem if target.suffix.lower() in FILE_SUFFIXES else target.name
    lowered = name.lower()

    if any(lowered.startswith(prefix) for prefix in DROPIN_PREFIXES):
        return Path("dropin")
    if lowered.startswith("release-claim-windows") or lowered.startswith("substantiation_report"):
        return Path("release-claim-windows")
    if lowered.startswith("test-inventory") or lowered.startswith("test-dashboard"):
        return Path("inventory")
    if lowered.startswith("perf_report") or lowered.startswith("run_metadata"):
        return Path("run-bench")
    if lowered.startswith("vulkan.recheck.app.claim_cycle") or "amd.vulkan.app.claim" in lowered:
        return Path("amd-vulkan") / "app-claim"

    stripped = _strip_known_prefix(lowered)
    if stripped.startswith("amd.vulkan.single."):
        return Path("amd-vulkan") / "singles"
    if stripped.startswith("amd.vulkan.extended.strict.comparable"):
        return Path("amd-vulkan") / "extended-strict-comparable"
    if stripped.startswith("amd.vulkan.extended.strict.release"):
        return Path("amd-vulkan") / "extended-strict-release"
    if stripped.startswith("amd.vulkan.extended.strict.directional"):
        return Path("amd-vulkan") / "extended-strict-directional"
    if stripped.startswith("local.vulkan.single."):
        return Path("local-vulkan") / "singles"
    if stripped.startswith("amd.vulkan.extended.comparable"):
        return Path("amd-vulkan") / "extended-comparable"
    if stripped.startswith("amd.vulkan.superset.native-supported.comparable"):
        return Path("amd-vulkan") / "superset-native-supported-comparable"
    if stripped.startswith("amd.vulkan.superset.native-supported.release"):
        return Path("amd-vulkan") / "superset-native-supported-release"
    if stripped.startswith("amd.vulkan.superset.comparable"):
        return Path("amd-vulkan") / "superset-comparable"
    if stripped.startswith("apple.metal.extended.comparable"):
        return Path("apple-metal") / "extended-comparable"
    if stripped.startswith("apple.metal.release"):
        return Path("apple-metal") / "release"
    if stripped.startswith("apple.metal.comparable"):
        return Path("apple-metal") / "comparable"
    if stripped.startswith("apple.metal.directional"):
        return Path("apple-metal") / "directional"
    if stripped.startswith("apple.metal"):
        return Path("apple-metal")
    if stripped.startswith("amd.vulkan"):
        return Path("amd-vulkan")
    if stripped.startswith("local.metal.extended.comparable"):
        return Path("apple-metal") / "extended-comparable"
    if stripped.startswith("local.metal.release"):
        return Path("apple-metal") / "release"
    if stripped.startswith("local.metal"):
        return Path("apple-metal")
    if stripped.startswith("local.vulkan.extended.comparable"):
        return Path("local-vulkan") / "extended-comparable"
    if stripped.startswith("local.vulkan.release"):
        return Path("local-vulkan") / "release"
    if stripped.startswith("local.vulkan"):
        return Path("local-vulkan")

    slug = _slugify_token(stripped)
    if not slug:
        slug = _slugify_token(name)
    return Path(slug) if slug else None


def collect_timestamp_folders(
    out_dir: str | Path,
    *,
    include_scratch: bool = True,
) -> list[Path]:
    root = Path(out_dir)
    if not root.exists() or not root.is_dir():
        return []
    folders = [
        path
        for path in root.rglob("*")
        if path.is_dir() and _is_timestamp_folder(path.name)
    ]
    if not include_scratch:
        folders = [path for path in folders if "scratch" not in path.parts]
    return sorted(
        folders,
        key=lambda path: (
            path.name,
            str(path.parent.relative_to(root)) if path.parent != root else "",
            str(path),
        ),
    )


def _is_scratch_candidate_name(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in SCRATCH_NAME_TOKENS)


def run_folder_for_path(path: str | Path) -> Path | None:
    target = Path(path)
    for candidate in [target, *target.parents]:
        if not _is_timestamp_folder(candidate.name):
            continue
        if _bench_out_index(candidate) is not None:
            return candidate
    return None


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _timestamp_from_run_folder(run_folder: Path) -> str:
    return run_folder.name if _is_timestamp_folder(run_folder.name) else ""


def write_run_manifest_for_outputs(
    outputs: Iterable[str | Path],
    payload: dict[str, Any],
) -> list[Path]:
    folders: list[Path] = []
    seen: set[str] = set()
    for output in outputs:
        folder = run_folder_for_path(output)
        if folder is None:
            continue
        key = str(folder)
        if key in seen:
            continue
        seen.add(key)
        folders.append(folder)

    written: list[Path] = []
    for folder in folders:
        manifest_path = folder / "run_manifest.json"
        current = _load_manifest(manifest_path)
        now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        merged = dict(current)
        merged.update(payload)
        merged["schemaVersion"] = SCHEMA_VERSION
        merged["runFolder"] = str(folder)
        merged["outputTimestamp"] = _timestamp_from_run_folder(folder)
        merged.setdefault("createdAtUtc", now_utc)
        merged["updatedAtUtc"] = now_utc
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(merged, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(manifest_path)
    return written


def with_timestamp(
    path: str | Path,
    timestamp: str,
    *,
    enabled: bool = True,
    layout: str = "auto",
    group: str | Path | None = None,
) -> Path:
    target = Path(path)
    if not enabled:
        return target
    if layout not in {"auto", "suffix", "folder"}:
        raise ValueError(f"invalid timestamp layout: {layout}")
    if is_timestamped_path(target):
        return target
    if layout == "auto":
        resolved_layout = "folder" if _is_bench_out_path(target) else "suffix"
    else:
        resolved_layout = layout
    if resolved_layout == "folder":
        if _is_under_timestamp_folder(target):
            return target
        bench_out_root = _bench_out_root(target)
        if bench_out_root is not None and _is_scratch_candidate_name(target.name):
            return bench_out_root / "scratch" / timestamp / target.name
        if bench_out_root is not None:
            try:
                relative_parent = target.parent.relative_to(bench_out_root)
            except ValueError:
                relative_parent = None
            if relative_parent is not None and relative_parent != Path("."):
                return bench_out_root / relative_parent / timestamp / target.name
            resolved_group = _sanitize_group(group) if group is not None else derive_bench_out_group(target)
            if resolved_group is not None:
                return bench_out_root / resolved_group / timestamp / target.name
        return target.parent / timestamp / target.name
    if target.suffix.lower() in FILE_SUFFIXES:
        return target.with_name(f"{target.stem}.{timestamp}{target.suffix}")
    return target.with_name(f"{target.name}.{timestamp}")
