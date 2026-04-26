#!/usr/bin/env python3
"""Validate every PROVENANCE.json under bench/out/ against config/doe-provenance.schema.json.

Mitigates the "Ad-hoc PROVENANCE.json files drift" risk from
docs/cerebras-north-star.md (Local risk mitigations). Walks bench/out/
for files named PROVENANCE.json, validates each against the canonical
schema, and emits a machine-readable report of conformance + a
non-zero exit on any validation failure.

Usage:
  python3 bench/tools/validate_provenance_files.py
  python3 bench/tools/validate_provenance_files.py --bench-out PATH --schema PATH
  python3 bench/tools/validate_provenance_files.py --report-out PATH

Exits 0 if every PROVENANCE.json validates; non-zero on the first
schema violation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCH_OUT = REPO_ROOT / "bench" / "out"
DEFAULT_SCHEMA = REPO_ROOT / "config" / "doe-provenance.schema.json"
DEFAULT_REPORT = REPO_ROOT / "bench" / "out" / "provenance-validation" / "report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bench-out",
        type=Path,
        default=DEFAULT_BENCH_OUT,
        help="Directory tree to scan for PROVENANCE.json files.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="Path to the doe-provenance schema.",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=DEFAULT_REPORT,
        help="Where to write the JSON report.",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Print every validation issue. Default shows first 20 then count.",
    )
    return parser.parse_args()


def find_provenance_files(bench_out: Path) -> list[Path]:
    return sorted(bench_out.rglob("PROVENANCE.json"))


def validate_one(
    path: Path, validator: jsonschema.Draft202012Validator
) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": str(path.relative_to(REPO_ROOT)),
            "status": "unreadable",
            "errors": [str(exc)],
        }
    if not isinstance(doc, dict):
        return {
            "path": str(path.relative_to(REPO_ROOT)),
            "status": "invalid",
            "errors": ["top-level value is not a JSON object"],
        }
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if not errors:
        return {
            "path": str(path.relative_to(REPO_ROOT)),
            "status": "pass",
            "errors": [],
        }
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "status": "fail",
        "errors": [
            {
                "schemaPath": "/".join(str(p) for p in e.absolute_path),
                "message": e.message,
            }
            for e in errors
        ],
    }


def main() -> int:
    args = parse_args()
    if not args.schema.is_file():
        print(f"FAIL: schema not found at {args.schema}", file=sys.stderr)
        return 1
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    paths = find_provenance_files(args.bench_out)
    results = [validate_one(p, validator) for p in paths]
    failed = [r for r in results if r["status"] != "pass"]

    report = {
        "schemaVersion": 1,
        "artifactKind": "doe_provenance_validation_report",
        "schemaPath": str(args.schema.relative_to(REPO_ROOT)),
        "scannedRoot": str(args.bench_out.relative_to(REPO_ROOT)),
        "totalFiles": len(results),
        "passCount": len(results) - len(failed),
        "failCount": len(failed),
        "results": results,
    }
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    if failed:
        print(
            f"FAIL: {len(failed)} of {len(results)} PROVENANCE.json files do "
            f"not validate against {args.schema.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        shown = failed if args.show_all else failed[:20]
        for r in shown:
            print(f"  {r['path']}: {r['status']}", file=sys.stderr)
            for e in r["errors"][:3]:
                if isinstance(e, dict):
                    print(f"    {e['schemaPath']}: {e['message']}", file=sys.stderr)
                else:
                    print(f"    {e}", file=sys.stderr)
        if not args.show_all and len(failed) > 20:
            print(f"  ... and {len(failed) - 20} more", file=sys.stderr)
        return 1

    print(
        f"PASS: {len(results)} PROVENANCE.json files validate against "
        f"{args.schema.relative_to(REPO_ROOT)} (report: {args.report_out.relative_to(REPO_ROOT)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
