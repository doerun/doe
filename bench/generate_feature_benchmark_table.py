#!/usr/bin/env python3
"""Generate Dawn-vs-Fawn feature and benchmark coverage markdown table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CAPABILITY_TO_WORKLOADS: dict[str, list[str]] = {
    "p0_buffer_destroy_and_barrier_clear": ["p0_resource_lifecycle_contract"],
    "p0_compute_indirect_async_timestamp": ["p0_compute_indirect_timestamp_contract"],
    "p0_query_set_introspection_lifecycle": [
        "p0_compute_indirect_timestamp_contract",
        "p0_render_multidraw_contract",
        "p0_render_multidraw_indexed_contract",
    ],
    "p0_render_occlusion_multidraw_timestamp": [
        "p0_render_multidraw_contract",
        "p0_render_multidraw_indexed_contract",
    ],
    "p0_device_destroy_lifecycle": ["p0_resource_lifecycle_contract"],
    "p0_render_pixel_local_storage_barrier": [
        "p0_render_pixel_local_storage_barrier_contract",
        "p0_render_pixel_local_storage_barrier_macro_500",
    ],
    "p1_capability_introspection_surface": [
        "p1_capability_introspection_contract",
        "p1_capability_introspection_macro_500",
    ],
    "p1_resource_table_immediates_surface": [
        "p1_resource_table_immediates_contract",
        "p1_resource_table_immediates_macro_500",
    ],
    "p2_lifecycle_addref_surface": [
        "p2_lifecycle_refcount_contract",
        "p2_lifecycle_refcount_macro_200",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--coverage",
        default="config/webgpu-spec-coverage.json",
        help="Coverage config JSON path.",
    )
    parser.add_argument(
        "--workloads",
        default="bench/workloads.amd.vulkan.extended.json",
        help="Workloads config JSON path.",
    )
    parser.add_argument(
        "--dawn-map",
        default="bench/dawn_workload_map.amd.extended.json",
        help="Dawn workload map JSON path.",
    )
    parser.add_argument(
        "--out",
        default="bench/out/dawn-vs-fawn-feature-benchmark-coverage.md",
        help="Output markdown file path.",
    )
    return parser.parse_args()


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _compact(text: str, max_len: int = 110) -> str:
    value = " ".join(text.split())
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def main() -> int:
    args = parse_args()
    coverage = _load_json(args.coverage)
    workloads = _load_json(args.workloads)
    dawn_map = _load_json(args.dawn_map).get("filters", {})

    known_workloads = {entry["id"] for entry in workloads.get("workloads", [])}
    rows: list[str] = []
    implemented = 0
    partial = 0
    planned = 0

    for item in coverage.get("coverage", []):
        status = item.get("status", "unknown")
        if status == "implemented":
            implemented += 1
        elif status == "partial":
            partial += 1
        else:
            planned += 1
        capability_id = item.get("capabilityId", "")
        workload_ids = [
            workload
            for workload in CAPABILITY_TO_WORKLOADS.get(capability_id, [])
            if workload in known_workloads
        ]
        if not workload_ids:
            workload_field = "n/a"
            dawn_field = "n/a"
        else:
            workload_field = ", ".join(f"`{workload}`" for workload in workload_ids)
            dawn_filters = []
            for workload in workload_ids:
                mapped = dawn_map.get(workload)
                if mapped and mapped not in dawn_filters:
                    dawn_filters.append(mapped)
            dawn_field = "<br>".join(f"`{flt}`" for flt in dawn_filters) if dawn_filters else "n/a"
        rows.append(
            "| `{capability}` | `{status}` | `{priority}` | {contract} | {workloads} | {dawn} |".format(
                capability=capability_id,
                status=status,
                priority=item.get("priority", ""),
                contract=_compact(item.get("contract", "")),
                workloads=workload_field,
                dawn=dawn_field,
            )
        )

    output = [
        "# Dawn vs Fawn Feature + Benchmark Coverage",
        "",
        f"- generatedFrom: `{args.coverage}` + `{args.workloads}` + `{args.dawn_map}`",
        f"- totals: implemented={implemented}, partial={partial}, planned={planned}",
        "",
        "| Capability | Status | Priority | Fawn Contract | Benchmark Workloads | Dawn Baseline Filter(s) |",
        "|---|---|---|---|---|---|",
    ]
    output.extend(rows)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(output) + "\n")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
