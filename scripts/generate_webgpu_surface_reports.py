#!/usr/bin/env python3
"""Generate surface-oriented WebGPU reports from canonical axis-based ledgers."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


COMPUTE_CAPABILITY_DOMAINS = {
    "compute",
    "copy",
    "resource",
    "pipeline",
    "queue",
    "query",
    "capability",
    "resource-table",
    "lifecycle",
    "device",
}

HEADLESS_EXCLUDED_DOMAINS = {"surface"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", default="config/webgpu-command-coverage-core.json")
    parser.add_argument("--full", default="config/webgpu-command-coverage-full.json")
    parser.add_argument("--inventory", default="config/webgpu-capability-inventory.json")
    parser.add_argument("--chromium", default="config/webgpu-integration-chromium.json")
    parser.add_argument("--spec-index", default="config/webgpu-spec-index.jsonl")
    parser.add_argument("--out-dir", default="config/generated")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def inventory_entries_for_surface(surface_id: str, inventory: dict[str, Any]) -> list[dict[str, Any]]:
    entries = inventory.get("coverage", [])
    if surface_id == "doe-compute":
        return [entry for entry in entries if entry.get("domain") in COMPUTE_CAPABILITY_DOMAINS]
    if surface_id == "doe-headless":
        return [entry for entry in entries if entry.get("domain") not in HEADLESS_EXCLUDED_DOMAINS]
    return list(entries)


def summarize_status(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter = Counter(item.get(key, "unknown") for item in items)
    return dict(sorted(counter.items()))


def summarize_spec_index(rows: list[dict[str, Any]], backend: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        if row.get("kind") == "header":
            continue
        cell = row.get(backend, {})
        if isinstance(cell, dict):
            counter[cell.get("impl", "unreviewed")] += 1
        else:
            counter["unreviewed"] += 1
    return dict(sorted(counter.items()))


def build_compute_report(
    core: dict[str, Any],
    inventory: dict[str, Any],
    spec_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    relevant_inventory = inventory_entries_for_surface("doe-compute", inventory)
    return {
        "schemaVersion": 1,
        "reportKind": "webgpu-surface-report",
        "surfaceId": "doe-compute",
        "generatedAt": datetime.now(UTC).isoformat(),
        "derivedFrom": {
            "commandCoverage": "config/webgpu-command-coverage-core.json",
            "capabilityInventory": "config/webgpu-capability-inventory.json",
            "specIndex": "config/webgpu-spec-index.jsonl",
        },
        "notes": [
            "Surface reports are generated views. Canonical source-of-truth remains axis-based.",
            "Compute view is based on the core command surface plus compute-relevant capability inventory domains.",
        ],
        "commandCoverage": {
            "surfaceId": core.get("surfaceId"),
            "commandCount": core.get("commandCount"),
            "statusSummary": summarize_status(core.get("coverage", []), "status"),
            "commands": core.get("coverage", []),
        },
        "capabilityInventory": {
            "entryCount": len(relevant_inventory),
            "statusSummary": summarize_status(relevant_inventory, "status"),
            "entries": relevant_inventory,
        },
        "specIndexSummary": {
            "note": "The spec index is backend-oriented rather than tier-oriented; these are global implementation counts for native backends.",
            "metal": summarize_spec_index(spec_rows, "metal"),
            "vulkan": summarize_spec_index(spec_rows, "vulkan"),
            "d3d12": summarize_spec_index(spec_rows, "d3d12"),
        },
    }


def build_headless_report(
    full: dict[str, Any],
    inventory: dict[str, Any],
    spec_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    relevant_inventory = inventory_entries_for_surface("doe-headless", inventory)
    full_only = [
        entry for entry in full.get("fullOnlyCoverage", [])
        if entry.get("domain") != "surface"
    ]
    total_count = len(full.get("coreCoverage", [])) + len(full_only)
    return {
        "schemaVersion": 1,
        "reportKind": "webgpu-surface-report",
        "surfaceId": "doe-headless",
        "generatedAt": datetime.now(UTC).isoformat(),
        "derivedFrom": {
            "commandCoverage": "config/webgpu-command-coverage-full.json",
            "capabilityInventory": "config/webgpu-capability-inventory.json",
            "specIndex": "config/webgpu-spec-index.jsonl",
        },
        "notes": [
            "Headless view is derived from the full command ledger by excluding surface-presentation commands.",
            "Canonical full command coverage remains broader than the current headless-only packaging split.",
        ],
        "commandCoverage": {
            "sourceSurfaceId": full.get("surfaceId"),
            "derivedCommandCount": total_count,
            "statusSummary": summarize_status(full.get("coreCoverage", []) + full_only, "status"),
            "coreCommands": full.get("coreCoverage", []),
            "headlessOnlyCommands": full_only,
        },
        "capabilityInventory": {
            "entryCount": len(relevant_inventory),
            "statusSummary": summarize_status(relevant_inventory, "status"),
            "entries": relevant_inventory,
        },
        "specIndexSummary": {
            "note": "The spec index is backend-oriented rather than tier-oriented; these are global implementation counts for native backends.",
            "metal": summarize_spec_index(spec_rows, "metal"),
            "vulkan": summarize_spec_index(spec_rows, "vulkan"),
            "d3d12": summarize_spec_index(spec_rows, "d3d12"),
        },
    }


def build_chromium_report(
    full: dict[str, Any],
    inventory: dict[str, Any],
    chromium: dict[str, Any],
    spec_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    relevant_inventory = inventory_entries_for_surface("doe-headless", inventory)
    return {
        "schemaVersion": 1,
        "reportKind": "webgpu-surface-report",
        "surfaceId": "doe-chromium",
        "generatedAt": datetime.now(UTC).isoformat(),
        "derivedFrom": {
            "commandCoverage": "config/webgpu-command-coverage-full.json",
            "capabilityInventory": "config/webgpu-capability-inventory.json",
            "integrationOverlay": "config/webgpu-integration-chromium.json",
            "specIndex": "config/webgpu-spec-index.jsonl",
        },
        "notes": [
            "Chromium view is a browser integration overlay on top of Doe's native command and capability surfaces.",
            "Browser-specific constraints come from the wire transport seam and browser-owned media/image paths.",
        ],
        "commandCoverage": {
            "sourceSurfaceId": full.get("surfaceId"),
            "totalCommandCount": full.get("totalCommandCount"),
            "statusSummary": summarize_status(
                full.get("coreCoverage", []) + full.get("fullOnlyCoverage", []),
                "status",
            ),
        },
        "capabilityInventory": {
            "entryCount": len(relevant_inventory),
            "statusSummary": summarize_status(relevant_inventory, "status"),
        },
        "integrationOverlay": chromium,
        "specIndexSummary": {
            "note": "Browser cells come from the canonical spec index; the Chromium integration overlay records additional wire/browser-specific constraints.",
            "browser": summarize_spec_index(spec_rows, "browser"),
        },
    }


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    core = load_json(root / args.core)
    full = load_json(root / args.full)
    inventory = load_json(root / args.inventory)
    chromium = load_json(root / args.chromium)
    spec_rows = load_jsonl(root / args.spec_index)

    reports = {
        "webgpu-surface-compute.json": build_compute_report(core, inventory, spec_rows),
        "webgpu-surface-headless.json": build_headless_report(full, inventory, spec_rows),
        "webgpu-surface-chromium.json": build_chromium_report(full, inventory, chromium, spec_rows),
    }

    for name, payload in reports.items():
        (out_dir / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
