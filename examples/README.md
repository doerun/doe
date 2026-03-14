# Examples status

This document tracks the command-stream examples in `examples/*_commands.json`.
It does not cover quirk sample JSON under `examples/quirks/` or notes such as
`examples/intel_gen12_temp_buffer.md`.

## Status legend

| Status | Meaning |
|--------|---------|
| `fresh-evidence` | The example appears in the latest published comparable/release artifact for at least one active lane. |
| `diagnostic` | The latest artifact includes the example, but the lane is not currently claimable for that example. |
| `contract-covered` | The example is referenced by at least one active workload contract, but it is absent from the latest published comparable/release artifacts. |
| `ungoverned` | The example exists on disk but is not referenced by any current smoke/extended/release workload matrix. |

Validation run for this doc pass:

- `python3 bench/schema_gate.py` -> `PASS`
- all 90 JSON files under `examples/` parse successfully

That means no obvious structurally broken example files were found in this pass.
Current status differences are evidence and governance differences, not JSON or
schema failures.

## Latest lane status (2026-03-10 artifacts)

| Lane | Latest artifact | Workloads in artifact | Unique command examples | Lane status |
|------|-----------------|-----------------------|-------------------------|-------------|
| AMD Vulkan release | `bench/out/amd-vulkan/20260310T153903Z/dawn-vs-doe.amd.vulkan.release.json` | 7 | 7 | `comparable`, overall `diagnostic` |
| Apple Metal extended-comparable | `bench/out/apple-metal/extended-comparable/20260310T171918Z/dawn-vs-doe.local.metal.extended.comparable.json` | 31 | 30 | `comparable`, overall `diagnostic` |
| Local D3D12 extended | `bench/workloads.local.d3d12.extended.json` | 11 contract rows | 11 contract examples | contract only; no fresh Windows artifact in inventory |

## Current diagnostic examples

These are the examples that appear in the latest artifact for a lane but are
not currently claimable for that lane.

| Lane | Example | Current read | Why |
|------|---------|--------------|-----|
| AMD Vulkan release | `examples/upload_1kb_commands.json` | comparable, not claimable | Latest 2026-03-10 release artifact shows negative `p50`, `p95`, and `p99` deltas for the tiny-upload row. |
| Apple Metal extended-comparable | `examples/upload_1mb_commands.json` | comparable, not claimable | Latest 2026-03-10 comparable artifact shows selected-timing `p95Percent=-28.039886`, so the 1 MB upload row blocks a fully claimable lane. |

Diagnostic does not mean malformed. It means the latest evidence does not yet
support claim language for that example in that lane.

## Fresh evidence-backed examples

Union of the latest AMD Vulkan release artifact and the latest Apple Metal
extended-comparable artifact: 30 unique command examples.

```text
examples/compute_dispatch_grid_commands.json
examples/concurrent_execution_single_commands.json
examples/copy_buffer_to_texture_commands.json
examples/copy_protocol_commands.json
examples/copy_texture_to_buffer_commands.json
examples/copy_texture_to_texture_commands.json
examples/dispatch_workgroups_commands.json
examples/draw_call_proxy_commands.json
examples/draw_call_proxy_macro_commands.json
examples/draw_call_redundant_pipeline_bindings_commands.json
examples/draw_call_render_bundle_dynamic_bindings_commands.json
examples/draw_call_render_bundle_dynamic_pipeline_commands.json
examples/draw_call_state_bindings_commands.json
examples/p0_resource_lifecycle_commands.json
examples/shader_compile_stress_commands.json
examples/surface_full_presentation_commands.json
examples/texture_sampler_write_query_destroy_commands.json
examples/texture_sampler_write_query_destroy_macro_commands.json
examples/uniform_buffer_update_writebuffer_partial_single_commands.json
examples/upload_16mb_commands.json
examples/upload_1gb_commands.json
examples/upload_1kb_commands.json
examples/upload_1mb_commands.json
examples/upload_256mb_commands.json
examples/upload_4gb_commands.json
examples/upload_4mb_commands.json
examples/upload_64kb_commands.json
examples/workgroup_atomic_commands.json
examples/workgroup_non_atomic_commands.json
examples/zero_initialize_workgroup_memory_256_commands.json
```

