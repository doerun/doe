#!/usr/bin/env python3
"""Check command encoder and resource reuse receipt discipline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", required=True, help="Native resource reuse receipts JSON.")
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
    for index, row in enumerate(row for row in payload.get("rows", []) if isinstance(row, dict)):
        row_path = f"rows[{index}]"
        if row.get("hiddenFallbackAllowed") is not False:
            failures.append(failure("hidden_fallback_allowed", f"{row_path}.hiddenFallbackAllowed", "hidden fallback must stay disabled"))
        if row.get("fallbackApplied") is True and not row.get("reasonCode"):
            failures.append(failure("missing_fallback_reason", f"{row_path}.reasonCode", "fallback rows require reasonCode"))
        if row.get("reuseApplied") is True and row.get("semanticsAllowReuse") is not True:
            failures.append(failure("reuse_without_semantics", f"{row_path}.reuseApplied", "reuse cannot be applied unless semanticsAllowReuse=true"))
        if row.get("claimEligible") is True and row.get("reuseApplied") is True:
            if row.get("resourceIdentityPreserved") is not True:
                failures.append(failure("resource_identity_not_preserved", f"{row_path}.resourceIdentityPreserved", "claimable reuse rows must preserve resource identity"))
            if row.get("commandOrderPreserved") is not True:
                failures.append(failure("command_order_not_preserved", f"{row_path}.commandOrderPreserved", "claimable reuse rows must preserve command order"))
        if row.get("claimEligible") is True and row.get("semanticsAllowReuse") is not True:
            failures.append(failure("claimable_reuse_semantics_missing", f"{row_path}.semanticsAllowReuse", "claimable reuse rows require semanticsAllowReuse=true"))
    return failures


def main() -> int:
    args = parse_args()
    failures = check_receipts(load_json(Path(args.receipts)))
    report = {
        "schemaVersion": 1,
        "artifactKind": "native_resource_reuse_receipts_check",
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: native resource reuse receipts")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: native resource reuse receipts")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
