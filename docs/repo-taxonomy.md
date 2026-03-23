# Fawn repository taxonomy

## Purpose

Fawn is organized by product boundary first:

- engine/runtime
- package families
- browser integration
- benchmark evidence
- pipeline support

This avoids treating package subpaths or benchmark entrypoints as standalone
products.

## Top-level families

### Runtime

- `runtime/zig`
  - the Doe runtime, compiler, and backend implementation
- `runtime/bridge`
  - shared bridge and addon-facing native code used by package surfaces

### Packages

- `packages/webgpu`
  - the `@simulatte/webgpu` package family
- `packages/webgpu-doe`
  - the `@simulatte/webgpu-doe` package family

### Browser

- `browser/chromium`
  - the repo-local Chromium integration layer
- `browser/chromium_webgpu_lane`
  - the Chromium checkout/build workspace when kept in-tree

### Benchmarking

- `bench/single-runtime`
- `bench/native-compare`
- `bench/package-compare`
- `bench/browser`
- `bench/diagnostics`
- `bench/drop-in`
- `bench/shared`

### Pipeline

- `pipeline/agent`
- `config`
- `pipeline/lean`
- `pipeline/trace`

`config/` remains top-level for path stability, but it is conceptually owned by
the pipeline family.

## Legacy path note

Historical `nursery/*`, `zig/`, `agent/`, `lean/`, `trace/`, and `config/`
references may still appear in older artifacts or compatibility paths. Use the
families above as the canonical structure.
