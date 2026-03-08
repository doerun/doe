# Proposed zig source inventory for core and full

Inventory status: `draft`

Scope:

- current `zig/src` source inventory for the future `core` / `full` split
- refactor planning only
- no runtime behavior changes

This document maps the current `zig/src` tree into four buckets:

1. `keep_in_core`
   - can move into `core` with little or no semantic surgery
2. `move_to_full`
   - clearly belongs in `full`
3. `needs_api_extraction`
   - current file spans both contracts, or imports a mixed API/state layer, so
     it cannot be moved cleanly yet
4. `ancillary_or_track_a`
   - keep outside the `core` / `full` runtime split for now

Use this with:

- `SUPPORT_CONTRACTS.md`
- `LAYERING_PLAN.md`

## Reading rule

This is an extraction inventory, not a statement that the current file already
matches the target layer.

Current repo note:

- `zig/src/core/` now exists for an initial low-risk extraction slice
- root-path compatibility shims remain for the migrated files so the rest of the
  tree can move incrementally

Examples:

1. a file may eventually live in `core`, but still be marked
   `needs_api_extraction` because it imports the current mixed `webgpu_ffi.zig`
   state
2. a file may be `full` because it is clearly render/surface/lifecycle-only
3. a file may be `ancillary_or_track_a` because it serves drop-in ABI or Dawn
   delegate lanes rather than the future package/runtime split

## Immediate extraction hotspots

These are the files that currently carry the strongest `core` / `full` bleed:

1. `zig/src/model.zig`
2. `zig/src/webgpu_ffi.zig`
3. `zig/src/wgpu_types.zig`
4. `zig/src/wgpu_loader.zig`
5. `zig/src/wgpu_commands.zig`
6. `zig/src/wgpu_resources.zig`
7. `zig/src/backend/metal/mod.zig`
8. `zig/src/backend/metal/metal_native_runtime.zig`
9. `zig/src/backend/vulkan/mod.zig`
10. `zig/src/backend/vulkan/native_runtime.zig`
11. `zig/src/backend/vulkan/vulkan_runtime_state.zig`
12. `zig/src/backend/d3d12/mod.zig`

If the refactor starts anywhere else, the boundary will erode immediately.

## keep_in_core

### Parsing, trace, replay, quirk dispatch

Paths:

- `zig/src/command_json.zig`
- `zig/src/command_json_extra.zig`
- `zig/src/command_json_raw.zig`
- `zig/src/command_parse_helpers.zig`
- `zig/src/trace.zig`
- `zig/src/replay.zig`
- `zig/src/runtime.zig`
- `zig/src/quirk/mod.zig`
- `zig/src/quirk/quirk_actions.zig`
- `zig/src/quirk/quirk_json.zig`
- `zig/src/quirk/runtime.zig`
- `zig/src/quirk/toggle_registry.zig`
- `zig/src/quirk_json.zig`

Why:

- deterministic parsing, trace/replay, and quirk selection are shared runtime
  foundations
- these files do not define render/surface ownership

### WGSL frontend, IR, and proof plumbing

Paths:

- `zig/src/doe_wgsl/ast.zig`
- `zig/src/doe_wgsl/emit_dxil.zig`
- `zig/src/doe_wgsl/emit_hlsl.zig`
- `zig/src/doe_wgsl/emit_msl.zig`
- `zig/src/doe_wgsl/emit_msl_ir.zig`
- `zig/src/doe_wgsl/emit_spirv.zig`
- `zig/src/doe_wgsl/ir.zig`
- `zig/src/doe_wgsl/ir_builder.zig`
- `zig/src/doe_wgsl/ir_validate.zig`
- `zig/src/doe_wgsl/lexer.zig`
- `zig/src/doe_wgsl/mod.zig`
- `zig/src/doe_wgsl/parser.zig`
- `zig/src/doe_wgsl/sema.zig`
- `zig/src/doe_wgsl/sema_attrs.zig`
- `zig/src/doe_wgsl/sema_body.zig`
- `zig/src/doe_wgsl/sema_helpers.zig`
- `zig/src/doe_wgsl/sema_types.zig`
- `zig/src/doe_wgsl/spirv_builder.zig`
- `zig/src/doe_wgsl/token.zig`
- `zig/src/doe_wgsl_msl.zig`
- `zig/src/lean_proof.zig`
- `zig/src/env_flags.zig`
- `zig/src/main_print.zig`

