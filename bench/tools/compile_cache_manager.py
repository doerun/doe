"""Content-addressed compile cache for cslc outputs (north-star rung 0).

The steps-mode driver materializes per-target `layout.csl` /
`pe_program.csl` plus metadata sidecars, then runs `cslc` per target.
Across runs that touch only orthogonal targets, the per-target compile
cost is paid every time even though the inputs are byte-identical.

This module provides a content-addressed cache keyed by
sha256(layout.csl bytes + pe_program.csl bytes + compileParams JSON).
On a cache hit the prior `bin/` directory and `out_*.elf` artifacts can
be restored verbatim; on a miss the caller compiles and then stores
the result.

The cache lives under `bench/out/scratch/compile-cache/` by default
(gitignored, alongside the other simfabric scratch paths). Each cache
entry is `<cache_root>/<key>/{bin/...,out_*.elf,layout.csl,pe_program.csl}`
plus a `cache-entry.json` with the input hashes and a timestamp so
auditors can spot stale entries.

The cache key intentionally hashes the same artifacts the prepack
drift guard pins, so a real lowering change invalidates the key and
the cache cannot serve a stale `.elf`. There is no "force rebuild"
escape hatch — the right way to evict is to delete the cache entry.

Public API:

  - target_cache_key(target_dir, compile_params=None) -> str
  - cache_path(cache_root, key) -> Path
  - is_hit(cache_root, key) -> bool
  - restore(cache_root, key, target_compile_dir) -> Path
  - store(cache_root, key, target_compile_dir, source_target_dir,
          compile_params=None) -> Path
  - load_entry_metadata(cache_root, key) -> dict | None

The module is dependency-free aside from the standard library.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_ROOT = REPO_ROOT / "bench/out/scratch/compile-cache"

LAYOUT_FILENAME = "layout.csl"
PE_PROGRAM_FILENAME = "pe_program.csl"
CACHE_ENTRY_METADATA = "cache-entry.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def target_cache_key(
    target_dir: Path,
    compile_params: dict[str, Any] | None = None,
) -> str:
    """Compute the content-addressed cache key for a per-target compile dir.

    `target_dir` must contain `layout.csl` and `pe_program.csl`. Their
    bytes are hashed together with a canonical JSON encoding of
    `compile_params` (default {}) so callers can include cslc flags,
    width/height, or any other invocation-affecting input.

    Returns a 64-char hex sha256.
    """
    layout = target_dir / LAYOUT_FILENAME
    pe_program = target_dir / PE_PROGRAM_FILENAME
    if not layout.is_file():
        raise FileNotFoundError(
            f"compile_cache_manager: missing {LAYOUT_FILENAME} in {target_dir}"
        )
    if not pe_program.is_file():
        raise FileNotFoundError(
            f"compile_cache_manager: missing {PE_PROGRAM_FILENAME} in {target_dir}"
        )
    h = hashlib.sha256()
    h.update(b"layout=")
    h.update(_sha256_file(layout).encode("ascii"))
    h.update(b"\n")
    h.update(b"pe_program=")
    h.update(_sha256_file(pe_program).encode("ascii"))
    h.update(b"\n")
    h.update(b"compileParams=")
    h.update(_stable_json(compile_params or {}).encode("utf-8"))
    return h.hexdigest()


def cache_path(cache_root: Path, key: str) -> Path:
    """Return the absolute path of the cache entry for `key`."""
    return cache_root / key


def is_hit(cache_root: Path, key: str) -> bool:
    """Return True iff a cache entry for `key` exists and looks complete."""
    entry = cache_path(cache_root, key)
    if not entry.is_dir():
        return False
    if not (entry / CACHE_ENTRY_METADATA).is_file():
        return False
    bin_dir = entry / "bin"
    if not bin_dir.is_dir():
        return False
    elves = list(bin_dir.glob("*.elf"))
    return bool(elves)


def load_entry_metadata(
    cache_root: Path,
    key: str,
) -> dict[str, Any] | None:
    """Return the cache entry's `cache-entry.json` payload or None."""
    meta_path = cache_path(cache_root, key) / CACHE_ENTRY_METADATA
    if not meta_path.is_file():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


def store(
    cache_root: Path,
    key: str,
    target_compile_dir: Path,
    source_target_dir: Path,
    compile_params: dict[str, Any] | None = None,
) -> Path:
    """Copy a freshly-compiled target into the cache.

    `target_compile_dir` is the cslc output dir for the target (the one
    holding `bin/out_*.elf`). `source_target_dir` is the materialized
    layout/pe_program input dir; its hashes are recorded so auditors
    can verify the key was computed against the same inputs.

    Returns the cache entry path. Overwrites a prior entry with the
    same key if present.
    """
    if not target_compile_dir.is_dir():
        raise FileNotFoundError(
            f"compile_cache_manager: target_compile_dir {target_compile_dir} "
            "does not exist"
        )
    if not (target_compile_dir / "bin").is_dir():
        raise FileNotFoundError(
            f"compile_cache_manager: {target_compile_dir} has no bin/ subdir; "
            "refusing to cache an incomplete compile output"
        )

    entry = cache_path(cache_root, key)
    if entry.exists():
        shutil.rmtree(entry)
    entry.mkdir(parents=True, exist_ok=False)

    # Copy compile output (bin/, anything else under target_compile_dir).
    for child in target_compile_dir.iterdir():
        dest = entry / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)

    # Pin the input artifacts that fed the cache key.
    layout_src = source_target_dir / LAYOUT_FILENAME
    pe_src = source_target_dir / PE_PROGRAM_FILENAME
    shutil.copy2(layout_src, entry / LAYOUT_FILENAME)
    shutil.copy2(pe_src, entry / PE_PROGRAM_FILENAME)

    metadata = {
        "schemaVersion": 1,
        "artifactKind": "doe_compile_cache_entry",
        "key": key,
        "storedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "inputHashes": {
            LAYOUT_FILENAME: _sha256_file(layout_src),
            PE_PROGRAM_FILENAME: _sha256_file(pe_src),
        },
        "compileParams": compile_params or {},
        "sourceTargetDir": str(source_target_dir),
        "sourceCompileDir": str(target_compile_dir),
    }
    (entry / CACHE_ENTRY_METADATA).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return entry


def restore(
    cache_root: Path,
    key: str,
    target_compile_dir: Path,
) -> Path:
    """Copy a cached compile output back to `target_compile_dir`.

    Raises if the key is not in the cache. Overwrites
    `target_compile_dir` contents (with the exception of the
    cache-entry.json metadata, which stays in the cache only).
    """
    if not is_hit(cache_root, key):
        raise FileNotFoundError(
            f"compile_cache_manager: cache miss for key {key} under {cache_root}"
        )
    entry = cache_path(cache_root, key)
    target_compile_dir.mkdir(parents=True, exist_ok=True)
    for child in entry.iterdir():
        if child.name == CACHE_ENTRY_METADATA:
            continue
        if child.name in (LAYOUT_FILENAME, PE_PROGRAM_FILENAME):
            # Inputs are not part of the compile output; the live
            # target_compile_dir already has them.
            continue
        dest = target_compile_dir / child.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    return target_compile_dir
