#!/usr/bin/env python3
"""Check native backend coverage matrix completeness and evidence discipline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


REQUIRED_BACKENDS = {"doe_metal", "doe_vulkan", "doe_d3d12"}
REQUIRED_CLASSES = {
    "upload",
    "pipeline_creation",
    "compute",
    "readback",
    "small_command_stream",
    "cache_behavior",
    "concurrency",
    "tails",
}
EXPECTED_ARTIFACT_KINDS = {
    "upload": {"native_upload_path_receipts"},
    "pipeline_creation": {"native_pipeline_cache_receipts"},
    "compute": {"run-receipt", "native_command_graph_receipt"},
    "readback": {"run-receipt", "native_command_graph_receipt"},
    "small_command_stream": {"native_command_graph_receipt"},
    "cache_behavior": {"native_pipeline_cache_receipts"},
    "concurrency": {"run-receipt", "native_command_graph_receipt"},
    "tails": {"run-receipt", "native_command_graph_receipt"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True, help="Native backend coverage matrix JSON.")
    parser.add_argument(
        "--verify-evidence-root",
        default="",
        help="Resolve relative covered-row evidence paths under this root and verify artifact kind.",
    )
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def resolve_path(path_text: str, root: Path | None) -> Path:
    path = Path(path_text)
    if path.is_absolute() or root is None:
        return path
    return root / path


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def check_evidence_file(
    row: dict[str, Any],
    row_path: str,
    evidence_root: Path | None,
) -> list[dict[str, str]]:
    if evidence_root is None or row.get("status") != "covered":
        return []
    evidence_path = row.get("evidencePath")
    if not isinstance(evidence_path, str) or not evidence_path:
        return []
    if not safe_repo_path(evidence_path):
        return [failure("unsafe_evidence_path", f"{row_path}.evidencePath", "evidencePath must be repo-relative")]
    resolved = resolve_path(evidence_path, evidence_root)
    if not resolved.is_file():
        return [failure("evidence_file_missing", f"{row_path}.evidencePath", f"evidence file not found: {evidence_path}")]
    try:
        payload = load_json(resolved)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [failure("evidence_file_invalid", f"{row_path}.evidencePath", str(exc))]
    expected_kinds = EXPECTED_ARTIFACT_KINDS.get(str(row.get("coverageClass", "")), set())
    artifact_kind = payload.get("artifactKind")
    if expected_kinds and artifact_kind not in expected_kinds:
        return [
            failure(
                "evidence_artifact_kind_mismatch",
                f"{row_path}.evidencePath",
                f"expected one of {sorted(expected_kinds)}, got {artifact_kind!r}",
            )
        ]
    return []


def check_matrix(payload: dict[str, Any], evidence_root: Path | None = None) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(row for row in payload.get("rows", []) if isinstance(row, dict)):
        row_path = f"rows[{index}]"
        key = (str(row.get("backend", "")), str(row.get("coverageClass", "")))
        if key in seen:
            failures.append(failure("duplicate_coverage_row", row_path, f"duplicate coverage row {key}"))
        seen.add(key)
        status = row.get("status")
        if status == "covered" and not row.get("evidencePath"):
            failures.append(failure("covered_row_missing_evidence", f"{row_path}.evidencePath", "covered rows require evidencePath"))
        if status != "covered" and not row.get("reasonCode"):
            failures.append(failure("diagnostic_row_missing_reason", f"{row_path}.reasonCode", "diagnostic and missing rows require reasonCode"))
        if status == "covered" and row.get("reasonCode"):
            failures.append(failure("covered_row_has_reason", f"{row_path}.reasonCode", "covered rows must not carry reasonCode"))
        failures.extend(check_evidence_file(row, row_path, evidence_root))

    for backend in sorted(REQUIRED_BACKENDS):
        for coverage_class in sorted(REQUIRED_CLASSES):
            if (backend, coverage_class) not in seen:
                failures.append(failure("missing_coverage_row", "rows", f"missing coverage row {backend}:{coverage_class}"))
    return failures


def main() -> int:
    args = parse_args()
    evidence_root = Path(args.verify_evidence_root).resolve() if args.verify_evidence_root else None
    failures = check_matrix(load_json(Path(args.matrix)), evidence_root)
    report = {
        "schemaVersion": 1,
        "artifactKind": "native_backend_coverage_matrix_check",
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: native backend coverage matrix")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: native backend coverage matrix")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
