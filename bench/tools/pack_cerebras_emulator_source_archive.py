#!/usr/bin/env python3
"""Pack runnable Cerebras CSL source for external emulator experiments."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SourceEntry:
    path: str
    role: str


QWEN_CELL_FILES = (
    "README.md",
    "attn_decode_layout.csl",
    "attn_decode_pe_program.csl",
    "attn_decode_run.py",
    "embed_layout.csl",
    "embed_pe_program.csl",
    "embed_run.py",
    "gemv_layout.csl",
    "gemv_pe_program.csl",
    "gemv_run.py",
    "kv_write_layout.csl",
    "kv_write_pe_program.csl",
    "kv_write_run.py",
    "residual_layout_patched.csl",
    "residual_pe_program.csl",
    "residual_run.py",
    "rmsnorm_layout_patched.csl",
    "rmsnorm_pe_program.csl",
    "rmsnorm_run.py",
    "rope_partial_layout.csl",
    "rope_partial_pe_program.csl",
    "rope_partial_run.py",
    "sample_layout.csl",
    "sample_pe_program.csl",
    "sample_run.py",
    "silu_layout_patched.csl",
    "silu_pe_program.csl",
    "silu_run.py",
    "tiled_layout.csl",
    "tiled_pe_program.csl",
    "tiled_run.py",
)

GEMMA_LM_HEAD_FILES = (
    "README.md",
    "lm_head_prefill_stable_layout.csl",
    "lm_head_prefill_stable_pe_program.csl",
    "lm_head_prefill_stable_run.py",
)

INCLUDE_FILES: tuple[SourceEntry, ...] = (
    SourceEntry("LICENSE", "license"),
    SourceEntry(
        "bench/out/streaming-executor/e2b-layer-block-source/"
        "transformer_layer_shape.csl",
        "gemma-layer-block-csl",
    ),
    SourceEntry(
        "bench/runners/csl-runners/gemma_4_31b_layer_block_smoke.py",
        "gemma-layer-block-driver",
    ),
    SourceEntry(
        "bench/runners/csl-runners/e2b_layer_block_smoke.py",
        "gemma-e2b-layer-block-driver",
    ),
    SourceEntry(
        "bench/runners/csl-runners/_e2b_layer_block_compute.py",
        "gemma-layer-block-reference",
    ),
    SourceEntry(
        "bench/tools/run_gemma4_31b_af16_simfabric_cells.py",
        "gemma-cell-tool",
    ),
    SourceEntry(
        "bench/tools/synthesize_gemma4_31b_af16_simfabric_cells_summary_receipt.py",
        "gemma-cell-tool",
    ),
    SourceEntry(
        "bench/tools/synthesize_qwen_3_6_27b_simfabric_cells_summary_receipt.py",
        "qwen-cell-tool",
    ),
    SourceEntry(
        "runtime/zig/examples/execution-v1/gemma-4-31b-af16-smoke.json",
        "manifest-contract",
    ),
    SourceEntry(
        "runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json",
        "manifest-contract",
    ),
    *(
        SourceEntry(
            f"bench/runners/csl-runners/gemma-4-31b-af16-cells/{name}",
            "gemma-lm-head-cell-source",
        )
        for name in GEMMA_LM_HEAD_FILES
    ),
    *(
        SourceEntry(
            f"bench/runners/csl-runners/qwen-3-6-27b-cells/{name}",
            "qwen-cell-source",
        )
        for name in QWEN_CELL_FILES
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="",
        help="Archive path. Defaults to bench/out with git sha in the name.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow packing when git reports uncommitted changes.",
    )
    return parser.parse_args()


def git_output(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def git_commit() -> str:
    return git_output(["rev-parse", "HEAD"]) or "unknown"


def git_dirty_tree() -> bool:
    return bool(git_output(["status", "--porcelain"]))


def git_short_sha(commit: str) -> str:
    return commit[:12] if commit and commit != "unknown" else "nogit"


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def default_out_path(commit: str) -> Path:
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M")
    return (
        REPO_ROOT
        / "bench/out"
        / f"doe-cerebras-emulator-source-{stamp}-{git_short_sha(commit)}.tar.gz"
    )


def metadata(commit: str, dirty: bool, archive_name: str) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_cerebras_emulator_source_archive_meta",
        "archiveFilename": archive_name,
        "builtAt": datetime.now(tz=timezone.utc).isoformat(),
        "gitCommit": commit,
        "gitDirtyTree": dirty,
        "sourceArchiveScope": {
            "purpose": "Runnable CSL source for external emulator experiments.",
            "notWhat": (
                "Not a correctness evidence bundle. Not a hardware receipt. "
                "Not a weight bundle. Not a performance claim."
            ),
        },
        "tool": "bench/tools/pack_cerebras_emulator_source_archive.py",
    }


def readme() -> str:
    return """# Doe Cerebras emulator source archive

This archive is for people who want runnable CSL source and Python drivers.
It is separate from `doe-cerebras-evidence-*.tar.gz`, which is a
correctness/governance bundle made of receipts and claim-scope documents.

