# Doe Naming Contract (No Backward Compatibility)

## Product and package naming

1. Workspace/repo product: `fawn`
2. Runtime/backend family: `doe`
3. Browser distribution package: `@simulatte/fawn-browser`
4. Canonical JS/runtime package: `@simulatte/webgpu`

Legacy package identities are retained only as compatibility history:

1. `@doe/webgpu-core` / `@doe/webgpu` - retired package scope experiment

Public package naming now follows the product surface, not the backend implementation.
Doe remains the runtime/backend identity in artifact names, backend IDs, flags, and reports.

## Backend ID contract

External/runtime-visible backend IDs are now:

1. `dawn_delegate`
2. `doe_vulkan`
3. `doe_metal`
4. `doe_d3d12`

These IDs describe executor + API and replace all old `dawn_oracle` / `zig_*` IDs.

## Lane ID contract

Lane IDs use one shape:

`<api>_<executor>_<mode>`

Allowed executors:

1. `doe`
2. `dawn`

Current lane IDs:

1. `vulkan_dawn_release`
2. `vulkan_dawn_directional`
3. `vulkan_doe_app`
4. `vulkan_doe_comparable`
5. `vulkan_doe_release`
6. `d3d12_dawn_release`
7. `d3d12_doe_app`
8. `d3d12_doe_directional`
9. `d3d12_doe_comparable`
10. `d3d12_doe_release`
11. `metal_dawn_release`
12. `metal_doe_app`
13. `metal_doe_directional`
14. `metal_doe_comparable`
15. `metal_doe_release`

No old aliases are supported.

## Directory/module naming

Runtime backend modules align to executor/API identity:

1. `zig/src/backend/vulkan/`
2. `zig/src/backend/metal/`
3. `zig/src/backend/d3d12/`
4. `zig/src/backend/dawn_delegate_backend.zig`

Internal Zig type names may continue to include `Zig` (implementation language detail), but contracts/configs/reports use `doe_*` IDs.

## Reporting and benchmark naming

Report/config naming is now `doe-vs-dawn` / `doe_vs_dawn`, and runtime artifacts in `bench/out` were rewritten to the new backend/lane IDs.

## Migration status

This migration is complete and intentionally non-backward-compatible.
