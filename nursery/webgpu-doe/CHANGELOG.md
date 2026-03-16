# Changelog

All notable changes to `@simulatte/webgpu-doe` are documented in this file.

## [Unreleased]

### Added

- Added reusable kernel-scoped binding sets through `kernel.bindings.create(...)`.
- Added batched compute submission through `gpu.compute.begin(...)`.
- Added the lower-level Doe command encoder path through
  `gpu.commandEncoder.create(...)`.
- Added `kernel.encode(...)` so compiled kernels can target a shared Doe batch
  or explicit Doe compute pass.
- Expanded the standalone package example and smoke test to cover the new
  lower-overhead execution paths.

### Fixed

- Corrected Doe workgroup validation so dispatch counts are checked against
  `maxComputeWorkgroupsPerDimension`, not `@workgroup_size(...)` limits such as
  `maxComputeWorkgroupSizeX` or `maxComputeInvocationsPerWorkgroup`.

## [0.3.2] - 2026-03-15

### Added

- Reintroduced `@simulatte/webgpu-doe` as a standalone helper-only package.
- Exported `createDoeNamespace(...)`, `doe`, and the default Doe namespace.
- Added standalone TypeScript types for the Doe helper contract.
- Added a package-local smoke test and example showing how to bind Doe to
  `@simulatte/webgpu` or `@simulatte/webgpu/compute`.

### Notes

- This package intentionally does not ship a runtime, addon, or Bun FFI layer.
- The Doe helper surface remains compatible with the helper contract currently
  shipped inside `@simulatte/webgpu`.
