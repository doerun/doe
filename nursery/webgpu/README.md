# @simulatte/webgpu

Canonical WebGPU package for browserless benchmarking, CI workflows, and
headless runtime integration.

<p align="center">
  <img src="https://raw.githubusercontent.com/clocksmith/fawn/main/nursery/webgpu/assets/fawn-icon-main-256.png" alt="Fawn logo" width="196" />
</p>

It is built on Doe, Fawn's Zig WebGPU runtime and Dawn-replacement path for
Fawn/Chromium. Doe uses Zig for explicit low-overhead systems paths, explicit
allocator control, and keeping hot runtime paths minimal across
Vulkan/Metal/D3D12 backends. Optional `-Dlean-verified=true` builds use Lean 4
where proved invariants can be hoisted out of runtime branches instead of being
re-checked on every command; package consumers should not assume that path by
default.

Doe also keeps adapter and driver quirks explicit. Profile selection happens at
startup, quirk data is schema-backed, and the runtime binds the selected
profile instead of relying on hidden per-command fallback logic.

In this package, Node uses an N-API addon and Bun uses Bun FFI to load
`libwebgpu_doe`. Current package builds still ship a Dawn sidecar where proc
resolution requires it.

This directory is the package root for `@simulatte/webgpu`. It contains the
Node provider source, the addon build contract, the Bun FFI entrypoint, and
the CLI helpers used by benchmark and CI workflows.

## Surface maturity

- Node is the primary supported package surface (N-API bridge).
- Bun has API parity with Node via direct FFI to `libwebgpu_doe` (57/57
  contract tests passing). Bun benchmark cube maturity remains prototype
  until Bun cells are populated by comparable benchmark artifacts.
- Package-surface comparisons should be read through the benchmark cube outputs
  under `bench/out/cube/`, not as a replacement for strict backend reports.

The **benchmark cube** is a cross-product matrix of surface (backend_native,
node_package, bun_package) × provider pair (e.g. doe_vs_dawn) × workload set
(e.g. compute_e2e, render, upload). Each intersection is a **cell** with its
own comparability and claimability status. Cube outputs live in
`bench/out/cube/` and include a dashboard, matrix summary, and per-row data.

<p align="center">
  <img src="https://raw.githubusercontent.com/clocksmith/fawn/main/nursery/webgpu/assets/package-surface-cube-snapshot.svg" alt="Static package-surface benchmark cube snapshot" width="920" />
</p>

Static snapshot above:

- source: `bench/out/cube/latest/cube.summary.json`
- renderer: `npm run build:readme-assets`
- scope: package surfaces only; backend-native strict claim lanes remain separate

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

## From source

```bash
# From the Fawn workspace root:
cd zig && zig build dropin   # build libwebgpu_doe + Dawn sidecar

cd nursery/webgpu
npm run build:addon          # compile doe_napi.node from source
npm run smoke                # verify native loading + GPU round-trip
```

Use this when working from the Fawn checkout or when rebuilding the addon
against the local Doe runtime.

## Packaging prebuilds (CI / release)

```bash
npm run prebuild             # assembles prebuilds/<platform>-<arch>/
```

Supported prebuild targets: macOS arm64 (Metal), Linux x64 (Vulkan),
Windows x64 (D3D12). Host GPU drivers are the only external prerequisite.
Install uses prebuilds when available, falls back to node-gyp from source.
Prebuild `metadata.json` now records `doeBuild.leanVerifiedBuild` and
`proofArtifactSha256`, and `providerInfo()` surfaces the same values when
metadata is present.

## What lives here

- `src/index.js`: default Node provider entrypoint
- `src/node-runtime.js`: compatibility alias for the Node entrypoint
- `src/bun-ffi.js`: Bun FFI provider (full API parity with Node)
- `src/bun.js`: Bun re-export entrypoint
- `src/runtime_cli.js`: Doe CLI/runtime helpers
- `native/doe_napi.c`: N-API bridge for the in-process Node provider
- `binding.gyp`: addon build contract
- `bin/fawn-webgpu-bench.js`: command-stream bench wrapper
- `bin/fawn-webgpu-compare.js`: Dawn-vs-Doe compare wrapper

## Current caveats

- This package is for headless benchmarking and CI workflows, not full browser
  parity.
- Node provider comparisons are host-local package/runtime evidence measured
  with package-level timers. They are useful surface-positioning data, not
  backend claim substantiation or a broad "the package is faster" claim.
- `@simulatte/webgpu` does not yet have a single broad cross-surface speed
  claim. Current performance evidence is split across Node package-surface
  runs, prototype Bun package-surface runs, and workload-specific strict
  backend reports.
- Linux Node Doe-native path is now wired end-to-end (Linux guard removed).
  No `DOE_WEBGPU_LIB` env var needed when prebuilds or workspace artifacts
  are present.
- Bun has API parity with Node (57/57 contract tests). Bun benchmark lane
  is at `bench/bun/compare.js` and compares Doe FFI against the `bun-webgpu`
  package. Latest validated local run observed 7/11 claimable rows, but this
  remains prototype-quality package-surface evidence rather than a
  publication-grade performance claim. Benchmark cube policy now isolates
  directional `compute_dispatch_simple` into a dispatch-only cell so the Bun
  compute-e2e cube cell reflects the claimable end-to-end rows.
  `buffer_map_write_unmap` remains slower (~19µs polling overhead). Cube
  maturity remains prototype until cell coverage stabilizes.
- Self-contained install ships prebuilt `doe_napi.node` + `libwebgpu_doe` +
  Dawn sidecar per platform. Clean-machine smoke test: `npm run smoke`.
- API details live in `API_CONTRACT.md`.
- Compatibility scope is documented in `COMPAT_SCOPE.md`.