## Included source surfaces

- Gemma 4 31B dense layer-block CSL:
  `bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl`
- Gemma 4 31B layer-block drivers:
  `bench/runners/csl-runners/gemma_4_31b_layer_block_smoke.py`
  and `bench/runners/csl-runners/e2b_layer_block_smoke.py`
- Gemma 4 31B AF16 lm-head cell:
  `bench/runners/csl-runners/gemma-4-31b-af16-cells/`
- Qwen 3.6 27B bounded per-kernel cells:
  `bench/runners/csl-runners/qwen-3-6-27b-cells/`
- Manifest contracts:
  `runtime/zig/examples/execution-v1/*smoke.json`

`MANIFEST.txt` records sha256, role, and path for every payload.
`BUNDLE_META.json` records the git commit and dirty-tree flag.

## Running cells

Gemma lm-head cell from the unpacked archive root:

```bash
python3 bench/tools/run_gemma4_31b_af16_simfabric_cells.py
```

For Qwen, see:

```bash
bench/runners/csl-runners/qwen-3-6-27b-cells/README.md
```

That README names the layout files with `_patched` suffixes where the
bounded cell differs from the manifest layout parameter forwarding.

## Scope

The sources here are bounded-shape simulator/emulator inputs. Manifest-shape
compile receipts and parity receipts live in the evidence bundle. Full-fabric
manifest-scale simulator execution remains a separate receipt path and is not
claimed by this source archive.
"""


def payload_rows(
    meta_bytes: bytes,
    readme_bytes: bytes,
) -> list[tuple[str, str, bytes]]:
    rows: list[tuple[str, str, bytes]] = [
        ("BUNDLE_META.json", "governance", meta_bytes),
        ("README.md", "governance", readme_bytes),
    ]
    for entry in INCLUDE_FILES:
        path = REPO_ROOT / entry.path
        if not path.is_file():
            raise FileNotFoundError(f"source archive include missing: {entry.path}")
        rows.append((entry.path, entry.role, path.read_bytes()))
    return rows


def manifest_text(rows: list[tuple[str, str, bytes]]) -> str:
    lines = [
        "# Doe Cerebras emulator source archive manifest",
        "# sha256  role  path",
    ]
    for path, role, data in rows:
        lines.append(f"{sha256_bytes(data)}  {role}  {path}")
    return "\n".join(lines) + "\n"


def add_bytes(
    archive: tarfile.TarFile,
    path: str,
    data: bytes,
    mode: int = 0o644,
) -> None:
    info = tarfile.TarInfo(path)
    info.size = len(data)
    info.mode = mode
    info.mtime = 0
    archive.addfile(info, io.BytesIO(data))


def file_mode(path: Path) -> int:
    mode = path.stat().st_mode & 0o777
    return mode or 0o644


def write_archive(out_path: Path, rows: list[tuple[str, str, bytes]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = manifest_text(rows).encode("utf-8")
    with tarfile.open(out_path, "w:gz") as archive:
        add_bytes(archive, "MANIFEST.txt", manifest_bytes)
        for path, _role, data in rows:
            source_path = REPO_ROOT / path
            mode = file_mode(source_path) if source_path.exists() else 0o644
            add_bytes(archive, path, data, mode=mode)


def verify_archive(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        try:
            manifest = archive.extractfile("MANIFEST.txt")
        except KeyError as exc:
            raise ValueError("archive missing MANIFEST.txt") from exc
        if manifest is None:
            raise ValueError("archive MANIFEST.txt is not a regular file")
        entries = manifest.read().decode("utf-8").splitlines()
        for line in entries:
            if not line or line.startswith("#"):
                continue
            parts = line.split("  ", 2)
            if len(parts) != 3:
                raise ValueError(f"invalid manifest line: {line}")
            expected, _role, rel_path = parts
            member = archive.extractfile(rel_path)
            if member is None:
                raise ValueError(f"archive payload missing: {rel_path}")
            actual = sha256_bytes(member.read())
            if actual != expected:
                raise ValueError(f"sha256 mismatch for {rel_path}")


def main() -> int:
    args = parse_args()
    commit = git_commit()
    dirty = git_dirty_tree()
    if dirty and not args.allow_dirty:
        sys.stderr.write(
            "pack_cerebras_emulator_source_archive: refusing to pack from "
            "a dirty work tree. Commit or pass --allow-dirty.\n"
        )
        return 2

    out_path = resolve(args.out) if args.out else default_out_path(commit)
    meta_bytes = (
        json.dumps(
            metadata(commit, dirty, out_path.name),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    readme_bytes = readme().encode("utf-8")
    rows = payload_rows(meta_bytes, readme_bytes)
    write_archive(out_path, rows)
    try:
        verify_archive(out_path)
    except (OSError, tarfile.TarError, ValueError) as exc:
        sys.stderr.write(f"archive verification failed: {exc}\n")
        return 1
    print(
        f"wrote {repo_rel(out_path)} "
        f"({sha256_file(out_path)}, {len(rows)} payload files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