Why:

- the compiler frontend and proof-elimination hooks are shared foundations for
  both compute-only and full headless surfaces
- stage-aware lowering can stay in `core`; `full` depends on it

### Shared backend policy and neutral helpers

Paths:

- `zig/src/backend/backend_errors.zig`
- `zig/src/backend/backend_ids.zig`
- `zig/src/backend/backend_policy.zig`
- `zig/src/backend/backend_selection.zig`
- `zig/src/backend/backend_telemetry.zig`
- `zig/src/backend/common/artifact_meta.zig`
- `zig/src/backend/common/errors.zig`
- `zig/src/backend/common/timing.zig`

Why:

- these files describe generic backend identity, timing, and error contracts
- they do not by themselves force render/surface ownership

### Compute-focused runtime shards

Paths:

- `zig/src/core/wgpu_commands_compute.zig`
- `zig/src/core/wgpu_commands_copy.zig`
- `zig/src/wgpu_p1_capability_procs.zig`
- `zig/src/wgpu_sandbox_guard.zig`
- `zig/src/core/wgpu_ffi_sync.zig`

Why:

- these files are already centered on compute, copy, capability probing, and
  map/wait/sync behavior
- they are good early candidates for a `core` subtree
- temporary root-path shim files remain at:
  - `zig/src/wgpu_commands_compute.zig`
  - `zig/src/wgpu_commands_copy.zig`
  - `zig/src/wgpu_ffi_sync.zig`
  - these should be removed after the remaining imports are retargeted

### D3D12 compute runtime candidates

Paths:

- `zig/src/backend/d3d12/d3d12_bridge.c`
- `zig/src/backend/d3d12/d3d12_bridge.h`
- `zig/src/backend/d3d12/d3d12_errors.zig`
- `zig/src/backend/d3d12/d3d12_native_runtime.zig`
- `zig/src/backend/d3d12/d3d12_native_runtime_stub.zig`
- `zig/src/backend/d3d12/d3d12_timing.zig`

Why:

- current D3D12 native runtime is still compute-first
- this is the cleanest backend candidate for an early `core` carve-out

### Backend adapter/device/queue and pure compute/copy/upload shards

Paths:

- `zig/src/backend/metal/metal_adapter.zig`
- `zig/src/backend/metal/metal_device.zig`
- `zig/src/backend/metal/metal_errors.zig`
- `zig/src/backend/metal/metal_instance.zig`
- `zig/src/backend/metal/metal_queue.zig`
- `zig/src/backend/metal/metal_sync.zig`
- `zig/src/backend/metal/metal_timing.zig`
- `zig/src/backend/metal/commands/compute_encode.zig`
- `zig/src/backend/metal/commands/copy_encode.zig`
- `zig/src/backend/metal/pipeline/msl_compile_runner.zig`
- `zig/src/backend/metal/pipeline/shader_artifact_manifest.zig`
- `zig/src/backend/metal/pipeline/wgsl_ingest.zig`
- `zig/src/backend/metal/pipeline/wgsl_to_msl_runner.zig`
- `zig/src/backend/metal/upload/staging_ring.zig`
- `zig/src/backend/metal/upload/upload_path.zig`
- `zig/src/backend/vulkan/vulkan_adapter.zig`
- `zig/src/backend/vulkan/vulkan_device.zig`
- `zig/src/backend/vulkan/vulkan_errors.zig`
- `zig/src/backend/vulkan/vulkan_instance.zig`
- `zig/src/backend/vulkan/vulkan_queue.zig`
- `zig/src/backend/vulkan/vulkan_sync.zig`
- `zig/src/backend/vulkan/vulkan_timing.zig`
- `zig/src/backend/vulkan/commands/compute_encode.zig`
- `zig/src/backend/vulkan/commands/copy_encode.zig`
- `zig/src/backend/vulkan/pipeline/shader_artifact_manifest.zig`
- `zig/src/backend/vulkan/pipeline/spirv_opt_runner.zig`
- `zig/src/backend/vulkan/pipeline/wgsl_ingest.zig`
- `zig/src/backend/vulkan/pipeline/wgsl_to_spirv_runner.zig`
- `zig/src/backend/vulkan/upload/staging_ring.zig`
- `zig/src/backend/vulkan/upload/upload_path.zig`

