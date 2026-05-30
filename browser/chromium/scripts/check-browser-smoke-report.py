#!/usr/bin/env python3
"""Validate Chromium WebGPU smoke report evidence without launching Chromium."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BENCH_ROOT = REPO_ROOT / "bench"
for path in (str(REPO_ROOT), str(BENCH_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from bench.browser.browser_gate import validate_smoke_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-report", required=True, help="Chromium WebGPU smoke report JSON path.")
    parser.add_argument(
        "--require-modes",
        default="dawn,doe",
        help="Comma-separated smoke modes that must be present. Supported: dawn,doe.",
    )
    parser.add_argument(
        "--no-require-strict",
        action="store_true",
        help="Do not require methodology.strictMode=true.",
    )
    parser.add_argument(
        "--no-require-hash-chain",
        action="store_true",
        help="Do not recompute reportHash or modeResult hash-chain fields.",
    )
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def parse_modes(raw: str) -> tuple[str, ...]:
    modes = tuple(mode.strip() for mode in raw.split(",") if mode.strip())
    if not modes:
        raise ValueError("--require-modes must name at least one mode")
    return modes


def failure_from_error(message: str) -> dict[str, str]:
    return {"code": "smoke_report_contract_failure", "path": "smokeReport", "message": message}


def main() -> int:
    args = parse_args()
    smoke_report = Path(args.smoke_report)
    modes = parse_modes(args.require_modes)
    failures = [
        failure_from_error(message)
        for message in validate_smoke_report(
            load_json(smoke_report),
            required_modes=modes,
            require_strict=not args.no_require_strict,
            require_hash_chain=not args.no_require_hash_chain,
        )
    ]
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_smoke_report_check",
        "smokeReportPath": str(smoke_report),
        "requiredModes": list(modes),
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser smoke report")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser smoke report")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
