# Doe repository taxonomy

## Purpose

Doe is organized by product boundary first:

- engine/runtime
- package families
- browser integration
- benchmark evidence
- pipeline support

This avoids treating package subpaths or benchmark entrypoints as standalone
products.

For a shared project link, use the [Doe overview](https://github.com/doerun/doe#readme).
The root keeps product entry points, licensing, configuration, and automatically
discovered agent instructions. Supporting archives live with their owning families.

## Top-level families

### Runtime

- `runtime/zig`
  - the Doe runtime, compiler, and backend implementation
  - `runtime/zig/src/README.md` is the source ownership map
  - `runtime/zig/source-layout.json` is the machine-enforced directory contract
- `runtime/bridge`
  - shared bridge and addon-facing native code used by package surfaces

### Packages

- `packages/doe-gpu`
  - the current public npm package surface

### Browser

- `browser/chromium`
  - the repo-local Chromium integration layer
- `browser/chromium_webgpu_lane`
  - the Chromium checkout/build workspace when kept in-tree

### Conformance and examples

- `bench/cts`
  - repo-only CTS provider shims and related execution glue
- `examples`
  - command examples, sample receipts, and checked sample artifacts

### Demos and scripts

- `demos`
  - experimental demos and diagnostic sample hosts
- `scripts`
  - contributor maintenance and report-generation scripts

### Benchmarking

- `bench/single-runtime`
- `bench/native-compare`
- `bench/executors/package-webgpu`
- `bench/browser`
- `bench/diagnostics`
- `bench/drop-in`
- `bench/shared`

### Pipeline

- `pipeline/agent`
- `config`
- `pipeline/lean`
- `pipeline/trace`
- `pipeline/upstream_intelligence`
- `pipeline/dawn-research`
  - retained Gerrit research scripts and corpus used for offline replay

`config/` remains top-level for path stability, but it is conceptually owned by
the pipeline family.

### Documentation archives

- `docs/archive/nursery`
  - navigation from former nursery surfaces to their current owners

## Legacy path note

Historical `dawn-research/`, `nursery/*`, `zig/`, `agent/`, `lean/`, `trace/`, and `config/`
references may still appear in older artifacts or compatibility paths. Use the
families above as the canonical structure. Retained evidence keeps its original
paths and bytes; current commands and navigation use the relocated paths.
