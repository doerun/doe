# Changelog

## 0.1.2

### Docs

- Rewrote the package README intro and readiness notes to describe the shipped
  package in concrete terms and remove slogan-style release language
- Clarified that the published package currently targets `darwin-arm64`

## 0.1.1

### WGSL compiler

- Replaced regex-based WGSL-to-MSL line translator with AST-based compiler
  (lexer, parser, emitter). Handles structs, helper functions, multiple entry
  points, override constants, `var<workgroup>`, `enable f16`/`subgroups`,
  subgroup operations, barriers, and all Doppler compute shaders.

### New APIs

- `pipeline.getBindGroupLayout(index)` — returns bind group layout from
  compiled shader metadata
- `pass.dispatchWorkgroupsIndirect(buffer, offset)` — indirect compute dispatch
- `device.createComputePipelineAsync(descriptor)` — async wrapper over sync
  pipeline creation

### Fixes

- `createRenderPipeline` now prints a diagnostic when a descriptor is passed,
  instead of silently ignoring it
- Compute pipeline entry point now uses the descriptor's `entryPoint` field
  instead of hardcoding `main_kernel`
- `main` entry points are automatically renamed to `main_kernel` for Metal
  compatibility

### Prebuilds

- Updated `libdoe_webgpu.dylib` and `doe_napi.node` for darwin-arm64

## 0.1.0

Initial release. Metal compute backend with WGSL support, N-API addon,
JS wrapper classes, device limits, adapter features.
