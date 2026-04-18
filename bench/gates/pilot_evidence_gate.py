#!/usr/bin/env python3
"""Validate pilot-evidence receipts and their artifact bundles.

A pilot-evidence receipt points at an `artifactBundle` directory with a
manifest of files, each pinned by a sha256 and a byte size. This gate:

1. Locates every receipt registered against config/pilot-evidence-receipt.schema.json
   via config/schema-targets.json, or accepts explicit paths via --receipt.
2. Checks that the bundle directory exists.
3. Verifies every manifest entry resolves to a real file under the bundle
   path, matches the declared sha256, and matches the declared size.
4. Rejects manifests that list files outside the bundle directory.

Treat this gate as blocking when a receipt is offered as pilot evidence;
the scaffolding marks it optional in `run_blocking_gates.py` because not
every repo-level gate run has a receipt to audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.lib.bench_utils import detect_repo_root, load_json

PILOT_EVIDENCE_SCHEMA = "config/pilot-evidence-receipt.schema.json"


@dataclass(frozen=True)
class ReceiptTarget:
    path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="",
        help="Repository root. Auto-detected when omitted.",
    )
    parser.add_argument(
        "--receipt",
        action="append",
        default=[],
        help=(
            "Pilot-evidence receipt path relative to root. May be repeated. "
            "Defaults to receipts registered against the pilot-evidence schema."
        ),
    )
    return parser.parse_args()


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def require_array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def load_registered_receipts(root: Path) -> list[ReceiptTarget]:
    registry = require_object(
        load_json(root / "config" / "schema-targets.json"),
        "config/schema-targets.json",
    )
    targets: list[ReceiptTarget] = []
    for index, entry in enumerate(require_array(registry.get("targets"), "targets")):
        entry_obj = require_object(entry, f"targets[{index}]")
        schema_path = require_string(entry_obj.get("schema"), f"targets[{index}].schema")
        data_path = require_string(entry_obj.get("data"), f"targets[{index}].data")
        if schema_path == PILOT_EVIDENCE_SCHEMA:
            targets.append(ReceiptTarget(path=data_path))
    return targets


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def validate_receipt(root: Path, receipt_rel: str) -> list[str]:
    failures: list[str] = []
    receipt_path = root / receipt_rel
    if not receipt_path.exists():
        return [f"[{receipt_rel}] receipt file does not exist"]

    try:
        receipt = load_json(receipt_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"[{receipt_rel}] receipt load failed: {exc}"]
    if not isinstance(receipt, dict):
        return [f"[{receipt_rel}] receipt must be a JSON object"]

    bundle = receipt.get("artifactBundle")
    if not isinstance(bundle, dict):
        return [f"[{receipt_rel}] artifactBundle must be an object"]

    bundle_rel = bundle.get("path")
    if not isinstance(bundle_rel, str) or not bundle_rel:
        return [f"[{receipt_rel}] artifactBundle.path must be a non-empty string"]

    bundle_path = root / bundle_rel
    if not bundle_path.exists():
        failures.append(f"[{receipt_rel}] bundle path does not exist: {bundle_rel}")
        return failures
    if not bundle_path.is_dir():
        failures.append(f"[{receipt_rel}] bundle path is not a directory: {bundle_rel}")
        return failures

    manifest = bundle.get("manifest")
    if not isinstance(manifest, list) or not manifest:
        return [f"[{receipt_rel}] artifactBundle.manifest must be a non-empty array"]

    for index, entry in enumerate(manifest):
        label = f"[{receipt_rel}] manifest[{index}]"
        if not isinstance(entry, dict):
            failures.append(f"{label} must be an object")
            continue
        entry_rel = entry.get("path")
        if not isinstance(entry_rel, str) or not entry_rel:
            failures.append(f"{label}.path must be a non-empty string")
            continue
        if entry_rel.startswith("/"):
            failures.append(f"{label}.path must be bundle-relative (no leading slash): {entry_rel}")
            continue
        resolved = (bundle_path / entry_rel).resolve()
        try:
            resolved.relative_to(bundle_path.resolve())
        except ValueError:
            failures.append(f"{label}.path escapes the bundle directory: {entry_rel}")
            continue
        if not resolved.exists():
            failures.append(f"{label} missing file: {bundle_rel}/{entry_rel}")
            continue
        declared_size = entry.get("sizeBytes")
        if not isinstance(declared_size, int) or declared_size < 0:
            failures.append(f"{label}.sizeBytes must be a non-negative integer")
            continue
        actual_size = resolved.stat().st_size
        if actual_size != declared_size:
            failures.append(
                f"{label} size mismatch for {entry_rel}: declared {declared_size}, actual {actual_size}"
            )
        declared_sha = entry.get("sha256")
        if not isinstance(declared_sha, str) or len(declared_sha) != 64:
            failures.append(f"{label}.sha256 must be a 64-character hex string")
            continue
        actual_sha = sha256_of(resolved)
        if actual_sha != declared_sha:
            failures.append(
                f"{label} sha256 mismatch for {entry_rel}: declared {declared_sha}, actual {actual_sha}"
            )
    return failures


def main() -> int:
    args = parse_args()
    try:
        root = detect_repo_root(args.root)
    except (ValueError, OSError) as exc:
        print(f"FAIL: {exc}")
        return 1

    receipt_rels: list[str] = list(args.receipt)
    if not receipt_rels:
        try:
            targets = load_registered_receipts(root)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"FAIL: {exc}")
            return 1
        receipt_rels = [t.path for t in targets]

    if not receipt_rels:
        print("PASS: no pilot-evidence receipts registered")
        return 0

    failures: list[str] = []
    for receipt_rel in receipt_rels:
        failures.extend(validate_receipt(root, receipt_rel))

    if failures:
        print("FAIL: pilot-evidence gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(f"PASS ({len(receipt_rels)} receipt{'s' if len(receipt_rels) != 1 else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
