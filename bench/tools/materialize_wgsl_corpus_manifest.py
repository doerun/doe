#!/usr/bin/env python3
"""Validate and materialize a WGSL corpus manifest."""

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
REQUIRED_CATEGORIES = {
    "browser_shader",
    "canvas_workload",
    "webgpu_sample",
    "model_inference_kernel",
    "game_engine_shader",
    "invalid_diagnostic_fixture",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="WGSL corpus manifest path.")
    parser.add_argument("--out-dir", required=True, help="Directory for normalized WGSL files.")
    parser.add_argument("--receipt-out", help="Optional materialization receipt path.")
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


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(normalize_source(path.read_text(encoding="utf-8")).encode("utf-8")).hexdigest()


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def resolve_repo_path(repo_root: Path, path_text: str) -> Path:
    return repo_root.joinpath(*PurePosixPath(path_text).parts)


def safe_filename(shader_id: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", shader_id).strip("._")
    return name or "shader"


def check_manifest(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    rows = payload.get("rows", [])
    categories = {row.get("category") for row in rows if isinstance(row, dict)}
    for category in sorted(REQUIRED_CATEGORIES - categories):
        failures.append(failure("missing_category", "rows", f"missing WGSL corpus category {category}"))

    seen_shader_ids: set[str] = set()
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row_path = f"rows[{row_index}]"
        shader_id = str(row.get("shaderId", ""))
        if shader_id in seen_shader_ids:
            failures.append(failure("duplicate_shader_id", f"{row_path}.shaderId", f"duplicate shader id {shader_id!r}"))
        seen_shader_ids.add(shader_id)

        source_path_text = str(row.get("sourcePath", ""))
        if not safe_repo_path(source_path_text):
            failures.append(
                failure(
                    "unsafe_source_path",
                    f"{row_path}.sourcePath",
                    "sourcePath must be repo-relative",
                )
            )
            continue
        source_path = resolve_repo_path(repo_root, source_path_text)
        if not source_path.is_file():
            failures.append(failure("source_not_found", f"{row_path}.sourcePath", f"source path not found: {source_path}"))
            continue
        actual_hash = normalized_sha256(source_path)
        expected_hash = row.get("normalizedSourceSha256")
        if actual_hash != expected_hash:
            failures.append(
                failure(
                    "source_hash_mismatch",
                    f"{row_path}.normalizedSourceSha256",
                    f"expected {expected_hash}, got {actual_hash}",
                )
            )
        if row.get("expectedValidity") == "invalid" and not row.get("expectedDiagnosticCategory"):
            failures.append(
                failure(
                    "missing_expected_diagnostic",
                    f"{row_path}.expectedDiagnosticCategory",
                    "invalid shader row requires expectedDiagnosticCategory",
                )
            )

    return failures


def materialize_manifest(
    payload: dict[str, Any],
    *,
    manifest_path: str,
    out_dir: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    failures = check_manifest(payload, repo_root=repo_root)
    if failures:
        return {
            "schemaVersion": 1,
            "artifactKind": "wgsl_corpus_materialization",
            "corpusId": payload.get("corpusId", "unknown"),
            "manifestPath": manifest_path,
            "outputRoot": str(out_dir),
            "materializationStatus": "fail",
            "rows": [],
            "failureCodes": failures,
        }

    materialized_rows: list[dict[str, Any]] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for row in payload["rows"]:
        source_path = resolve_repo_path(repo_root, row["sourcePath"])
        category_dir = out_dir / row["category"]
        category_dir.mkdir(parents=True, exist_ok=True)
        materialized_path = category_dir / f"{safe_filename(row['shaderId'])}.wgsl"
        materialized_path.write_text(normalize_source(source_path.read_text(encoding="utf-8")), encoding="utf-8")
        materialized_rows.append(
            {
                "shaderId": row["shaderId"],
                "category": row["category"],
                "sourcePath": row["sourcePath"],
                "materializedPath": str(materialized_path),
                "normalizedSourceSha256": row["normalizedSourceSha256"],
                "expectedValidity": row["expectedValidity"],
                "expectedBackendTargets": row["expectedBackendTargets"],
                "shaderStages": row["shaderStages"],
            }
        )

    return {
        "schemaVersion": 1,
        "artifactKind": "wgsl_corpus_materialization",
        "corpusId": payload["corpusId"],
        "manifestPath": manifest_path,
        "outputRoot": str(out_dir),
        "materializationStatus": "pass",
        "rows": materialized_rows,
        "failureCodes": [],
    }


def main() -> int:
    args = parse_args()
    receipt = materialize_manifest(
        load_json(Path(args.manifest)),
        manifest_path=args.manifest,
        out_dir=Path(args.out_dir),
    )
    encoded = json.dumps(receipt, indent=2)
    if args.receipt_out:
        Path(args.receipt_out).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 1 if receipt["materializationStatus"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
