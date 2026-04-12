# Doe

<p align="center">
  <img src="assets/doe-logo.svg" alt="Doe logo" width="96" />
</p>

Doe is a Zig-first WebGPU runtime built as an explicit, performance-oriented
challenger to Dawn.

This repo contains the runtime, the `doe-gpu` package surface, benchmarking and
gate tooling, proof artifacts, trace/replay tooling, and an experimental
Chromium browser lane. If you want the published package surface, start with
[`packages/doe-gpu/README.md`](packages/doe-gpu/README.md).

Dawn remains the incumbent browser runtime in Chromium today. Doe's immediate
competitive ground is narrower: package, embedded, native, and server-side
JavaScript lanes where shipping Dawn is undesirable or too costly.

## Start here

- Package consumers: [`packages/doe-gpu/README.md`](packages/doe-gpu/README.md)
- Runtime contributors: [`runtime/zig/README.md`](runtime/zig/README.md)
- Benchmarking and gates: [`bench/README.md`](bench/README.md)
- Browser lane: [`browser/chromium/README.md`](browser/chromium/README.md)
- Proof and pipeline work: [`pipeline/lean/README.md`](pipeline/lean/README.md), [`pipeline/trace/README.md`](pipeline/trace/README.md), [`pipeline/agent/README.md`](pipeline/agent/README.md)
  Current Lean theorem inventory: [`pipeline/lean/artifacts/proven-conditions.json`](pipeline/lean/artifacts/proven-conditions.json)
- Public vs repo-only tooling boundary: [`docs/internal-tooling.md`](docs/internal-tooling.md)

## Package layer stack

```text
Application code
┌─────────────────────────────────────────────────────────────────┐
│ Your app / script / CLI / worker / web page                     │
│ imports from doe-gpu                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
doe-gpu package boundary
┌─────────────────────────────────────────────────────────────────┐
│ Package exports                                                 │
│ doe-gpu · doe-gpu/compute · doe-gpu/browser · doe-gpu/hybrid    │
├─────────────────────────────────────────────────────────────────┤
│ Doe API helpers                                                 │
│ doe.requestDevice · doe.bind · gpu.buffer.* · gpu.kernel.*      │
├─────────────────────────────────────────────────────────────────┤
│ Shared WebGPU JS object model and validation                    │
│ src/vendor/webgpu/shared/full-surface.js                        │
│ src/vendor/webgpu/shared/encoder-surface.js                     │
│ src/vendor/webgpu/shared/validation.js                          │
└─────────────────────┬───────────────────────────────────────────┘
                      │
        ┌─────────────┴──────────────┐
        │                            │
        ▼                            ▼
 Headless native path       Browser wrapper path
 (Node.js / Bun / Deno)     (web page)
┌──────────────────────┐   ┌──────────────────────────────┐
│ N-API addon          │   │ src/browser.js               │
│ (doe_napi.node)      │   │ wraps browser-native WebGPU  │
│ or Bun FFI bridge    │   │ objects behind doe-gpu       │
│ (src/vendor/webgpu/  │   │ classes.                     │
│ bun-ffi.js via       │   │                              │
│ src/bun.js)          │   │                              │
└──────────┬───────────┘   └──────────────┬───────────────┘
           │                              │
           ▼                              ▼
 Doe Zig runtime              Browser-native WebGPU
┌──────────────────────┐   ┌──────────────────────────────┐
│ doe_*.zig native ABI │   │ The browser's built-in       │
│ WGSL compiler        │   │ WebGPU implementation        │
│ (doe_wgsl)           │   │ (Dawn in Chrome, wgpu in     │
│ Metal / Vulkan /     │   │ Firefox, etc.)               │
│ D3D12 backends       │   │ No Doe code runs here.       │
└──────────┬───────────┘   └──────────────┬───────────────┘
           │                              │
           ▼                              ▼
    OS GPU APIs                   Browser GPU sandbox
    + physical GPU                + physical GPU
```

The two paths share the same JS object model and validation layer but diverge
at the transport boundary:

- **Headless native** — N-API or the Bun runtime path calls into the Doe Zig
  runtime, which drives Metal/Vulkan/D3D12 directly. On Linux the Bun path
  uses `src/vendor/webgpu/bun-ffi.js`. This is where Doe's WGSL compiler,
  backend execution, and proof-aware branch elimination run.
- **Browser wrapper** — `src/browser.js` wraps browser-native WebGPU objects
  behind Doe surface classes. No Zig code runs; the browser's WebGPU
  implementation (typically Dawn) handles GPU work. The wrapper exists so that
  code written against `doe-gpu` can run in a browser without modification.

Neither path is related to the Chromium integration lane
(`browser/chromium/`), which is a separate future effort to test whether the
Doe Zig runtime could replace Dawn inside Chromium. That browser lane is not
the current product center and should not be confused with the present package
or native runtime surfaces.

## Zig runtime dependency graph

