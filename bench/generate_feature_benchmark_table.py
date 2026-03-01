#!/usr/bin/env python3
"""Generate Dawn-vs-Doe feature and benchmark coverage markdown table."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CAPABILITY_TO_WORKLOADS: dict[str, list[str]] = {
    "queue_sync_mode": ["par_buffer_upload_64kb", "exp_draw_indexed_render_proxy"],
    "render_draw_offsets": ["exp_render_draw_throughput_proxy"],
    "render_draw_indexed": ["exp_draw_indexed_render_proxy", "ctr_render_multidraw_indexed_contract"],
    "render_core_api_surface": [
        "exp_render_draw_throughput_proxy",
        "par_render_draw_state_bindings",
        "exp_draw_indexed_render_proxy",
    ],
    "render_pass_state_bindings": [
        "par_render_draw_state_bindings",
        "par_render_draw_redundant_pipeline_bindings",
    ],
    "render_draw_encode_modes": [
        "exp_render_draw_throughput_proxy",
        "par_render_bundle_dynamic_bindings",
    ],
    "textured_render_workload_contract": [
        "exp_texture_sampling_raster_proxy",
        "ctr_texture_sampler_write_query_destroy_contract",
        "ctr_texture_sampler_write_query_destroy_contract_mip8",
    ],
    "render_bundle_execution": [
        "par_render_bundle_dynamic_bindings",
        "par_render_bundle_dynamic_pipeline_bindings",
    ],
    "surface_presentation": ["ctr_surface_presentation_contract"],
    "async_pipeline_diagnostics": ["ctr_async_pipeline_diagnostics_contract"],
    "render_pass_state_space": [
        "par_render_draw_state_bindings",
        "par_render_draw_redundant_pipeline_bindings",
        "exp_draw_indexed_render_proxy",
    ],
    "timestamp_query_claimability": [
        "ctr_compute_indirect_timestamp_contract",
        "ctr_render_multidraw_contract",
    ],
    "feature_buffer_map_extended_usages": [
        "buffer_map_readback_1kb",
        "buffer_map_readback_64kb",
        "buffer_map_write_1kb",
        "buffer_map_write_64kb",
        "buffer_map_partial_read_4kb",
        "buffer_map_partial_write_64kb",
        "buffer_map_unmap_storm_macro",
    ],
    "feature_multi_draw_indirect": [
        "dispatch_indirect_1",
        "dispatch_indirect_live_args",
        "dispatch_indirect_large_args",
        "dispatch_workgroups_2d_sweep",
        "dispatch_workgroups_3d_sweep",
        "dispatch_workgroups_indirect_pipeline_switch",
        "draw_indexed_indirect_u16",
        "draw_indexed_indirect_u32",
        "draw_indirect_legacy_equivalent",
    ],
    "texture_query_assertions": [
        "ctr_texture_sampler_write_query_destroy_contract",
        "ctr_texture_sampler_write_query_destroy_contract_mip8",
    ],
    "p0_buffer_destroy_and_barrier_clear": ["ctr_resource_lifecycle_contract"],
    "p0_compute_indirect_async_timestamp": ["ctr_compute_indirect_timestamp_contract"],
    "p0_query_set_introspection_lifecycle": [
        "ctr_compute_indirect_timestamp_contract",
        "ctr_render_multidraw_contract",
        "ctr_render_multidraw_indexed_contract",
    ],
    "p0_render_occlusion_multidraw_timestamp": [
        "ctr_render_multidraw_contract",
        "ctr_render_multidraw_indexed_contract",
    ],
    "p0_device_destroy_lifecycle": ["ctr_resource_lifecycle_contract"],
    "p0_render_pixel_local_storage_barrier": [
        "ctr_render_pixel_local_storage_barrier_contract",
        "ctr_render_pixel_local_storage_barrier_macro_500",
    ],
    "p1_capability_introspection_surface": [
        "ctr_capability_introspection_contract",
        "ctr_capability_introspection_macro_500",
    ],
    "p1_resource_table_immediates_surface": [
        "ctr_resource_table_immediates_contract",
        "ctr_resource_table_immediates_macro_500",
    ],
    "p2_lifecycle_addref_surface": [
        "ctr_lifecycle_refcount_contract",
        "ctr_lifecycle_refcount_macro_200",
    ],
}

FEATURE_INVENTORY_WORKLOADS = [
    "ctr_capability_introspection_contract",
    "ctr_capability_introspection_macro_500",
]


def _workloads_for_capability(capability_id: str) -> list[str]:
    mapped = CAPABILITY_TO_WORKLOADS.get(capability_id)
    if mapped is not None:
        return mapped
    if capability_id.startswith("feature_"):
        return FEATURE_INVENTORY_WORKLOADS
    return []


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
        default="bench/out/dawn-vs-doe-feature-benchmark-coverage.md",
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


def _benchmark_class(item: dict[str, object]) -> str:
    value = item.get("benchmarkClass")
    if isinstance(value, str) and value in ("comparable", "directional"):
        return value
    return "comparable"


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
    comparable_workloads = {
        entry["id"]
        for entry in workloads.get("workloads", [])
        if isinstance(entry, dict) and entry.get("comparable") is True
    }
    rows: list[str] = []
    implemented = 0
    partial = 0
    tracked = 0
    planned = 0
    blocked = 0
    mapped_capability_count = 0
    comparable_mapped_capability_count = 0
    comparable_eligible_capability_count = 0
    comparable_eligible_mapped_capability_count = 0
    directional_capability_ids: list[str] = []

    for item in coverage.get("coverage", []):
        status = item.get("status", "unknown")
        if status == "implemented":
            implemented += 1
        elif status == "partial":
            partial += 1
        elif status == "tracked":
            tracked += 1
        elif status == "planned":
            planned += 1
        elif status == "blocked":
            blocked += 1
        else:
            planned += 1
        capability_id = item.get("capabilityId", "")
        benchmark_class = _benchmark_class(item)
        if benchmark_class == "directional":
            directional_capability_ids.append(capability_id)
        else:
            comparable_eligible_capability_count += 1
        workload_ids = [workload for workload in _workloads_for_capability(capability_id) if workload in known_workloads]
        if workload_ids:
            mapped_capability_count += 1
            if any(workload in comparable_workloads for workload in workload_ids):
                comparable_mapped_capability_count += 1
                if benchmark_class == "comparable":
                    comparable_eligible_mapped_capability_count += 1
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
            "| `{capability}` | `{status}` | `{priority}` | `{benchmark_class}` | {contract} | {workloads} | {dawn} |".format(
                capability=capability_id,
                status=status,
                priority=item.get("priority", ""),
                benchmark_class=benchmark_class,
                contract=_compact(item.get("contract", "")),
                workloads=workload_field,
                dawn=dawn_field,
            )
        )

    total_capabilities = len(coverage.get("coverage", []))
    tracked_inventory_count = total_capabilities - planned
    tracked_inventory_percent = (tracked_inventory_count * 100.0 / total_capabilities) if total_capabilities else 0.0
    implemented_completion_percent = (implemented * 100.0 / total_capabilities) if total_capabilities else 0.0
    mapped_capability_percent = (mapped_capability_count * 100.0 / total_capabilities) if total_capabilities else 0.0
    comparable_mapped_capability_percent = (
        (comparable_mapped_capability_count * 100.0 / total_capabilities)
        if total_capabilities
        else 0.0
    )
    comparable_eligible_mapped_capability_percent = (
        (comparable_eligible_mapped_capability_count * 100.0 / comparable_eligible_capability_count)
        if comparable_eligible_capability_count
        else 0.0
    )
    directional_capability_count = len(directional_capability_ids)
    directional_capability_percent = (
        (directional_capability_count * 100.0 / total_capabilities)
        if total_capabilities
        else 0.0
    )
    dawn_header_covered, dawn_header_total, dawn_header_percent = _measure_dawn_header_api_surface_coverage()

    output = [
        "# Dawn vs Doe Feature + Benchmark Coverage",
        "",
        "| Metric | % | How it was measured |",
        "|---|---:|---|",
        "| Spec-universe inventory tracking completion | {percent:.1f}% ({done}/{total}) | `config/webgpu-spec-coverage.json` entries not in `planned` state |".format(
            percent=tracked_inventory_percent,
            done=tracked_inventory_count,
            total=total_capabilities,
        ),
        "| Runtime-implemented capability completion | {percent:.1f}% ({done}/{total}) | `config/webgpu-spec-coverage.json` entries with `status=implemented` |".format(
            percent=implemented_completion_percent,
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
        "| Comparable capability benchmark coverage | {percent:.2f}% ({done}/{total}) | Capabilities with at least one mapped workload where `comparable=true` in `bench/workloads.amd.vulkan.extended.json` |".format(
            percent=comparable_mapped_capability_percent,
            done=comparable_mapped_capability_count,
            total=total_capabilities,
        ),
        "| Comparable capability benchmark coverage (eligible-only) | {percent:.2f}% ({done}/{total}) | Excludes capability entries with `benchmarkClass=directional` in `config/webgpu-spec-coverage.json` |".format(
            percent=comparable_eligible_mapped_capability_percent,
            done=comparable_eligible_mapped_capability_count,
            total=comparable_eligible_capability_count,
        ),
        "| Directional-only capability domains | {percent:.2f}% ({done}/{total}) | Capability entries with `benchmarkClass=directional` in `config/webgpu-spec-coverage.json` |".format(
            percent=directional_capability_percent,
            done=directional_capability_count,
            total=total_capabilities,
        ),
        "",
        f"- generatedFrom: `{args.coverage}` + `{args.workloads}` + `{args.dawn_map}`",
        f"- totals: implemented={implemented}, partial={partial}, tracked={tracked}, planned={planned}, blocked={blocked}",
        "- directionalCapabilityIds: {ids}".format(
            ids=", ".join(f"`{capability_id}`" for capability_id in sorted(directional_capability_ids))
            if directional_capability_ids
            else "none"
        ),
        "",
        "| Capability | Status | Priority | Benchmark Class | Fawn Contract | Benchmark Workloads | Dawn Baseline Filter(s) |",
        "|---|---|---|---|---|---|---|",
    ]
    output.extend(rows)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(output) + "\n")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
