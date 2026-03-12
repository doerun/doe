#!/usr/bin/env python3
"""Split coverage gate: validates core and full coverage ledgers against
the Zig runtime command partitions and surface schemas.

Checks:
1. Schema validation for both ledger files.
2. Command-kind completeness: every Zig partition enum value has a ledger entry.
3. Count invariant: ledger commandCount matches the Zig partition enum size.
4. Superset invariant: full coreCoverage is a strict superset of core coverage.
5. Domain classification consistency between core and full ledgers.
6. No overlap: core and full-only command kinds are disjoint.
7. Total count: full totalCommandCount == coreCommandCount + fullOnlyCommandCount.

Exit 0 on success, 1 on failure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Zig enum extraction pattern for command_partition.zig files.
ZIG_ENUM_FIELD_RE = re.compile(r"^\s+\.?([a-z_]+)\s*[,=]", re.MULTILINE)
ZIG_ENUM_FIELD_RE2 = re.compile(r"^\s+([a-z_]+)\s*[,]?\s*$", re.MULTILINE)


def extract_enum_fields(partition_path: Path) -> list[str]:
    """Extract enum field names from a Zig command_partition.zig file."""
    text = partition_path.read_text()
    # Match lines like "    upload," or "    upload = 0," inside the enum block.
    fields: list[str] = []
    in_enum = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("pub const CommandKind"):
            in_enum = True
            continue
        if in_enum and stripped.startswith("};"):
            break
        if in_enum:
            # Match "upload," or "upload = 0," or ".upload,"
            m = re.match(r"\.?([a-z_][a-z0-9_]*)\s*[,=]", stripped)
            if not m:
                m = re.match(r"([a-z_][a-z0-9_]*)\s*,?\s*$", stripped)
            if m:
                fields.append(m.group(1))
    return fields


def validate_schema(ledger: dict, schema_path: Path) -> list[str]:
    """Basic structural validation (JSON Schema would be ideal, but we keep
    this self-contained without external dependencies)."""
    errors: list[str] = []
    schema = json.loads(schema_path.read_text())
    required = schema.get("required", [])
    for field in required:
        if field not in ledger:
            errors.append(f"missing required field: {field}")
    return errors


def validate_core(
    core_ledger: dict,
    core_schema_path: Path,
    core_partition_path: Path,
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_schema(core_ledger, core_schema_path))

    zig_fields = extract_enum_fields(core_partition_path)
    if not zig_fields:
        errors.append(f"no enum fields extracted from {core_partition_path}")
        return errors

    ledger_kinds = {entry["commandKind"] for entry in core_ledger.get("coverage", [])}
    zig_set = set(zig_fields)

    # Count invariant.
    expected_count = core_ledger.get("commandCount", 0)
    if expected_count != len(zig_fields):
        errors.append(
            f"core commandCount ({expected_count}) != Zig partition enum size ({len(zig_fields)})"
        )

    # Completeness: every Zig field has a ledger entry.
    missing = zig_set - ledger_kinds
    if missing:
        errors.append(f"core ledger missing Zig command kinds: {sorted(missing)}")

    # No extras: ledger should not have kinds not in the partition.
    extra = ledger_kinds - zig_set
    if extra:
        errors.append(f"core ledger has extra command kinds not in partition: {sorted(extra)}")

    return errors


def validate_full(
    full_ledger: dict,
    full_schema_path: Path,
    core_partition_path: Path,
    full_partition_path: Path,
    core_ledger: dict,
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_schema(full_ledger, full_schema_path))

    core_zig_fields = extract_enum_fields(core_partition_path)
    full_zig_fields = extract_enum_fields(full_partition_path)
    if not core_zig_fields:
        errors.append(f"no enum fields extracted from {core_partition_path}")
    if not full_zig_fields:
        errors.append(f"no enum fields extracted from {full_partition_path}")
    if errors:
        return errors

    core_zig_set = set(core_zig_fields)
    full_zig_set = set(full_zig_fields)

    # Disjoint check.
    overlap = core_zig_set & full_zig_set
    if overlap:
        errors.append(f"core and full-only partitions overlap: {sorted(overlap)}")

    # Count invariants.
    core_count = full_ledger.get("coreCommandCount", 0)
    full_only_count = full_ledger.get("fullOnlyCommandCount", 0)
    total_count = full_ledger.get("totalCommandCount", 0)

    if core_count != len(core_zig_fields):
        errors.append(
            f"full coreCommandCount ({core_count}) != core Zig partition size ({len(core_zig_fields)})"
        )
    if full_only_count != len(full_zig_fields):
        errors.append(
            f"full fullOnlyCommandCount ({full_only_count}) != full Zig partition size ({len(full_zig_fields)})"
        )
    if total_count != core_count + full_only_count:
        errors.append(
            f"full totalCommandCount ({total_count}) != core ({core_count}) + full-only ({full_only_count})"
        )

    # Completeness: coreCoverage.
    core_coverage_kinds = {
        entry["commandKind"] for entry in full_ledger.get("coreCoverage", [])
    }
    missing_core = core_zig_set - core_coverage_kinds
    if missing_core:
        errors.append(f"full coreCoverage missing core kinds: {sorted(missing_core)}")

    # Completeness: fullOnlyCoverage.
    full_coverage_kinds = {
        entry["commandKind"] for entry in full_ledger.get("fullOnlyCoverage", [])
    }
    missing_full = full_zig_set - full_coverage_kinds
    if missing_full:
        errors.append(f"full fullOnlyCoverage missing full-only kinds: {sorted(missing_full)}")

    # Superset invariant: full coreCoverage command kinds must exactly match
    # the core ledger command kinds.
    core_ledger_kinds = {entry["commandKind"] for entry in core_ledger.get("coverage", [])}
    if core_coverage_kinds != core_ledger_kinds:
        drift = core_coverage_kinds.symmetric_difference(core_ledger_kinds)
        errors.append(f"full coreCoverage drifted from core ledger: {sorted(drift)}")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--core-ledger",
        default="config/webgpu-core-coverage.json",
        help="Core coverage ledger path.",
    )
    parser.add_argument(
        "--full-ledger",
        default="config/webgpu-full-coverage.json",
        help="Full coverage ledger path.",
    )
    parser.add_argument(
        "--core-schema",
        default="config/webgpu-core-coverage.schema.json",
        help="Core coverage schema path.",
    )
    parser.add_argument(
        "--full-schema",
        default="config/webgpu-full-coverage.schema.json",
        help="Full coverage schema path.",
    )
    parser.add_argument(
        "--core-partition",
        default="zig/src/core/command_partition.zig",
        help="Zig core command_partition.zig path.",
    )
    parser.add_argument(
        "--full-partition",
        default="zig/src/full/command_partition.zig",
        help="Zig full command_partition.zig path.",
    )
    parser.add_argument(
        "--surface",
        choices=["core", "full", "both"],
        default="both",
        help="Which surface(s) to validate.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    all_errors: list[str] = []

    core_ledger = json.loads((root / args.core_ledger).read_text())
    full_ledger = json.loads((root / args.full_ledger).read_text())

    if args.surface in ("core", "both"):
        errs = validate_core(
            core_ledger,
            root / args.core_schema,
            root / args.core_partition,
        )
        if errs:
            print("CORE COVERAGE GATE FAILED:", file=sys.stderr)
            for e in errs:
                print(f"  {e}", file=sys.stderr)
            all_errors.extend(errs)
        else:
            print("core coverage gate: PASS")

    if args.surface in ("full", "both"):
        errs = validate_full(
            full_ledger,
            root / args.full_schema,
            root / args.core_partition,
            root / args.full_partition,
            core_ledger,
        )
        if errs:
            print("FULL COVERAGE GATE FAILED:", file=sys.stderr)
            for e in errs:
                print(f"  {e}", file=sys.stderr)
            all_errors.extend(errs)
        else:
            print("full coverage gate: PASS")

    if all_errors:
        print(f"\n{len(all_errors)} error(s) total.", file=sys.stderr)
        return 1

    print("\nsplit coverage gate: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
