#!/usr/bin/env python3
"""Check strict native no-fallback reports."""

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
    parser.add_argument("--report", required=True, help="native_no_fallback_report JSON path.")
    parser.add_argument(
        "--verify-files-root",
        default="",
        help="Resolve relative run receipt paths under this root and verify sha256 values.",
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


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_path(path_text: str, verify_files_root: Path | None) -> Path:
    path = Path(path_text)
    if path.is_absolute() or verify_files_root is None:
        return path
    return verify_files_root / path


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def check_report(payload: dict[str, Any], verify_files_root: Path | None = None) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("artifactKind") != "native_no_fallback_report":
        failures.append(failure("invalid_artifact_kind", "artifactKind", "artifactKind must be native_no_fallback_report"))
    if payload.get("strictNoFallback") is not True:
        failures.append(failure("strict_no_fallback_disabled", "strictNoFallback", "strictNoFallback must be true"))
    if payload.get("status") != "pass":
        failures.append(failure("report_status_not_pass", "status", "status must be pass"))

    rows = payload.get("rows", [])
    if not isinstance(rows, list) or not rows:
        failures.append(failure("missing_rows", "rows", "no-fallback report rows must be non-empty"))
        return failures

    pass_count = 0
    fail_count = 0
    row_failures: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, row in enumerate(rows):
        row_path = f"rows[{index}]"
        if not isinstance(row, dict):
            failures.append(failure("invalid_row", row_path, "row must be an object"))
            continue
        receipt_path = row.get("runReceiptPath")
        if not isinstance(receipt_path, str) or not receipt_path:
            failures.append(failure("missing_run_receipt_path", f"{row_path}.runReceiptPath", "runReceiptPath is required"))
        elif receipt_path in seen_paths:
            failures.append(failure("duplicate_run_receipt_path", f"{row_path}.runReceiptPath", f"duplicate runReceiptPath {receipt_path}"))
        else:
            seen_paths.add(receipt_path)
        receipt_hash = row.get("runReceiptSha256")
        if not is_sha256(receipt_hash):
            failures.append(failure("missing_run_receipt_hash", f"{row_path}.runReceiptSha256", "runReceiptSha256 must be sha256 hex"))
        if row.get("product") != "doe":
            failures.append(failure("non_doe_product", f"{row_path}.product", "product must be doe"))
        if row.get("runtimeHost") != "native":
            failures.append(failure("non_native_runtime_host", f"{row_path}.runtimeHost", "runtimeHost must be native"))
        execution_backend = row.get("executionBackend")
        if not isinstance(execution_backend, str) or not execution_backend.startswith("doe_"):
            failures.append(failure("non_doe_execution_backend", f"{row_path}.executionBackend", "executionBackend must start with doe_"))
        if row.get("fallbackUsed") is not False:
            failures.append(failure("fallback_used", f"{row_path}.fallbackUsed", "fallbackUsed must be false"))
        status = row.get("status")
        if status == "pass":
            pass_count += 1
            if row.get("failureCodes"):
                failures.append(failure("passing_row_has_failures", f"{row_path}.failureCodes", "passing rows cannot carry failures"))
        elif status == "fail":
            fail_count += 1
        else:
            failures.append(failure("invalid_row_status", f"{row_path}.status", "row status must be pass or fail"))
        row_codes = row.get("failureCodes")
        if not isinstance(row_codes, list):
            failures.append(failure("invalid_row_failures", f"{row_path}.failureCodes", "failureCodes must be an array"))
            row_codes = []
        row_failures.extend(item for item in row_codes if isinstance(item, dict))
        if verify_files_root is not None and isinstance(receipt_path, str) and is_sha256(receipt_hash):
            if not safe_repo_path(receipt_path):
                failures.append(
                    failure(
                        "unsafe_run_receipt_path",
                        f"{row_path}.runReceiptPath",
                        "runReceiptPath must be repo-relative",
                    )
                )
                continue
            resolved = resolve_path(receipt_path, verify_files_root)
            if not resolved.is_file():
                failures.append(failure("run_receipt_missing", f"{row_path}.runReceiptPath", f"run receipt not found: {receipt_path}"))
            else:
                actual_hash = sha256_file(resolved)
                if actual_hash != receipt_hash:
                    failures.append(
                        failure(
                            "run_receipt_hash_mismatch",
                            f"{row_path}.runReceiptSha256",
                            f"expected {actual_hash}, got {receipt_hash}",
                        )
                    )

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        failures.append(failure("missing_summary", "summary", "summary must be an object"))
        summary = {}
    expected_counts = {
        "rowCount": len(rows),
        "passCount": pass_count,
        "failCount": fail_count,
    }
    for key, expected in expected_counts.items():
        if summary.get(key) != expected:
            failures.append(failure("summary_count_mismatch", f"summary.{key}", f"{key} must be {expected}"))
    summary_failures = summary.get("failureCodes")
    if not isinstance(summary_failures, list):
        failures.append(failure("invalid_summary_failures", "summary.failureCodes", "failureCodes must be an array"))
    elif len(summary_failures) != len(row_failures):
        failures.append(
            failure(
                "summary_failure_count_mismatch",
                "summary.failureCodes",
                "summary failureCodes must mirror row failureCodes",
            )
        )
    return failures


def main() -> int:
    args = parse_args()
    verify_files_root = Path(args.verify_files_root).resolve() if args.verify_files_root else None
    failures = check_report(load_json(Path(args.report)), verify_files_root)
    report = {
        "schemaVersion": 1,
        "artifactKind": "native_no_fallback_report_check",
        "reportPath": args.report,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: native no-fallback report")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: native no-fallback report")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
