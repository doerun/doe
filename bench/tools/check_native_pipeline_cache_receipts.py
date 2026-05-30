#!/usr/bin/env python3
"""Check native pipeline cache cold/warm receipt discipline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", required=True, help="Native pipeline cache receipts JSON.")
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
    modes_by_workload: dict[str, set[str]] = {}
    for index, row in enumerate(rows):
        row_path = f"rows[{index}]"
        workload_id = str(row.get("workloadId", ""))
        modes_by_workload.setdefault(workload_id, set()).add(str(row.get("mode", "")))
        if row.get("hiddenFallbackAllowed") is not False:
            failures.append(failure("hidden_fallback_allowed", f"{row_path}.hiddenFallbackAllowed", "hidden fallback must stay disabled"))
        if row.get("fallbackApplied") is True and not row.get("reasonCode"):
            failures.append(failure("missing_fallback_reason", f"{row_path}.reasonCode", "fallback rows require reasonCode"))
        if row.get("pathAsymmetry") is True and not row.get("pathAsymmetryNote"):
            failures.append(failure("missing_path_asymmetry_note", f"{row_path}.pathAsymmetryNote", "path asymmetry requires a note"))
        if row.get("mode") == "warm" and row.get("cacheState") in {"miss", "created"}:
            failures.append(failure("warm_mode_not_warm", f"{row_path}.cacheState", "warm mode must report hit or disabled"))
        if row.get("mode") == "cold" and row.get("cacheState") == "hit":
            failures.append(failure("cold_mode_reports_hit", f"{row_path}.cacheState", "cold mode cannot report a cache hit"))

    for workload_id, modes in sorted(modes_by_workload.items()):
        if not {"cold", "warm"}.issubset(modes):
            failures.append(failure("missing_cold_warm_pair", "rows", f"workload {workload_id!r} must carry cold and warm rows"))
    return failures


def main() -> int:
    args = parse_args()
    failures = check_receipts(load_json(Path(args.receipts)))
    report = {
        "schemaVersion": 1,
        "artifactKind": "native_pipeline_cache_receipts_check",
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: native pipeline cache receipts")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: native pipeline cache receipts")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
