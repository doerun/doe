#!/usr/bin/env python3
"""Generate backend workload contract files from a canonical catalog."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "bench" / "backend-workload-catalog.json"
CATALOG_SCHEMA_PATH = REPO_ROOT / "config" / "backend-workload-catalog.schema.json"

DEFAULT_LANE_OUTPUTS = OrderedDict(
    [
        ("generic", {"outputPath": "bench/workloads.json"}),
        ("amd_vulkan_base", {"outputPath": "bench/workloads.amd.vulkan.json"}),
        ("amd_vulkan_extended", {"outputPath": "bench/workloads.amd.vulkan.extended.json"}),
        (
            "amd_vulkan_native_supported",
            {"outputPath": "bench/workloads.amd.vulkan.extended.native-supported.json"},
        ),
        (
            "amd_vulkan_doe_vs_doe",
            {"outputPath": "bench/workloads.amd.vulkan.extended.doe-vs-doe.json"},
        ),
        ("amd_vulkan_app_claim", {"outputPath": "bench/workloads.amd.vulkan.app.claim.json"}),
        ("local_vulkan_smoke", {"outputPath": "bench/workloads.local.vulkan.smoke.json"}),
        ("local_vulkan_extended", {"outputPath": "bench/workloads.local.vulkan.extended.json"}),
        (
            "local_vulkan_strict",
            {"outputPath": "bench/workloads.local.vulkan.extended.strict.json"},
        ),
        ("local_metal_smoke", {"outputPath": "bench/workloads.local.metal.smoke.json"}),
        ("local_metal_extended", {"outputPath": "bench/workloads.local.metal.extended.json"}),
        ("local_d3d12_smoke", {"outputPath": "bench/workloads.local.d3d12.smoke.json"}),
        ("local_d3d12_extended", {"outputPath": "bench/workloads.local.d3d12.extended.json"}),
    ]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        default=str(CATALOG_PATH),
        help="Canonical backend workload catalog path.",
    )
    parser.add_argument(
        "--bootstrap-from-existing",
        action="store_true",
        help="Create/update the catalog from the existing generated workload files.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify generated workload files match the catalog instead of writing.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2) + "\n"


def write_json(path: Path, payload: Any) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json_text(payload)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == rendered:
            return False
    path.write_text(rendered, encoding="utf-8")
    return True


def validate_catalog(catalog: dict[str, Any]) -> None:
    schema = load_json(CATALOG_SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(catalog),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) if first.absolute_path else "<root>"
        raise ValueError(f"{CATALOG_SCHEMA_PATH}: {location}: {first.message}")


def bootstrap_catalog() -> dict[str, Any]:
    lane_outputs = OrderedDict(DEFAULT_LANE_OUTPUTS)
    lane_rows: dict[str, dict[str, dict[str, Any]]] = {}
    all_ids: set[str] = set()
    for lane_id, entry in lane_outputs.items():
        payload = load_json(REPO_ROOT / entry["outputPath"])
        rows = payload.get("workloads")
        if not isinstance(rows, list):
            raise ValueError(f"invalid workloads payload: {entry['outputPath']}")
        row_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            workload_id = row["id"]
            row_map[workload_id] = row
            all_ids.add(workload_id)
        lane_rows[lane_id] = row_map

    ordered_ids: list[str] = []
    seen_ids: set[str] = set()
    for lane_id in lane_outputs:
        for workload_id in lane_rows[lane_id]:
            if workload_id in seen_ids:
                continue
            seen_ids.add(workload_id)
            ordered_ids.append(workload_id)

    workloads = []
    for workload_id in ordered_ids:
        present_rows = [lane_rows[lane][workload_id] for lane in lane_outputs if workload_id in lane_rows[lane]]
        field_order = [key for key in present_rows[0].keys() if key != "id"]
        common_keys = set(present_rows[0].keys())
        for row in present_rows[1:]:
            common_keys &= set(row.keys())
        shared: dict[str, Any] = {}
        for key in field_order:
            if key not in common_keys:
                continue
            first_value = present_rows[0][key]
            if all(row[key] == first_value for row in present_rows[1:]):
                shared[key] = first_value
        if "id" in shared:
            shared.pop("id")

        lane_overrides: dict[str, dict[str, Any]] = OrderedDict()
        for lane_id in lane_outputs:
            row = lane_rows[lane_id].get(workload_id)
            if row is None:
                continue
            override = OrderedDict()
            for key in field_order:
                if key not in row:
                    continue
                value = row[key]
                if key == "id":
                    continue
                if shared.get(key) == value:
                    continue
                override[key] = value
            lane_overrides[lane_id] = override

        workloads.append(
            OrderedDict(
                [
                    ("id", workload_id),
                    ("fieldOrder", field_order),
                    ("shared", OrderedDict(shared.items())),
                    ("lanes", lane_overrides),
                ]
            )
        )

    catalog = OrderedDict(
        [
            ("schemaVersion", 1),
            ("laneOutputs", lane_outputs),
            ("workloads", workloads),
        ]
    )
    validate_catalog(catalog)
    return catalog


def materialize_lane(catalog: dict[str, Any], lane_id: str) -> dict[str, Any]:
    workloads = []
    for item in catalog["workloads"]:
        lane_override = item["lanes"].get(lane_id)
        if lane_override is None:
            continue
        row = OrderedDict()
        row["id"] = item["id"]
        for key in item.get("fieldOrder", []):
            if key in lane_override:
                row[key] = lane_override[key]
            elif key in item["shared"]:
                row[key] = item["shared"][key]
        for key, value in item["shared"].items():
            if key not in row:
                row[key] = value
        for key, value in lane_override.items():
            if key not in row:
                row[key] = value
        workloads.append(row)
    return OrderedDict(
        [
            ("schemaVersion", 1),
            ("workloads", workloads),
        ]
    )


def verify_lane(path: Path, expected: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    current = load_json(path)
    return current == expected


def generate_from_catalog(catalog: dict[str, Any], verify_only: bool) -> None:
    validate_catalog(catalog)
    mismatches: list[str] = []
    for lane_id, lane_entry in catalog["laneOutputs"].items():
        payload = materialize_lane(catalog, lane_id)
        output_path = REPO_ROOT / lane_entry["outputPath"]
        if verify_only:
            if not verify_lane(output_path, payload):
                mismatches.append(str(output_path))
        else:
            write_json(output_path, payload)
    if mismatches:
        raise SystemExit("generated workload files diverged:\n" + "\n".join(mismatches))


def main() -> None:
    args = parse_args()
    catalog_path = Path(args.catalog)
    if args.bootstrap_from_existing:
        catalog = bootstrap_catalog()
        write_json(catalog_path, catalog)
    else:
        catalog = load_json(catalog_path)
    generate_from_catalog(catalog, verify_only=args.verify)


if __name__ == "__main__":
    main()
