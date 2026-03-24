#!/usr/bin/env python3
"""Validate governed CSL compile/run/parity reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="bench/out/csl-governed-lane.report.json")
    parser.add_argument("--schema", default="config/csl-governed-lane-report.schema.json")
    parser.add_argument("--require-parity-match", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-compile-success", action="store_true")
    parser.add_argument("--require-run-success", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = (REPO_ROOT / report_path).resolve()
    schema_path = Path(args.schema)
    if not schema_path.is_absolute():
        schema_path = (REPO_ROOT / schema_path).resolve()
    report = load_json(report_path)
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator(schema).validate(report)

    failures: list[str] = []
    if report.get("laneStatus") == "failed":
        failures.append("laneStatus=failed")
    if args.require_parity_match and report.get("parity", {}).get("status") != "matched":
        failures.append(f"parity.status={report.get('parity', {}).get('status')!r}")
    if args.require_compile_success and report.get("compile", {}).get("status") != "succeeded":
        failures.append(f"compile.status={report.get('compile', {}).get('status')!r}")
    if args.require_run_success and report.get("run", {}).get("status") != "succeeded":
        failures.append(f"run.status={report.get('run', {}).get('status')!r}")

    if failures:
        print("FAIL: csl governed lane gate")
        for item in failures:
            print(f"  {item}")
        return 1

    print("PASS: csl governed lane gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
