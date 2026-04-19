#!/usr/bin/env python3
"""Fingerprint compiled CSL ELFs across the runtime-ready fixtures.

Walks every fixture under runtime/zig/examples/simulator/*-runtime/
whose `compile/compiled/<name>/bin/` directory has ELF artifacts, hashes
each ELF with SHA-256, and emits a consolidated fingerprint JSON. The
artifact is schema-registered so any future emitter or cslc change that
touches the ELF bytes shows up as a hash delta in the gate sweep.

Also includes full-grid probe outputs under
bench/out/cslc-grid-probe/{compile-outputs,2d-compile-outputs}/*/bin/
so E2B and 31B scale-compile evidence is covered too.

Skipped: GELU (WGSL-backed, ELFs emitted on demand by the governed lane
into temp dirs; no persistent copy). Noted explicitly in the artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

FIXTURE_ROOTS = [
    "runtime/zig/examples/simulator",
]
PROBE_ROOTS = [
    "bench/out/cslc-grid-probe/compile-outputs",
    "bench/out/cslc-grid-probe/2d-compile-outputs",
]

SOURCE_ONLY_FIXTURES = ["gelu-wgsl-backed"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out-json", default="bench/out/csl-kernel-fingerprints.json")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_bin_dir(bin_dir: Path, detailed: bool = True) -> dict[str, Any]:
    """Hash each ELF in bin_dir.

    When detailed=True (default), returns per-ELF hashes. When False, only
    emits a summary hash computed over the sorted (name, sha256) list plus
    the count + total bytes — used for large probe grids where per-ELF
    detail would blow up the artifact size.
    """
    elfs = sorted(p for p in bin_dir.iterdir() if p.suffix == ".elf")
    per_elf = [(p.name, sha256_file(p), p.stat().st_size) for p in elfs]
    total_bytes = sum(size for _, _, size in per_elf)

    base = {
        "binDir": rel(bin_dir),
        "elfCount": len(elfs),
        "totalBytes": total_bytes,
    }
    if detailed:
        base["elfs"] = [
            {"name": name, "bytes": size, "sha256": sha}
            for name, sha, size in per_elf
        ]
    # Summary hash of the concatenated per-ELF records — catches drift in
    # any single ELF without listing them all, which matters for 58k-PE
    # probe grids.
    digest = hashlib.sha256()
    for name, sha, size in per_elf:
        digest.update(f"{name}:{sha}:{size}\n".encode("utf-8"))
    base["aggregateSha256"] = digest.hexdigest()
    return base


def main() -> int:
    args = parse_args()

    fixtures: list[dict[str, Any]] = []
    for root in FIXTURE_ROOTS:
        root_path = resolve(root)
        if not root_path.exists():
            continue
        for fixture_dir in sorted(root_path.iterdir()):
            if not fixture_dir.is_dir():
                continue
            if fixture_dir.name in SOURCE_ONLY_FIXTURES:
                fixtures.append({
                    "fixtureId": fixture_dir.name,
                    "status": "source_only",
                    "reason": "WGSL-backed; ELFs emitted on demand by the governed lane into temp dirs and not persisted.",
                })
                continue
            # bin dir lives at compile/compiled/<name>/bin/
            compiled_root = fixture_dir / "compile" / "compiled"
            if not compiled_root.exists():
                continue
            for kernel_dir in sorted(compiled_root.iterdir()):
                if not kernel_dir.is_dir():
                    continue
                bin_dir = kernel_dir / "bin"
                if not bin_dir.exists():
                    continue
                entry = {
                    "fixtureId": fixture_dir.name,
                    "kernelName": kernel_dir.name,
                    "status": "compiled",
                    **fingerprint_bin_dir(bin_dir),
                }
                fixtures.append(entry)

    probes: list[dict[str, Any]] = []
    for root in PROBE_ROOTS:
        root_path = resolve(root)
        if not root_path.exists():
            continue
        for size_dir in sorted(root_path.iterdir()):
            if not size_dir.is_dir():
                continue
            bin_dir = size_dir / "bin"
            if not bin_dir.exists():
                continue
            entry = {
                "probeKind": root_path.name,
                "sizeTag": size_dir.name,
                **fingerprint_bin_dir(bin_dir, detailed=False),
            }
            probes.append(entry)

    out_path = resolve(args.out_json)
    artifact = {
        "schemaVersion": 1,
        "artifactKind": "doe_csl_kernel_fingerprints",
        "target": "wse3",
        "fixtures": fixtures,
        "probes": probes,
        "summary": {
            "fixtureCount": sum(1 for f in fixtures if f.get("status") == "compiled"),
            "sourceOnlyFixtureCount": sum(1 for f in fixtures if f.get("status") == "source_only"),
            "probeCount": len(probes),
            "totalElfsFingerprinted": sum(
                f.get("elfCount", 0) for f in fixtures
            ) + sum(p.get("elfCount", 0) for p in probes),
            "totalBytesFingerprinted": sum(
                f.get("totalBytes", 0) for f in fixtures
            ) + sum(p.get("totalBytes", 0) for p in probes),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    s = artifact["summary"]
    print(
        f"fingerprinted {s['fixtureCount']} fixtures + {s['probeCount']} probe grids "
        f"({s['totalElfsFingerprinted']} ELFs, {s['totalBytesFingerprinted']:,} bytes) "
        f"→ {rel(out_path)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