```text
┌──────────────────────────────────────────────────────────────────┐
│ Entry points                                                     │
│ main.zig          wgpu_dropin_lib.zig     main_emit_msl.zig     │
│ (CLI runtime)     (C ABI drop-in)         (shader tool)          │
│                   csl_bundle_emitter.zig                         │
│                   main_doe_plan_executor.zig                     │
│                   main_webgpu_plan_executor.zig                    │
└──────────────────────────┬───────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌──────────────────────┐  ┌──────────────────────────────────────┐
│ execution.zig        │  │ quirk/                               │
│ mode switching       │  │ mod.zig  runtime.zig  quirk_json.zig │
│ (trace / native)     │  │ quirk_actions.zig                    │
│                      │  │ toggle_registry.zig                  │
└──────────┬───────────┘  └──────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ backend/                                                         │
│ backend_runtime.zig  backend_iface.zig (vtable)                  │
│ backend_registry.zig backend_selection.zig backend_policy.zig    │
└──────────┬───────────────────────────────────────────────────────┘
           │
           ├──────────────────┬──────────────────┐
           ▼                  ▼                  ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│ metal/         │  │ vulkan/        │  │ d3d12/         │
│ ZigMetalBackend │ │ ZigVulkanBackend│ │ ZigD3D12Backend │
│ + ObjC bridges  │  │ + Vulkan bridge │ │ + C bridge      │
└───────┬────────┘  └───────┬────────┘  └───────┬────────┘
        │                   │                    │
        └───────────────────┼────────────────────┘
                            │
              each backend dispatches into BOTH:
                            │
           ┌────────────────┴────────────────┐
           ▼                                 ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│ core/                   │   │ full/                   │
│ command_dispatch.zig    │   │ command_dispatch.zig    │
│                         │   │                         │
│ compute/  (dispatch)    │   │ render/  (draw calls)   │
│ resource/ (buffer/tex)  │   │ surface/ (presentation) │
│ queue/    (FFI sync)     │   │ lifecycle/ (surface +    │
│ replay/   (hash-chain)   │   │ async diagnostics)       │
│ trace/    (metadata)     │   │ modules/  (services)     │
│ abi/      (WebGPU ABI)   │   │                          │
│ surface.zig (core-only   │   │                          │
│ surface API)             │   │                          │
└────────────┬────────────┘   └────────────┬────────────┘
             │                              │
             └──────────┬───────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ model_commands.zig                                               │
│ Command = CoreCommand ∪ FullCommand  (comptime-verified)         │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ model_*.zig  (split leaf contracts + compatibility barrels)      │
└──────────────────────────────────────────────────────────────────┘

 Parallel concern (shared by backends, not layered):
┌──────────────────────────────────────────────────────────────────┐
│ doe_wgsl/  (WGSL compiler)                                       │
│ lexer → parser → sema → ir_builder → ir_validate                │
│    → emit_msl / emit_spirv / emit_hlsl / emit_dxil / emit_csl  │
└──────────────────────────────────────────────────────────────────┘
```

`core/` and `full/` are a **command partition**, not layers. `core/` owns
compute, copy, and resource commands; `full/` owns render, surface, and
lifecycle commands. Each backend receives the unified `Command` union and
dispatches into whichever partition matches. The split is enforced at comptime
in `model_commands.zig` and by an import fence
(`runtime/zig/tools/check_core_import_fence.py`: `core/` cannot import `full/`).

## Repo layout

- [`runtime/zig`](runtime/zig/README.md): Doe runtime, WGSL pipeline, and native backends
- [`packages/doe-gpu`](packages/doe-gpu/README.md): npm package surface
- [`bench`](bench/README.md): compare harnesses, gates, and evidence workflows
- [`browser/chromium`](browser/chromium/README.md): Chromium integration docs, probes, and lane scripts
- [`pipeline`](pipeline/README.md): quirk mining, proofs, trace, and supporting pipeline modules

## Quick start

Requirements:

- Zig 0.15.2
- Node.js 18+

```bash
git clone https://github.com/doe-gpu/doe.git
cd doe
zig build dropin
node packages/doe-gpu/scripts/build-addon.js
node packages/doe-gpu/test/smoke/test-smoke-load.js
```

Expected output ends with:

```text
Results: <n> passed, 0 failed
```

That smoke path checks export/load wiring and does not require a GPU.

## Current scope

Doe currently targets Metal, Vulkan, and D3D12. Package-surface results are
tracked separately from backend-native Dawn-vs-Doe evidence.

For current status and policy, use:

- [`docs/status.md`](docs/status.md)
- [`docs/process.md`](docs/process.md)
- [`docs/performance-strategy.md`](docs/performance-strategy.md)

## Key docs

- [`docs/thesis.md`](docs/thesis.md): project rationale
- [`docs/architecture.md`](docs/architecture.md): system boundaries and surfaces
- [`docs/compare-taxonomy.md`](docs/compare-taxonomy.md): compare-axis language
- [`docs/licensing.md`](docs/licensing.md): licensing and third-party usage

## Deprecated package names

These legacy package names are deprecated in favor of `doe-gpu`:

- `@simulatte/webgpu`
- `@simulatte/webgpu-doe`

## License

See [`docs/licensing.md`](docs/licensing.md).
