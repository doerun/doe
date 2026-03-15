# Changelog

All notable changes to `@simulatte/webgpu-doe` are documented in this file.

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
