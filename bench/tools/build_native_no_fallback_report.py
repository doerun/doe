#!/usr/bin/env python3
"""Build strict no-fallback reports for native Doe run receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-receipt", action="append", required=True, help="Run receipt path.")
    parser.add_argument("--out", required=True, help="Output no-fallback report path.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def relative_or_absolute(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sample_fallback_used(sample: dict[str, Any]) -> bool:
    if sample.get("fallbackUsed") is True or sample.get("fallback_used") is True:
        return True
    trace_meta = sample.get("traceMeta")
    if isinstance(trace_meta, dict):
        return trace_meta.get("fallbackUsed") is True or trace_meta.get("fallback_used") is True
    return False


def build_row(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    runtime_identity = payload.get("runtimeIdentity", {})
    product = str(payload.get("product", ""))
    runtime_host = str(runtime_identity.get("runtimeHost", "")) if isinstance(runtime_identity, dict) else ""
    execution_backend = str(runtime_identity.get("executionBackend", "")) if isinstance(runtime_identity, dict) else ""
    failures: list[dict[str, str]] = []

    if product != "doe":
        failures.append(failure("non_doe_product", "product", f"expected doe, got {product!r}"))
    if runtime_host != "native":
        failures.append(failure("non_native_runtime_host", "runtimeIdentity.runtimeHost", f"expected native, got {runtime_host!r}"))
    if not execution_backend.startswith("doe_"):
        failures.append(
            failure(
                "non_doe_execution_backend",
                "runtimeIdentity.executionBackend",
                f"expected doe_* backend, got {execution_backend!r}",
            )
        )

    samples = payload.get("samples", [])
    fallback_used = False
    if isinstance(samples, list):
        fallback_used = any(isinstance(sample, dict) and sample_fallback_used(sample) for sample in samples)
    if fallback_used:
        failures.append(failure("sample_fallback_used", "samples", "at least one sample reports fallbackUsed"))

    return {
        "runReceiptPath": relative_or_absolute(path),
        "runReceiptSha256": sha256_file(path),
        "product": product,
        "runtimeHost": runtime_host,
        "executionBackend": execution_backend,
        "fallbackUsed": False,
        "status": "fail" if failures else "pass",
        "failureCodes": failures,
    }


def build_report(paths: list[Path]) -> dict[str, Any]:
    rows = [build_row(path, load_json(path)) for path in paths]
    failures = [item for row in rows for item in row["failureCodes"]]
    pass_count = sum(1 for row in rows if row["status"] == "pass")
    return {
        "schemaVersion": 1,
        "artifactKind": "native_no_fallback_report",
        "strictNoFallback": True,
        "status": "fail" if failures else "pass",
        "rows": rows,
        "summary": {
            "rowCount": len(rows),
            "passCount": pass_count,
            "failCount": len(rows) - pass_count,
            "failureCodes": failures,
        },
    }


def main() -> int:
    args = parse_args()
    report = build_report([Path(path) for path in args.run_receipt])
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
