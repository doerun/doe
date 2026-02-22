#!/usr/bin/env python3
"""Generate Dawn-vs-Fawn feature and benchmark coverage markdown table."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CAPABILITY_TO_WORKLOADS: dict[str, list[str]] = {
    "queue_sync_mode": ["buffer_upload_64kb", "draw_indexed_render_proxy"],
    "render_draw_offsets": ["render_draw_throughput_proxy"],
    "render_draw_indexed": ["draw_indexed_render_proxy", "p0_render_multidraw_indexed_contract"],
    "render_core_api_surface": [
        "render_draw_throughput_proxy",
        "render_draw_state_bindings",
        "draw_indexed_render_proxy",
    ],
    "render_pass_state_bindings": [
        "render_draw_state_bindings",
        "render_draw_redundant_pipeline_bindings",
    ],
    "render_draw_encode_modes": [
        "render_draw_throughput_proxy",
        "render_bundle_dynamic_bindings",
    ],
    "textured_render_workload_contract": [
        "texture_sampling_raster_proxy",
        "texture_sampler_write_query_destroy_contract",
        "texture_sampler_write_query_destroy_contract_mip8",
    ],
    "render_bundle_execution": [
        "render_bundle_dynamic_bindings",
        "render_bundle_dynamic_pipeline_bindings",
    ],
    "surface_presentation": ["surface_presentation_contract"],
    "async_pipeline_diagnostics": ["async_pipeline_diagnostics_contract"],
    "render_pass_state_space": [
        "render_draw_state_bindings",
        "render_draw_redundant_pipeline_bindings",
        "draw_indexed_render_proxy",
    ],
    "timestamp_query_claimability": [
        "p0_compute_indirect_timestamp_contract",
        "p0_render_multidraw_contract",
    ],
    "texture_query_assertions": [
        "texture_sampler_write_query_destroy_contract",
        "texture_sampler_write_query_destroy_contract_mip8",
    ],
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


def _measure_dawn_header_api_surface_coverage() -> tuple[int, int, float]:
    header = Path("bench/vendor/dawn/third_party/webgpu-headers/src/webgpu.h")
    header_text = header.read_text(errors="ignore")
    header_symbols = set(re.findall(r"\b(wgpu[A-Za-z0-9_]+)\s*\(", header_text))
    zig_symbols: set[str] = set()
    for source in Path("zig/src").glob("*.zig"):
        text = source.read_text(errors="ignore")
        zig_symbols.update(re.findall(r"\b(wgpu[A-Za-z0-9_]+)\b", text))
    if not header_symbols:
        return (0, 0, 0.0)
    covered = len(header_symbols & zig_symbols)
    total = len(header_symbols)
    percent = (covered * 100.0) / total
    return covered, total, percent


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
    mapped_capability_count = 0

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
        if workload_ids:
            mapped_capability_count += 1
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

    total_capabilities = len(coverage.get("coverage", []))
    tracked_completion_percent = (implemented * 100.0 / total_capabilities) if total_capabilities else 0.0
    mapped_capability_percent = (mapped_capability_count * 100.0 / total_capabilities) if total_capabilities else 0.0
    dawn_header_covered, dawn_header_total, dawn_header_percent = _measure_dawn_header_api_surface_coverage()

    output = [
        "# Dawn vs Fawn Feature + Benchmark Coverage",
        "",
        "| Metric | % | How it was measured |",
        "|---|---:|---|",
        "| Tracked spec-capability completion | {percent:.1f}% ({done}/{total}) | `config/webgpu-spec-coverage.json` status counts |".format(
            percent=tracked_completion_percent,
            done=implemented,
            total=total_capabilities,
        ),
        "| Dawn header API-surface reference coverage (estimate) | {percent:.2f}% ({done}/{total}) | Dawn header `bench/vendor/dawn/third_party/webgpu-headers/src/webgpu.h` vs `wgpu*` symbols referenced in `zig/src` |".format(
            percent=dawn_header_percent,
            done=dawn_header_covered,
            total=dawn_header_total,
        ),
        "| Capability-to-benchmark mapping coverage | {percent:.2f}% ({done}/{total}) | `CAPABILITY_TO_WORKLOADS` intersection with `bench/workloads.amd.vulkan.extended.json` |".format(
            percent=mapped_capability_percent,
            done=mapped_capability_count,
            total=total_capabilities,
        ),
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
