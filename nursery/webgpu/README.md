# @simulatte/webgpu

Canonical Doe WebGPU package for browserless benchmarking, CI workflows, and
headless runtime integration.

Doe is a WebGPU backend written in Zig that replaces Dawn (Chromium's C++
WebGPU implementation). The native runtime targets Vulkan/Metal/D3D12 with
explicit allocator control. In this package, Node uses an N-API addon and Bun
uses Bun FFI to load `libdoe_webgpu`. Optional `-Dlean-verified=true` builds
in the broader Fawn runtime can remove specific proved branches in the quirk
dispatch path; package consumers should not assume that path by default.

This directory is the package root for `@simulatte/webgpu`. It contains the
Node provider source, the addon build contract, the Bun FFI entrypoint, and
the CLI helpers used by benchmark and CI workflows.

Surface maturity:

- Node is the primary supported package surface (N-API bridge).
- Bun has API parity with Node via direct FFI to `libdoe_webgpu` (57/57
  contract tests passing). Cube maturity remains prototype until Bun cells
  are populated by comparable benchmark artifacts.
- Package-surface comparisons should be read through the benchmark cube outputs
  under `bench/out/cube/`, not as a replacement for strict backend reports.

## Quickstart

```bash
npm install @simulatte/webgpu
```

```js
import { providerInfo, requestDevice } from "@simulatte/webgpu";

console.log(providerInfo());

const device = await requestDevice();
console.log(device.limits.maxBufferSize);
```

Turnkey package install is the target shape. Current host/runtime caveats are
listed below.

## From Source

```bash
# From the Fawn workspace root:
cd zig && zig build dropin   # build libdoe_webgpu + Dawn sidecar

cd nursery/webgpu
npm run build:addon          # compile doe_napi.node from source
npm run smoke                # verify native loading + GPU round-trip
```

Use this when working from the Fawn checkout or when rebuilding the addon
against the local Doe runtime.

### Packaging prebuilds (CI / release)

```bash
npm run prebuild             # assembles prebuilds/<platform>-<arch>/
```

Supported prebuild targets: macOS arm64 (Metal), Linux x64 (Vulkan),
Windows x64 (D3D12). Host GPU drivers are the only external prerequisite.
Install uses prebuilds when available, falls back to node-gyp from source.

## What Lives Here

- `src/index.js`: default Node provider entrypoint
- `src/node-runtime.js`: compatibility alias for the Node entrypoint
- `src/bun-ffi.js`: Bun FFI provider (full API parity with Node)
- `src/bun.js`: Bun re-export entrypoint
- `src/runtime_cli.js`: Doe CLI/runtime helpers
- `native/doe_napi.c`: N-API bridge for the in-process Node provider
- `binding.gyp`: addon build contract
- `bin/fawn-webgpu-bench.js`: command-stream bench wrapper
- `bin/fawn-webgpu-compare.js`: Dawn-vs-Doe compare wrapper

## Current Caveats

- This package is for headless benchmarking and CI workflows, not full browser
  parity.
- Node provider comparisons are package/runtime evidence. Backend claim lanes
  remain the canonical performance evidence path.
- Linux Node Doe-native path is now wired end-to-end (Linux guard removed).
  No `DOE_WEBGPU_LIB` env var needed when prebuilds or workspace artifacts
  are present.
- Bun has API parity with Node (57/57 contract tests). Bun benchmark lane
  is at `bench/bun/compare.js` and compares Doe FFI against the `bun-webgpu`
  package. Latest validated run shows 7/11 claimable (compute e2e rows
  comparable + claimable after readback validation added to the timed path).
  Benchmark cube policy now isolates directional `compute_dispatch_simple`
  into a dispatch-only cell so the Bun compute-e2e cube cell reflects the
  claimable end-to-end rows. `buffer_map_write_unmap` remains slower
  (~19µs polling overhead).
  Cube maturity remains prototype until cell coverage stabilizes.
- Self-contained install ships prebuilt `doe_napi.node` + `libdoe_webgpu` +
  Dawn sidecar per platform. Clean-machine smoke test: `npm run smoke`.
- API details live in `API_CONTRACT.md`.
- Compatibility scope is documented in `COMPAT_SCOPE.md`.
