#!/usr/bin/env python3
"""Check WGSL CTS shader subset artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", required=True, help="wgsl_cts_shader_subset JSON path.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def check_subset(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("artifactKind") != "wgsl_cts_shader_subset":
        failures.append(failure("invalid_artifact_kind", "artifactKind", "artifactKind must be wgsl_cts_shader_subset"))
    if payload.get("subsetStatus") != "pass":
        failure_codes = payload.get("failureCodes")
        if isinstance(failure_codes, list) and failure_codes:
            for index, item in enumerate(failure_codes):
                if isinstance(item, dict):
                    failures.append(
                        failure(
                            str(item.get("code", "cts_subset_failure")),
                            str(item.get("path", f"failureCodes[{index}]")),
                            str(item.get("message", "CTS subset failure")),
                        )
                    )
        else:
            failures.append(failure("subset_status_not_pass", "subsetStatus", "subsetStatus must be pass"))

    rows = payload.get("rows", [])
    if not isinstance(rows, list) or not rows:
        failures.append(failure("missing_cts_shader_row", "rows", "CTS shader subset rows must be non-empty"))
        return failures

    seen_shader_ids: set[str] = set()
    seen_queries: set[str] = set()
    for index, row in enumerate(rows):
        row_path = f"rows[{index}]"
        if not isinstance(row, dict):
            failures.append(failure("invalid_cts_shader_row", row_path, "CTS shader row must be an object"))
            continue
        shader_id = row.get("shaderId")
        cts_query = row.get("ctsQuery")
        if not isinstance(shader_id, str) or not shader_id:
            failures.append(failure("missing_shader_id", f"{row_path}.shaderId", "shaderId is required"))
        elif shader_id in seen_shader_ids:
            failures.append(failure("duplicate_shader_id", f"{row_path}.shaderId", f"duplicate shaderId {shader_id}"))
        else:
            seen_shader_ids.add(shader_id)
        if not isinstance(cts_query, str) or not cts_query:
            failures.append(failure("missing_cts_query", f"{row_path}.ctsQuery", "ctsQuery is required"))
        elif cts_query in seen_queries:
            failures.append(failure("duplicate_cts_query", f"{row_path}.ctsQuery", f"duplicate ctsQuery {cts_query}"))
        else:
            seen_queries.add(cts_query)
        if not is_sha256(row.get("normalizedSourceSha256")):
            failures.append(failure("missing_source_hash", f"{row_path}.normalizedSourceSha256", "source hash must be sha256 hex"))
        for field in ("sourcePath", "ctsBucket", "ctsArtifactPath"):
            if not row.get(field):
                failures.append(failure("missing_cts_shader_field", f"{row_path}.{field}", f"{field} is required"))
        for field, code in (
            ("sourcePath", "unsafe_source_path"),
            ("ctsArtifactPath", "unsafe_cts_artifact_path"),
        ):
            path_text = row.get(field)
            if isinstance(path_text, str) and path_text and not safe_repo_path(path_text):
                failures.append(
                    failure(
                        code,
                        f"{row_path}.{field}",
                        f"{field} must be repo-relative",
                    )
                )
        if not isinstance(row.get("expectedBackendTargets"), list) or not row.get("expectedBackendTargets"):
            failures.append(failure("missing_backend_targets", f"{row_path}.expectedBackendTargets", "backend targets are required"))
        if not isinstance(row.get("shaderStages"), list) or not row.get("shaderStages"):
            failures.append(failure("missing_shader_stages", f"{row_path}.shaderStages", "shader stages are required"))
    return failures


def main() -> int:
    args = parse_args()
    failures = check_subset(load_json(Path(args.subset)))
    report = {
        "schemaVersion": 1,
        "artifactKind": "wgsl_cts_shader_subset_check",
        "subsetPath": args.subset,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: WGSL CTS shader subset")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: WGSL CTS shader subset")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
