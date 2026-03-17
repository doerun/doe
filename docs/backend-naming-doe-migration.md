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

1. `metal_doe_app`
2. `metal_doe_directional`
3. `metal_doe_comparable`
4. `metal_doe_release`
5. `metal_dawn_release`
6. `vulkan_doe_app`
7. `vulkan_doe_comparable`
8. `vulkan_doe_release`
9. `vulkan_dawn_release`
10. `d3d12_doe_app`
11. `d3d12_doe_directional`
12. `d3d12_doe_comparable`
13. `d3d12_doe_release`
14. `d3d12_dawn_release`

Legacy compatibility aliases:

1. `vulkan_dawn_directional` -> `vulkan_dawn_release`

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
