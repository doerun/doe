#!/usr/bin/env python3
"""Build a WGSL CTS shader subset from the browser corpus manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="WGSL corpus manifest path.")
    parser.add_argument("--cts-evidence", required=True, help="WebGPU CTS evidence ledger path.")
    parser.add_argument("--out", help="Optional output path for wgsl_cts_shader_subset JSON.")
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


def build_subset(
    manifest: dict[str, Any],
    cts_evidence: dict[str, Any],
    *,
    manifest_path: str,
    cts_evidence_path: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    evidence_by_query = {
        row.get("query"): row
        for row in cts_evidence.get("evidence", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(manifest.get("rows", [])):
        if not isinstance(row, dict):
            continue
        provenance = row.get("provenance", {})
        if not isinstance(provenance, dict) or provenance.get("sourceKind") != "cts_shader_subset":
            continue
        cts_query = provenance.get("origin")
        evidence = evidence_by_query.get(cts_query)
        if not isinstance(evidence, dict):
            failures.append(
                failure(
                    "missing_cts_evidence",
                    f"rows[{row_index}].provenance.origin",
                    f"missing CTS evidence for query {cts_query!r}",
                )
            )
            continue
        source_path_text = str(row.get("sourcePath", ""))
        if not safe_repo_path(source_path_text):
            failures.append(
                failure(
                    "unsafe_source_path",
                    f"rows[{row_index}].sourcePath",
                    "sourcePath must be repo-relative",
                )
            )
            continue
        source_path = resolve_repo_path(repo_root, source_path_text)
        actual_hash = normalized_sha256(source_path)
        if actual_hash != row.get("normalizedSourceSha256"):
            failures.append(
                failure(
                    "source_hash_mismatch",
                    f"rows[{row_index}].normalizedSourceSha256",
                    f"expected {row.get('normalizedSourceSha256')}, got {actual_hash}",
                )
            )
            continue
        cts_artifact_path = str(evidence.get("artifactPath", ""))
        if not safe_repo_path(cts_artifact_path):
            failures.append(
                failure(
                    "unsafe_cts_artifact_path",
                    f"rows[{row_index}].ctsArtifactPath",
                    "ctsArtifactPath must be repo-relative",
                )
            )
            continue
        rows.append(
            {
                "ctsQuery": cts_query,
                "ctsBucket": evidence.get("bucket", "unknown"),
                "shaderId": row["shaderId"],
                "sourcePath": source_path_text,
                "normalizedSourceSha256": row["normalizedSourceSha256"],
                "expectedValidity": row["expectedValidity"],
                "expectedBackendTargets": row["expectedBackendTargets"],
                "shaderStages": row["shaderStages"],
                "ctsArtifactPath": cts_artifact_path,
            }
        )

    if not rows and not failures:
        failures.append(failure("missing_cts_shader_row", "rows", "manifest has no CTS shader subset rows"))

    return {
        "schemaVersion": 1,
        "artifactKind": "wgsl_cts_shader_subset",
        "subsetId": f"{manifest.get('corpusId', 'unknown')}-cts",
        "manifestPath": manifest_path,
        "ctsEvidencePath": cts_evidence_path,
        "ctsSource": cts_evidence.get("ctsSource", "unknown"),
        "ctsRevision": cts_evidence.get("ctsRevision", "unknown"),
        "subsetStatus": "fail" if failures else "pass",
        "rows": [] if failures else rows,
        "failureCodes": failures,
    }


def main() -> int:
    args = parse_args()
    subset = build_subset(
        load_json(Path(args.manifest)),
        load_json(Path(args.cts_evidence)),
        manifest_path=args.manifest,
        cts_evidence_path=args.cts_evidence,
    )
    encoded = json.dumps(subset, indent=2)
    if args.out:
        Path(args.out).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 1 if subset["subsetStatus"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
