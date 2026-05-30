#!/usr/bin/env python3
"""Check native upload path receipts for comparability and asymmetry discipline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", required=True, help="Native upload path receipts JSON.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def check_receipts(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
    for index, row in enumerate(rows):
        row_path = f"rows[{index}]"
        if row.get("hiddenFallbackAllowed") is not False:
            failures.append(failure("hidden_fallback_allowed", f"{row_path}.hiddenFallbackAllowed", "hidden fallback must stay disabled"))
        if row.get("fallbackApplied") is True and not row.get("reasonCode"):
            failures.append(failure("missing_fallback_reason", f"{row_path}.reasonCode", "fallback rows require reasonCode"))
        if row.get("pathAsymmetry") is True and not row.get("pathAsymmetryNote"):
            failures.append(failure("missing_path_asymmetry_note", f"{row_path}.pathAsymmetryNote", "path asymmetry requires a note"))
        if row.get("pathAsymmetry") is True and row.get("claimEligible") is True:
            failures.append(failure("asymmetric_path_claimable", f"{row_path}.claimEligible", "path-asymmetric upload rows cannot be claim-eligible"))
        if row.get("strictComparable") is True and row.get("pathAsymmetry") is True:
            failures.append(failure("strict_row_path_asymmetry", f"{row_path}.pathAsymmetry", "strict comparable upload rows cannot carry path asymmetry"))
        if row.get("strictComparable") is True and row.get("uploadPath") != "staging_copy":
            failures.append(failure("strict_upload_not_staging_copy", f"{row_path}.uploadPath", "strict comparable upload rows must use staging_copy"))
        if row.get("uploadPath") == "staging_copy" and row.get("copyCommandsRecorded", 0) <= 0:
            failures.append(failure("missing_staging_copy_command", f"{row_path}.copyCommandsRecorded", "staging_copy rows must record copy commands"))
    return failures


def main() -> int:
    args = parse_args()
    failures = check_receipts(load_json(Path(args.receipts)))
    report = {
        "schemaVersion": 1,
        "artifactKind": "native_upload_path_receipts_check",
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: native upload path receipts")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: native upload path receipts")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
