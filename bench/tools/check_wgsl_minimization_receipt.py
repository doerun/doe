#!/usr/bin/env python3
"""Check WGSL corpus minimization receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, help="wgsl_minimization_receipt JSON path.")
    parser.add_argument(
        "--verify-files-root",
        default="",
        help="Resolve relative source/candidate paths under this root and verify normalized hashes.",
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


def normalize_source(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(
        normalize_source(path.read_text(encoding="utf-8")).encode("utf-8")
    ).hexdigest()


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def resolve_path(path_text: str, verify_files_root: Path) -> Path | None:
    root = verify_files_root.resolve()
    path = Path(path_text)
    candidate = path if path.is_absolute() else root.joinpath(*PurePosixPath(path_text).parts)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def check_receipt(
    payload: dict[str, Any],
    verify_files_root: Path | None = None,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("artifactKind") != "wgsl_minimization_receipt":
        failures.append(
            failure("invalid_artifact_kind", "artifactKind", "artifactKind must be wgsl_minimization_receipt")
        )

    source = payload.get("source")
    if not isinstance(source, dict):
        failures.append(failure("missing_source", "source", "source identity is required"))
        source = {}
    shader_id = source.get("shaderId")
    source_hash = source.get("normalizedSourceSha256")
    if not isinstance(shader_id, str) or not shader_id:
        failures.append(failure("missing_shader_id", "source.shaderId", "source shaderId is required"))
        shader_id = ""
    if not is_sha256(source_hash):
        failures.append(failure("missing_source_hash", "source.normalizedSourceSha256", "source hash must be sha256 hex"))
    source_path = source.get("sourcePath")
    if isinstance(source_path, str) and source_path and not safe_repo_path(source_path):
        failures.append(
            failure(
                "unsafe_source_path",
                "source.sourcePath",
                "sourcePath must be repo-relative",
            )
        )
    if (
        verify_files_root is not None
        and isinstance(source_path, str)
        and safe_repo_path(source_path)
        and is_sha256(source_hash)
    ):
        resolved_source = resolve_path(source_path, verify_files_root)
        if resolved_source is None:
            failures.append(
                failure(
                    "unsafe_source_path",
                    "source.sourcePath",
                    "sourcePath must resolve under verify-files-root",
                )
            )
        elif not resolved_source.is_file():
            failures.append(
                failure(
                    "source_file_missing",
                    "source.sourcePath",
                    f"source file not found: {source_path}",
                )
            )
        else:
            actual_hash = normalized_sha256(resolved_source)
            if actual_hash != source_hash:
                failures.append(
                    failure(
                        "source_hash_mismatch",
                        "source.normalizedSourceSha256",
                        f"expected {source_hash}, got {actual_hash}",
                    )
                )

    failure_identity = payload.get("failure")
    if not isinstance(failure_identity, dict):
        failures.append(failure("missing_failure_identity", "failure", "failure identity is required"))
        failure_identity = {}
    if not failure_identity.get("stage"):
        failures.append(failure("missing_failure_stage", "failure.stage", "failure stage is required"))
    if not failure_identity.get("taxonomyCode"):
        failures.append(failure("missing_taxonomy_code", "failure.taxonomyCode", "taxonomy code is required"))

    expected_targets = source.get("expectedBackendTargets")
    backend_targets = failure_identity.get("backendTargets")
    if isinstance(expected_targets, list) and isinstance(backend_targets, list):
        missing = sorted(set(backend_targets) - set(expected_targets))
        if missing:
            failures.append(
                failure(
                    "unexpected_backend_target",
                    "failure.backendTargets",
                    f"failure backend targets not expected by source: {', '.join(missing)}",
                )
            )

    policy = payload.get("minimizationPolicy")
    if not isinstance(policy, dict):
        failures.append(failure("missing_minimization_policy", "minimizationPolicy", "minimization policy is required"))
        policy = {}
    if policy.get("candidateStatus") != "pending_replay":
        failures.append(failure("candidate_status_not_pending", "minimizationPolicy.candidateStatus", "candidate status must be pending_replay"))
    if policy.get("preservesOriginalIdentity") is not True:
        failures.append(failure("identity_not_preserved", "minimizationPolicy.preservesOriginalIdentity", "original identity must be preserved"))
    if policy.get("freeFormDiagnosticCompared") is not False:
        failures.append(failure("free_form_diagnostic_compared", "minimizationPolicy.freeFormDiagnosticCompared", "free-form diagnostics cannot be compared"))
    if policy.get("replayRequired") is not True:
        failures.append(failure("replay_not_required", "minimizationPolicy.replayRequired", "replay must be required"))

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        failures.append(failure("missing_candidates", "candidates", "minimization candidates must be non-empty"))
        return failures

    seen_candidate_ids: set[str] = set()
    transformations: set[str] = set()
    for index, candidate in enumerate(candidates):
        candidate_path = f"candidates[{index}]"
        if not isinstance(candidate, dict):
            failures.append(failure("invalid_candidate", candidate_path, "candidate must be an object"))
            continue
        candidate_id = candidate.get("candidateId")
        if not isinstance(candidate_id, str) or not candidate_id:
            failures.append(failure("missing_candidate_id", f"{candidate_path}.candidateId", "candidateId is required"))
        elif candidate_id in seen_candidate_ids:
            failures.append(failure("duplicate_candidate_id", f"{candidate_path}.candidateId", f"duplicate candidateId {candidate_id}"))
        else:
            seen_candidate_ids.add(candidate_id)
        if shader_id and isinstance(candidate_id, str) and not candidate_id.startswith(f"{shader_id}:"):
            failures.append(failure("candidate_shader_id_mismatch", f"{candidate_path}.candidateId", "candidateId must preserve source shaderId"))
        transformation = candidate.get("transformation")
        if isinstance(transformation, str):
            transformations.add(transformation)
        if not is_sha256(candidate.get("normalizedSourceSha256")):
            failures.append(failure("missing_candidate_hash", f"{candidate_path}.normalizedSourceSha256", "candidate hash must be sha256 hex"))
        if candidate.get("parentSourceSha256") != source_hash:
            failures.append(failure("parent_hash_mismatch", f"{candidate_path}.parentSourceSha256", "candidate parent hash must match source hash"))
        candidate_file = candidate.get("candidatePath")
        candidate_hash = candidate.get("normalizedSourceSha256")
        if verify_files_root is not None and isinstance(candidate_file, str) and is_sha256(candidate_hash):
            resolved_candidate = resolve_path(candidate_file, verify_files_root)
            if resolved_candidate is None:
                failures.append(
                    failure(
                        "unsafe_candidate_path",
                        f"{candidate_path}.candidatePath",
                        "candidatePath must resolve under verify-files-root",
                    )
                )
                continue
            if not resolved_candidate.is_file():
                failures.append(
                    failure(
                        "candidate_file_missing",
                        f"{candidate_path}.candidatePath",
                        f"candidate file not found: {candidate_file}",
                    )
                )
            else:
                actual_hash = normalized_sha256(resolved_candidate)
                if actual_hash != candidate_hash:
                    failures.append(
                        failure(
                            "candidate_hash_mismatch",
                            f"{candidate_path}.normalizedSourceSha256",
                            f"expected {candidate_hash}, got {actual_hash}",
                        )
                    )
        if candidate.get("status") != "pending_replay":
            failures.append(failure("candidate_status_not_pending", f"{candidate_path}.status", "candidate status must be pending_replay"))
        if candidate.get("replayRequired") is not True:
            failures.append(failure("candidate_replay_not_required", f"{candidate_path}.replayRequired", "candidate replay must be required"))
        start = candidate.get("retainedLineStart")
        end = candidate.get("retainedLineEnd")
        if isinstance(start, int) and isinstance(end, int) and end < start:
            failures.append(failure("invalid_line_range", f"{candidate_path}.retainedLineEnd", "retainedLineEnd must be >= retainedLineStart"))
    if "normalized_original" not in transformations:
        failures.append(failure("missing_original_candidate", "candidates", "normalized_original candidate is required"))
    return failures


def main() -> int:
    args = parse_args()
    verify_files_root = Path(args.verify_files_root).resolve() if args.verify_files_root else None
    failures = check_receipt(load_json(Path(args.receipt)), verify_files_root)
    report = {
        "schemaVersion": 1,
        "artifactKind": "wgsl_minimization_receipt_check",
        "receiptPath": args.receipt,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: WGSL minimization receipt")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: WGSL minimization receipt")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