Why:

- these files are already biased toward adapter/device discovery, compute/copy,
  shader ingestion, and upload path control
- they are better starting points for `core` than the monolithic backend roots

## move_to_full

### Render command/model surface

Paths:

- `zig/src/doe_render_native.zig`
- `zig/src/wgpu_render_api.zig`
- `zig/src/wgpu_render_assets.zig`
- `zig/src/wgpu_render_commands.zig`
- `zig/src/wgpu_render_draw_loops.zig`
- `zig/src/wgpu_render_indexing.zig`
- `zig/src/wgpu_render_p0.zig`
- `zig/src/wgpu_render_resources.zig`
- `zig/src/wgpu_render_types.zig`
- `zig/src/backend/metal/commands/render_encode.zig`
- `zig/src/backend/vulkan/commands/render_encode.zig`

Why:

- these files are explicitly render-pipeline, render-pass, draw, or render
  resource modules
- they should leave the shared layer first

### Surface and presentation surface

Paths:

- `zig/src/wgpu_ffi_surface.zig`
- `zig/src/wgpu_surface_procs.zig`
- `zig/src/backend/metal/surface/present.zig`
- `zig/src/backend/metal/surface/surface_configure.zig`
- `zig/src/backend/metal/surface/surface_create.zig`
- `zig/src/backend/vulkan/surface/present.zig`
- `zig/src/backend/vulkan/surface/surface_configure.zig`
- `zig/src/backend/vulkan/surface/surface_create.zig`

Why:

- these are full-only or browser-adjacent headless presentation concerns
- `core` should not own surface lifecycle or present semantics

### Lifecycle and async render diagnostics

Paths:

- `zig/src/wgpu_async_diagnostics_command.zig`
- `zig/src/wgpu_async_pixel_local_storage.zig`
- `zig/src/wgpu_async_procs.zig`
- `zig/src/wgpu_p2_lifecycle_procs.zig`

Why:

- these files are tied to async render pipeline creation, shader compilation
  info, error scopes, lifecycle add-ref paths, or pixel-local-storage
- they belong with `full` object-model and render/lifecycle semantics

## needs_api_extraction

### Top-level command/type/runtime boundary

Paths:

- `zig/src/model.zig`
- `zig/src/main.zig`
- `zig/src/execution.zig`
- `zig/src/webgpu_ffi.zig`
- `zig/src/wgpu_loader.zig`
- `zig/src/wgpu_types.zig`
- `zig/src/wgpu_types_procs.zig`
- `zig/src/wgpu_commands.zig`
- `zig/src/wgpu_resources.zig`
- `zig/src/wgpu_extended_commands.zig`
- `zig/src/wgpu_texture_procs.zig`
- `zig/src/wgpu_capability_runtime.zig`
- `zig/src/wgpu_p0_procs.zig`
- `zig/src/wgpu_p1_resource_table_procs.zig`
- `zig/src/doe_device_caps.zig`

Why:

- these files currently encode one combined command universe and one combined
  proc/type/state ledger
- they mix compute, texture, render, surface, lifecycle, and benchmark
  claimability concerns in one layer
- they need sharding before any clean `core` / `full` move is possible

### Legacy monolithic native ABI path

Paths:

- `zig/src/doe_wgpu_native.zig`
- `zig/src/doe_compute_ext_native.zig`
- `zig/src/doe_compute_fast.zig`
- `zig/src/doe_shader_native.zig`

Why:

- these files are sharded out of the old monolithic Doe native ABI, but they
  still import or extend `doe_wgpu_native.zig`
- they cannot become a clean `core` layer until the legacy ABI itself is split
  or retired

### Shared backend interface and capability model

Paths:

- `zig/src/backend/backend_iface.zig`
- `zig/src/backend/backend_registry.zig`
- `zig/src/backend/backend_runtime.zig`
- `zig/src/backend/common/capabilities.zig`
- `zig/src/backend/common/command_info.zig`
- `zig/src/backend/common/command_requirements.zig`

Why:

- these files currently assume a single mixed command set spanning both compute
  and full-only operations
- they need separate `core` and `full` command/capability views

### Backend roots still owning mixed state

Paths:

