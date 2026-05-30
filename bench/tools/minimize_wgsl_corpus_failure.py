#!/usr/bin/env python3
"""Emit identity-preserving WGSL minimization candidates for corpus failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
VALID_BACKENDS = {"msl", "spirv", "dxil", "hlsl"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="WGSL corpus manifest path.")
    parser.add_argument("--shader-id", required=True, help="Manifest shader id to minimize.")
    parser.add_argument("--taxonomy", default="config/shader-error-taxonomy.json")
    parser.add_argument("--taxonomy-code", required=True, help="Doe shader taxonomy code for the failure.")
    parser.add_argument("--failure-stage", required=True, help="Compiler stage where the failure was observed.")
    parser.add_argument("--diagnostic-category", default="none")
    parser.add_argument("--backend-target", action="append", choices=sorted(VALID_BACKENDS))
    parser.add_argument("--diagnostic-line", type=int)
    parser.add_argument("--context-lines", type=int, default=4)
    parser.add_argument("--out-dir", required=True, help="Directory for candidate WGSL files.")
    parser.add_argument("--receipt-out", help="Optional receipt path.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def normalize_source(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def normalized_sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_source(text).encode("utf-8")).hexdigest()


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def resolve_repo_path(repo_root: Path, path_text: str) -> Path:
    return repo_root.joinpath(*PurePosixPath(path_text).parts)


def safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return name or "candidate"


def find_manifest_row(manifest: dict[str, Any], shader_id: str) -> dict[str, Any]:
    for row in manifest.get("rows", []):
        if isinstance(row, dict) and row.get("shaderId") == shader_id:
            return row
    raise ValueError(f"shader id {shader_id!r} not found in manifest")


def find_taxonomy_entry(taxonomy: dict[str, Any], taxonomy_code: str) -> dict[str, Any]:
    for row in taxonomy.get("codes", []):
        if isinstance(row, dict) and row.get("code") == taxonomy_code:
            return row
    raise ValueError(f"taxonomy code {taxonomy_code!r} not found")


def line_window(lines: list[str], diagnostic_line: int | None, context_lines: int) -> tuple[str, int, int]:
    if diagnostic_line is None:
        return "\n".join(lines) + "\n", 1, len(lines)
    start = max(1, diagnostic_line - context_lines)
    end = min(len(lines), diagnostic_line + context_lines)
    return "\n".join(lines[start - 1 : end]) + "\n", start, end


def entrypoint_block(lines: list[str]) -> tuple[str, int, int] | None:
    start_index = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("@vertex") or stripped.startswith("@fragment") or stripped.startswith("@compute"):
            start_index = index
            break
        if stripped.startswith("fn "):
            start_index = index
            break
    if start_index is None:
        return None

    depth = 0
    saw_open = False
    end_index = start_index
    for index in range(start_index, len(lines)):
        line = lines[index]
        depth += line.count("{")
        if "{" in line:
            saw_open = True
        depth -= line.count("}")
        end_index = index
        if saw_open and depth <= 0:
            break
    return "\n".join(lines[start_index : end_index + 1]) + "\n", start_index + 1, end_index + 1


def drop_local_declarations(lines: list[str]) -> tuple[str, int, int]:
    kept = [
        line
        for line in lines
        if not line.strip().startswith(("let ", "var ", "const "))
    ]
    if not kept:
        kept = lines
    return "\n".join(kept) + "\n", 1, len(lines)


def add_candidate(
    candidates: list[dict[str, Any]],
    seen_hashes: set[str],
    *,
    shader_id: str,
    transformation: str,
    source_text: str,
    out_dir: Path,
    parent_hash: str,
    line_start: int,
    line_end: int,
) -> None:
    normalized = normalize_source(source_text)
    source_hash = normalized_sha256_text(normalized)
    if source_hash in seen_hashes:
        return
    seen_hashes.add(source_hash)
    candidate_name = safe_filename(transformation.replace("_", "-"))
    candidate_path = out_dir / f"{candidate_name}.wgsl"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(normalized, encoding="utf-8")
    candidates.append(
        {
            "candidateId": f"{shader_id}:{candidate_name}",
            "transformation": transformation,
            "candidatePath": str(candidate_path),
            "normalizedSourceSha256": source_hash,
            "parentSourceSha256": parent_hash,
            "retainedLineStart": line_start,
            "retainedLineEnd": line_end,
            "lineCount": len(normalized.splitlines()),
            "status": "pending_replay",
            "replayRequired": True,
        }
    )


def build_receipt(
    *,
    manifest: dict[str, Any],
    manifest_path: str,
    taxonomy: dict[str, Any],
    shader_id: str,
    taxonomy_code: str,
    failure_stage: str,
    diagnostic_category: str,
    backend_targets: list[str] | None,
    diagnostic_line: int | None,
    context_lines: int,
    out_dir: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    row = find_manifest_row(manifest, shader_id)
    taxonomy_entry = find_taxonomy_entry(taxonomy, taxonomy_code)
    if taxonomy_entry.get("stage") != failure_stage:
        raise ValueError(
            f"taxonomy code {taxonomy_code!r} has stage {taxonomy_entry.get('stage')!r}, not {failure_stage!r}"
        )

    source_path_text = str(row.get("sourcePath", ""))
    if not safe_repo_path(source_path_text):
        raise ValueError(f"unsafe sourcePath for {shader_id}: {source_path_text}")
    source_path = resolve_repo_path(repo_root, source_path_text)
    normalized_source = normalize_source(source_path.read_text(encoding="utf-8"))
    source_hash = normalized_sha256_text(normalized_source)
    if source_hash != row["normalizedSourceSha256"]:
        raise ValueError(f"manifest hash mismatch for {shader_id}: expected {row['normalizedSourceSha256']}, got {source_hash}")

    requested_targets = backend_targets or list(row["expectedBackendTargets"])
    missing_targets = sorted(set(requested_targets) - set(row["expectedBackendTargets"]))
    if missing_targets:
        raise ValueError(f"backend target not expected for {shader_id}: {', '.join(missing_targets)}")

    lines = normalized_source.splitlines()
    shader_out_dir = out_dir / safe_filename(shader_id)
    candidates: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    add_candidate(
        candidates,
        seen_hashes,
        shader_id=shader_id,
        transformation="normalized_original",
        source_text=normalized_source,
        out_dir=shader_out_dir,
        parent_hash=source_hash,
        line_start=1,
        line_end=len(lines),
    )

    window_source, window_start, window_end = line_window(lines, diagnostic_line, context_lines)
    add_candidate(
        candidates,
        seen_hashes,
        shader_id=shader_id,
        transformation="diagnostic_line_window",
        source_text=window_source,
        out_dir=shader_out_dir,
        parent_hash=source_hash,
        line_start=window_start,
        line_end=window_end,
    )

    block = entrypoint_block(lines)
    if block is not None:
        block_source, block_start, block_end = block
        add_candidate(
            candidates,
            seen_hashes,
            shader_id=shader_id,
            transformation="entrypoint_block",
            source_text=block_source,
            out_dir=shader_out_dir,
            parent_hash=source_hash,
            line_start=block_start,
            line_end=block_end,
        )

    drop_source, drop_start, drop_end = drop_local_declarations(lines)
    add_candidate(
        candidates,
        seen_hashes,
        shader_id=shader_id,
        transformation="drop_local_declarations",
        source_text=drop_source,
        out_dir=shader_out_dir,
        parent_hash=source_hash,
        line_start=drop_start,
        line_end=drop_end,
    )

    return {
        "schemaVersion": 1,
        "artifactKind": "wgsl_minimization_receipt",
        "receiptId": f"wgsl-minimize-{safe_filename(shader_id)}",
        "manifestPath": manifest_path,
        "corpusId": manifest["corpusId"],
        "source": {
            "shaderId": row["shaderId"],
            "category": row["category"],
            "sourcePath": row["sourcePath"],
            "normalizedSourceSha256": row["normalizedSourceSha256"],
            "expectedValidity": row["expectedValidity"],
            "expectedBackendTargets": row["expectedBackendTargets"],
            "shaderStages": row["shaderStages"],
        },
        "failure": {
            "stage": failure_stage,
            "taxonomyCode": taxonomy_code,
            "diagnosticCategory": diagnostic_category,
            "backendTargets": requested_targets,
        },
        "minimizationPolicy": {
            "candidateStatus": "pending_replay",
            "preservesOriginalIdentity": True,
            "freeFormDiagnosticCompared": False,
            "replayRequired": True,
        },
        "candidates": candidates,
    }


def main() -> int:
    args = parse_args()
    receipt = build_receipt(
        manifest=load_json(Path(args.manifest)),
        manifest_path=args.manifest,
        taxonomy=load_json(Path(args.taxonomy)),
        shader_id=args.shader_id,
        taxonomy_code=args.taxonomy_code,
        failure_stage=args.failure_stage,
        diagnostic_category=args.diagnostic_category,
        backend_targets=args.backend_target,
        diagnostic_line=args.diagnostic_line,
        context_lines=args.context_lines,
        out_dir=Path(args.out_dir),
    )
    encoded = json.dumps(receipt, indent=2)
    if args.receipt_out:
        Path(args.receipt_out).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
