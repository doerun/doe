#!/usr/bin/env python3
"""Generate machine-readable workload overlap maps from comparable backend workload sets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FULL_FRONTIER = {
    "metal": "bench/workloads.apple.metal.extended.json",
    "vulkan": "bench/workloads.amd.vulkan.extended.strict.json",
    "d3d12": "bench/workloads.local.d3d12.extended.json",
}
DEFAULT_METAL_RELEASE_LENS = {
    "metal": "bench/workloads.apple.metal.smoke.json",
    "vulkan": "bench/workloads.amd.vulkan.extended.strict.json",
    "d3d12": "bench/workloads.local.d3d12.extended.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "bench" / "workload-overlap-map.json"),
        help="Output overlap artifact path.",
    )
    parser.add_argument(
        "--full-frontier-metal",
        default=str(REPO_ROOT / DEFAULT_FULL_FRONTIER["metal"]),
        help="Comparable workload source for full frontier Metal.",
    )
    parser.add_argument(
        "--full-frontier-vulkan",
        default=str(REPO_ROOT / DEFAULT_FULL_FRONTIER["vulkan"]),
        help="Comparable workload source for full frontier Vulkan.",
    )
    parser.add_argument(
        "--full-frontier-d3d12",
        default=str(REPO_ROOT / DEFAULT_FULL_FRONTIER["d3d12"]),
        help="Comparable workload source for full frontier D3D12.",
    )
    parser.add_argument(
        "--release-lens-metal",
        default=str(REPO_ROOT / DEFAULT_METAL_RELEASE_LENS["metal"]),
        help="Comparable workload source for Metal release lens.",
    )
    parser.add_argument(
        "--release-lens-vulkan",
        default=str(REPO_ROOT / DEFAULT_METAL_RELEASE_LENS["vulkan"]),
        help="Comparable workload source for Vulkan release lens.",
    )
    parser.add_argument(
        "--release-lens-d3d12",
        default=str(REPO_ROOT / DEFAULT_METAL_RELEASE_LENS["d3d12"]),
        help="Comparable workload source for D3D12 release lens.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Fail if output differs from existing artifact.",
    )
    return parser.parse_args()


def normalize_path(value: str) -> str:
    candidate = Path(value)
    try:
        return str(candidate.relative_to(REPO_ROOT))
    except ValueError:
        return str(candidate)


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected object")
    return payload


def load_comparable_ids(path: str | Path) -> set[str]:
    payload = load_json(path)
    workloads = payload.get("workloads")
    if not isinstance(workloads, list):
        raise ValueError(f"{path}: expected workloads array")
    workload_ids: set[str] = set()
    for row in workloads:
        if not isinstance(row, dict):
            continue
        if not row.get("comparable", False):
            continue
        workload_id = row.get("id")
        if isinstance(workload_id, str):
            workload_ids.add(workload_id)
    return workload_ids


def build_overlap_map(
    full_frontier_sources: dict[str, str],
    release_lens_sources: dict[str, str],
) -> dict[str, Any]:
    full_frontier = build_overlap_section(
        load_comparable_ids(full_frontier_sources["metal"]),
        load_comparable_ids(full_frontier_sources["vulkan"]),
        load_comparable_ids(full_frontier_sources["d3d12"]),
    )
    metal_release_lens = build_overlap_section(
        load_comparable_ids(release_lens_sources["metal"]),
        load_comparable_ids(release_lens_sources["vulkan"]),
        load_comparable_ids(release_lens_sources["d3d12"]),
    )
    return {
        "schemaVersion": 1,
        "generatedBy": "bench/generate_workload_overlap_map.py",
        "assumptions": {
            "criterion": "comparable == true",
            "fullComparableFrontier": {
                "metal": normalize_path(full_frontier_sources["metal"]),
                "vulkan": normalize_path(full_frontier_sources["vulkan"]),
                "d3d12": normalize_path(full_frontier_sources["d3d12"]),
            },
            "metalReleaseLens": {
                "metal": normalize_path(release_lens_sources["metal"]),
                "vulkan": normalize_path(release_lens_sources["vulkan"]),
                "d3d12": normalize_path(release_lens_sources["d3d12"]),
            },
        },
        "fullComparableFrontier": {
            "source": {
                "metal": normalize_path(full_frontier_sources["metal"]),
                "vulkan": normalize_path(full_frontier_sources["vulkan"]),
                "d3d12": normalize_path(full_frontier_sources["d3d12"]),
            },
            "coverage": full_frontier["coverage"],
            "counts": full_frontier["counts"],
        },
        "metalReleaseLens": {
            "source": {
                "metal": normalize_path(release_lens_sources["metal"]),
                "vulkan": normalize_path(release_lens_sources["vulkan"]),
                "d3d12": normalize_path(release_lens_sources["d3d12"]),
            },
            "reason": "Derived from current Metal release workload source plus Vulkan/D3D12 strict comparable sources.",
            "coverage": metal_release_lens["coverage"],
            "counts": metal_release_lens["counts"],
        },
    }


def sorted_list(values: set[str]) -> list[str]:
    return sorted(values)


def build_overlap_section(metal_ids: set[str], vulkan_ids: set[str], d3d12_ids: set[str]) -> dict[str, Any]:
    across_all_three = metal_ids & vulkan_ids & d3d12_ids
    only_vulkan = vulkan_ids - metal_ids - d3d12_ids
    only_metal = metal_ids - vulkan_ids - d3d12_ids
    only_d3d12 = d3d12_ids - metal_ids - vulkan_ids
    vulkan_and_metal_only = (vulkan_ids & metal_ids) - d3d12_ids
    metal_and_d3d12_only = (metal_ids & d3d12_ids) - vulkan_ids
    vulkan_and_d3d12_only = (vulkan_ids & d3d12_ids) - metal_ids
    return {
        "coverage": {
            "across_all_three_backends": sorted_list(across_all_three),
            "only_vulkan": sorted_list(only_vulkan),
            "only_metal": sorted_list(only_metal),
            "only_d3d12": sorted_list(only_d3d12),
            "vulkan_and_metal_only": sorted_list(vulkan_and_metal_only),
            "metal_and_d3d12_only": sorted_list(metal_and_d3d12_only),
            "vulkan_and_d3d12_only": sorted_list(vulkan_and_d3d12_only),
        },
        "counts": {
            "across_all_three_backends": len(across_all_three),
            "only_vulkan": len(only_vulkan),
            "only_metal": len(only_metal),
            "only_d3d12": len(only_d3d12),
            "vulkan_and_metal_only": len(vulkan_and_metal_only),
            "metal_and_d3d12_only": len(metal_and_d3d12_only),
            "vulkan_and_d3d12_only": len(vulkan_and_d3d12_only),
            "distinctComparable": {
                "metal": len(metal_ids),
                "vulkan": len(vulkan_ids),
                "d3d12": len(d3d12_ids),
            },
        },
    }


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


def main() -> None:
    args = parse_args()
    full_frontier_sources = {
        "metal": str(args.full_frontier_metal),
        "vulkan": str(args.full_frontier_vulkan),
        "d3d12": str(args.full_frontier_d3d12),
    }
    release_lens_sources = {
        "metal": str(args.release_lens_metal),
        "vulkan": str(args.release_lens_vulkan),
        "d3d12": str(args.release_lens_d3d12),
    }
    artifact = build_overlap_map(full_frontier_sources, release_lens_sources)

    output_path = Path(args.output)
    if args.verify:
        existing = load_json(output_path) if output_path.exists() else None
        if existing is None or existing != artifact:
            raise SystemExit("workload-overlap-map artifact mismatch; run generator without --verify to update.")
    else:
        write_json(output_path, artifact)


if __name__ == "__main__":
    main()