- `zig/src/backend/d3d12/mod.zig`
- `zig/src/backend/metal/metal_bridge.h`
- `zig/src/backend/metal/metal_bridge.m`
- `zig/src/backend/metal/metal_native_runtime.zig`
- `zig/src/backend/metal/metal_native_runtime_stub.zig`
- `zig/src/backend/metal/metal_runtime_state.zig`
- `zig/src/backend/metal/mod.zig`
- `zig/src/backend/metal/pipeline/pipeline_cache.zig`
- `zig/src/backend/metal/procs/proc_export.zig`
- `zig/src/backend/metal/procs/proc_table.zig`
- `zig/src/backend/metal/resources/bind_group.zig`
- `zig/src/backend/metal/resources/buffer.zig`
- `zig/src/backend/metal/resources/resource_table.zig`
- `zig/src/backend/metal/resources/sampler.zig`
- `zig/src/backend/metal/resources/texture.zig`
- `zig/src/backend/vulkan/mod.zig`
- `zig/src/backend/vulkan/native_runtime.zig`
- `zig/src/backend/vulkan/native_runtime_stub.zig`
- `zig/src/backend/vulkan/vulkan_runtime_state.zig`
- `zig/src/backend/vulkan/pipeline/pipeline_cache.zig`
- `zig/src/backend/vulkan/procs/proc_export.zig`
- `zig/src/backend/vulkan/procs/proc_table.zig`
- `zig/src/backend/vulkan/resources/bind_group.zig`
- `zig/src/backend/vulkan/resources/buffer.zig`
- `zig/src/backend/vulkan/resources/resource_table.zig`
- `zig/src/backend/vulkan/resources/sampler.zig`
- `zig/src/backend/vulkan/resources/texture.zig`

Why:

- these files either:
  - directly own mixed compute/render/surface runtime state, or
  - are thin wrappers over a mixed runtime-state module, or
  - export one combined backend proc surface
- they are the main files that require composition-based API extraction

## ancillary_or_track_a

### Drop-in ABI and browser-lane surfaces

Paths:

- `zig/src/dropin/dropin_abi_procs.zig`
- `zig/src/dropin/dropin_behavior_policy.zig`
- `zig/src/dropin/dropin_build_info.zig`
- `zig/src/dropin/dropin_diagnostics.zig`
- `zig/src/dropin/dropin_router.zig`
- `zig/src/dropin/dropin_symbol_ownership.zig`
- `zig/src/wgpu_dropin_ext_a.zig`
- `zig/src/wgpu_dropin_ext_b.zig`
- `zig/src/wgpu_dropin_ext_c.zig`
- `zig/src/wgpu_dropin_lib.zig`
- `zig/src/backend/dawn_delegate_backend.zig`

Why:

- these files serve drop-in ABI, Dawn delegate, and browser-lane compatibility
  concerns
- they are not the right place to define the `core` / `full` package boundary

### Generated artifacts and maintenance scripts

Paths:

- `zig/src/bench/out/shader-artifacts/vulkan-manifest-1.json`
- `zig/src/bench/out/shader-artifacts/vulkan-manifest-2.json`
- `zig/src/fix_usingnamespace.py`
- `zig/src/update_webgpu_ffi.py`

Why:

- these are generated artifacts or maintenance helpers, not runtime-layer
  modules
- the manifest JSON files should not stay under `zig/src` long-term

## Recommended first extraction sequence

1. split the command/type boundary:
   - `model.zig`
   - `wgpu_types.zig`
   - `wgpu_loader.zig`
   - `webgpu_ffi.zig`
2. split backend roots from backend shards:
   - `backend/metal/mod.zig`
   - `backend/metal/metal_native_runtime.zig`
   - `backend/vulkan/mod.zig`
   - `backend/vulkan/native_runtime.zig`
   - `backend/vulkan/vulkan_runtime_state.zig`
   - `backend/d3d12/mod.zig`
3. move obvious full-only files:
   - `wgpu_render_*`
   - `wgpu_surface_procs.zig`
   - `wgpu_ffi_surface.zig`
   - render/surface backend subtrees
4. continue growing the physical `zig/src/core/` directory and create
   `zig/src/full/` once the first full-only extraction slice is ready

## Sanity rule for future edits

If a patch adds new render/surface/lifecycle state to any file listed above
under `keep_in_core`, the patch should be treated as boundary regression unless
the inventory and support contracts are updated in the same change.
