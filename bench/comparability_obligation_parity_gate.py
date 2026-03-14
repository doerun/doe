#!/usr/bin/env python3
"""Comparability obligation parity gate across Lean IDs and Python fixture evaluation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from compare_dawn_vs_doe_modules import comparability as comparability_mod


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="",
        help="Repository root. Auto-detected when omitted.",
    )
    parser.add_argument(
        "--fixtures",
        default="bench/comparability_obligation_fixtures.json",
        help="Comparability fixture file path.",
    )
    parser.add_argument(
        "--lean-ids-source",
        default="lean/Fawn/Generated/ComparabilityContract.lean",
        help="Lean source file containing ComparabilityObligationId constructors.",
    )
    return parser.parse_args()


def detect_repo_root(explicit_root: str) -> Path:
    if explicit_root:
        root = Path(explicit_root)
        if not root.exists():
            raise ValueError(f"invalid --root path: {root}")
        return root.resolve()

    cwd = Path.cwd()
    direct_root = cwd
    nested_root = cwd / "fawn"

    if (direct_root / "config").is_dir() and (direct_root / "bench").is_dir():
        return direct_root.resolve()
    if (nested_root / "config").is_dir() and (nested_root / "bench").is_dir():
        return nested_root.resolve()

    raise ValueError(
        "unable to auto-detect repository root; pass --root with a path containing config/ and bench/"
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def camel_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def parse_lean_obligation_ids(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    in_block = False
    ids: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not in_block:
            if stripped == "inductive ComparabilityObligationId where":
                in_block = True
            continue

        if stripped.startswith("deriving "):
            break
        if not stripped:
            continue
        if not stripped.startswith("| "):
            continue
        token = stripped[2:].split()[0].strip()
        if not token:
            continue
        ids.append(camel_to_snake(token))
    return ids


def validate_fixture_schema(payload: Any, *, path: Path) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return [f"{path}: expected object"]
    if payload.get("schemaVersion") != 1:
        failures.append(f"{path}: schemaVersion must be 1")
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        failures.append(f"{path}: fixtures must be a non-empty list")
        return failures
    fixture_ids: set[str] = set()
    for index, fixture in enumerate(fixtures):
        label = f"{path}: fixtures[{index}]"
        if not isinstance(fixture, dict):
            failures.append(f"{label}: expected object")
            continue
        fixture_id = fixture.get("id")
        if not isinstance(fixture_id, str) or not fixture_id:
            failures.append(f"{label}.id: expected non-empty string")
        elif fixture_id in fixture_ids:
            failures.append(f"{label}.id: duplicate fixture id {fixture_id}")
        else:
            fixture_ids.add(fixture_id)
        if not isinstance(fixture.get("facts"), dict):
            failures.append(f"{label}.facts: expected object")
        if not isinstance(fixture.get("expectedComparable"), bool):
            failures.append(f"{label}.expectedComparable: expected bool")
        expected_blocking = fixture.get("expectedBlockingFailedObligations")
        if not isinstance(expected_blocking, list):
            failures.append(f"{label}.expectedBlockingFailedObligations: expected list")
        elif any((not isinstance(item, str) or not item) for item in expected_blocking):
            failures.append(
                f"{label}.expectedBlockingFailedObligations: expected non-empty string entries"
            )
    return failures


def main() -> int:
    args = parse_args()
    root = detect_repo_root(args.root)

    fixture_path = root / args.fixtures
    lean_source_path = root / args.lean_ids_source
    if not fixture_path.exists():
        print(f"FAIL: missing fixture file: {fixture_path}")
        return 1
    if not lean_source_path.exists():
        print(f"FAIL: missing Lean source file: {lean_source_path}")
        return 1

    fixture_payload = load_json(fixture_path)
    schema_failures = validate_fixture_schema(fixture_payload, path=fixture_path)
    if schema_failures:
        print("FAIL: fixture schema validation")
        for failure in schema_failures:
            print(f"  {failure}")
        return 1

    fixtures = fixture_payload["fixtures"]
    canonical_ids = list(comparability_mod.CANONICAL_COMPARABILITY_OBLIGATION_IDS)
    lean_ids = parse_lean_obligation_ids(lean_source_path)

    failures: list[str] = []
    if lean_ids != canonical_ids:
        failures.append(
            "Lean/Python obligation ID mismatch between "
            f"{lean_source_path} and config/comparability-obligations.json"
        )

    for fixture in fixtures:
        fixture_id = str(fixture.get("id", "unknown"))
        facts = fixture.get("facts")
        expected_comparable = fixture.get("expectedComparable")
        expected_blocking = fixture.get("expectedBlockingFailedObligations")
        if not isinstance(facts, dict):
            failures.append(f"{fixture_id}: facts must be object")
            continue
        if not isinstance(expected_comparable, bool):
            failures.append(f"{fixture_id}: expectedComparable must be bool")
            continue
        if not isinstance(expected_blocking, list):
            failures.append(f"{fixture_id}: expectedBlockingFailedObligations must be list")
            continue

        try:
            evaluation = comparability_mod.evaluate_comparability_from_facts(facts)
        except ValueError as exc:
            failures.append(f"{fixture_id}: failed to evaluate comparability facts: {exc}")
            continue

        schema_version = evaluation.get("obligationSchemaVersion")
        if schema_version != comparability_mod.OBLIGATION_SCHEMA_VERSION:
            failures.append(
                f"{fixture_id}: obligationSchemaVersion mismatch "
                f"(expected {comparability_mod.OBLIGATION_SCHEMA_VERSION}, got {schema_version!r})"
            )

        obligations = evaluation.get("obligations")
        if not isinstance(obligations, list):
            failures.append(f"{fixture_id}: obligations must be list")
            continue
        generated_ids = [str(item.get("id", "")) for item in obligations if isinstance(item, dict)]
        if generated_ids != canonical_ids:
            failures.append(f"{fixture_id}: generated obligation ID order does not match canonical contract")

        blocking_failed = evaluation.get("blockingFailedObligations")
        if not isinstance(blocking_failed, list):
            failures.append(f"{fixture_id}: blockingFailedObligations must be list")
        elif blocking_failed != expected_blocking:
            failures.append(
                f"{fixture_id}: blockingFailedObligations mismatch "
                f"(expected {expected_blocking}, got {blocking_failed})"
            )

        comparable = evaluation.get("comparable")
        if comparable != expected_comparable:
            failures.append(
                f"{fixture_id}: comparable mismatch "
                f"(expected {expected_comparable}, got {comparable})"
            )

    if failures:
        print("FAIL: comparability parity gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(
        "PASS: comparability parity gate "
        f"(fixtures={len(fixtures)}, obligations={len(canonical_ids)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