## Contract-covered but not in the latest published artifacts

These examples are wired into at least one active workload contract, but they
do not appear in the latest published AMD Vulkan release artifact or the latest
Apple Metal extended-comparable artifact.

```text
examples/async_pipeline_diagnostics_commands.json
examples/draw_call_indexed_proxy_commands.json
examples/draw_call_indexed_proxy_macro_commands.json
examples/matrix_vector_mul_32768x2048_commands.json
examples/matrix_vector_mul_32768x2048_swizzle1_commands.json
examples/matrix_vector_mul_32768x2048_workgroupshared_swizzle1_commands.json
examples/p0_compute_indirect_timestamp_commands.json
examples/p0_render_multidraw_commands.json
examples/p0_render_multidraw_indexed_commands.json
examples/p0_render_pixel_local_storage_barrier_commands.json
examples/p1_capability_introspection_commands.json
examples/p1_capability_introspection_macro_commands.json
examples/p1_resource_table_immediates_commands.json
examples/p2_lifecycle_refcount_commands.json
examples/p2_lifecycle_refcount_macro_commands.json
examples/surface_presentation_commands.json
examples/texture_raster_proxy_commands.json
```

## Ungoverned command examples

These files are not currently referenced by any active smoke, extended, or
release workload matrix in the repo. They are not automatically broken, but
they should not be described as covered or supported until a workload contract
and fresh artifact include them.

```text
examples/buffer_map_commands.json
examples/compute_dispatch_indirect_large_args_commands.json
examples/compute_dispatch_indirect_live_args_commands.json
examples/compute_dispatch_indirect_single_commands.json
examples/compute_dispatch_workgroups_2d_sweep_commands.json
examples/compute_dispatch_workgroups_3d_sweep_commands.json
examples/compute_dispatch_workgroups_indirect_pipeline_switch_commands.json
examples/compute_kernel_dispatch_1000_commands.json
examples/copy_buffer_to_buffer_4kb_commands.json
examples/copy_buffer_to_buffer_overlap_commands.json
examples/copy_buffer_to_texture_tight_pitch_commands.json
examples/copy_texture_to_buffer_padded_commands.json
examples/copy_texture_to_texture_stress_commands.json
examples/copy_texture_to_texture_subresource_commands.json
examples/dispatch_commands.json
examples/kernel_dispatch_commands.json
examples/p0_render_pixel_local_storage_barrier_macro_commands.json
examples/p1_resource_table_immediates_macro_commands.json
examples/render_draw_indexed_indirect_u16_commands.json
examples/render_draw_indexed_indirect_u32_commands.json
examples/render_draw_indirect_legacy_equivalent_commands.json
examples/render_pass_depth_stencil_commands.json
examples/render_pass_dynamic_viewport_scissor_commands.json
examples/render_pass_loadops_clear_load_commands.json
examples/render_pass_multisample_resolve_commands.json
examples/render_pass_stencil_ref_sweep_commands.json
examples/render_pass_storeops_discard_commands.json
examples/resource_buffer_map_double_request_guard_commands.json
examples/resource_buffer_map_partial_read_4kb_commands.json
examples/resource_buffer_map_partial_write_64kb_commands.json
examples/resource_buffer_map_readback_1kb_commands.json
examples/resource_buffer_map_readback_64kb_commands.json
examples/resource_buffer_map_unmap_storm_commands.json
examples/resource_buffer_map_write_1kb_commands.json
examples/resource_buffer_map_write_64kb_commands.json
examples/webgpu_full_api_commands.json
```
