#!/usr/bin/env python3
"""Shared helpers for timestamped benchmark artifact paths.

For benchmark artifacts under bench/out, timestamping defaults to folder layout:
bench/out/<timestamp>/<artifact>.
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


def _is_scratch_candidate_name(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in SCRATCH_NAME_TOKENS)


def run_folder_for_path(path: str | Path) -> Path | None:
    target = Path(path)
    for candidate in [target, *target.parents]:
        if not _is_timestamp_folder(candidate.name):
            continue
        parent = candidate.parent
        grandparent = parent.parent
        if parent.name == "out" and grandparent.name == "bench":
            return candidate
        if (
            parent.name == "scratch"
            and grandparent.name == "out"
            and grandparent.parent.name == "bench"
        ):
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
        merged["schemaVersion"] = 1
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
        return target.parent / timestamp / target.name
    if target.suffix.lower() in FILE_SUFFIXES:
        return target.with_name(f"{target.stem}.{timestamp}{target.suffix}")
    return target.with_name(f"{target.name}.{timestamp}")
