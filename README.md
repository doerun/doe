# Doe

<p align="center">
  <img src="https://raw.githubusercontent.com/doe-gpu/doe/main/assets/doe-logo.svg" alt="Doe logo" width="96" />
</p>

Doe is a source-preserving accelerator runtime and compiler system: it keeps
shader/program bodies visible, lowers them across execution targets, and
produces receipts that prove what ran.

In practice that means embedding where Dawn is too heavy, lowering kernels to
multiple GPU and spatial backends from the same IR, and emitting artifact-
backed receipts that bind every claim to a specific build.

Published npm surface: [`packages/doe-gpu/README.md`](packages/doe-gpu/README.md).

## Tenants

The repo carries five tenants under that umbrella:

| Tenant | Role |
|---|---|
| Dawn replacement (Zig WebGPU runtime) | runtime tenant; embeddable WebGPU runtime details in [`docs/thesis.md`](docs/thesis.md). |
| Vulkan / Metal / D3D12 emitters | backend tenant; multi-target lowering from the WGSL compiler (`runtime/zig/src/doe_wgsl/`). |
| Cerebras (TSIR / HostPlan / CSL) | spatial retargeting tenant; Tiled Spatial IR plus host-plan and CSL emit (`runtime/zig/src/tsir/`, `runtime/zig/src/doe_wgsl/emit_csl_*`). |
| Lean proof pipeline | verification tenant; proof-eliminated runtime branches and verified artifacts (`pipeline/lean/`). |
| Benchmarks and evidence bundles | proof tenant; claim-discipline gates, parity receipts, hardware-validation bundles (`bench/`). |

Same discipline applied to different targets: shader/program bodies stay
visible, lowering preserves identity, and every claim has a receipt path.

## Why Doe

- Lean runtime story: a Zig runtime with a small package layer instead of
  treating Chromium's in-tree Dawn stack as the default deployment model.
- Explicit behavior: no silent fallback, explicit runtime boundaries, and
  artifact-backed benchmarking instead of hand-wavy claims.
- Performance work with receipts: current results live in
  [`docs/status.md`](docs/status.md) and `bench/out/*`.

## Current evidence

These charts summarize the current public benchmark lanes. A positive percent means Doe finished faster than the comparison runtime (Dawn).

![Doe package benchmark claims](assets/readme/package-claims.svg)

Outputs:
- Node package, AMD Vulkan: [benchmark output](bench/out/amd-vulkan/20260410T235522Z/gemma270m.node-package.ir.compare.json)
- Bun package, AMD Vulkan: [benchmark output](bench/out/amd-vulkan/20260410T235541Z/gemma270m.bun-package.ir.compare.json)
- Node package, Apple Metal: [benchmark output](bench/out/apple-metal/20260414T010826Z/gemma64.node-package.warm.ir.compare.json)
- Bun package, Apple Metal: [benchmark output](bench/out/apple-metal/20260414T010736Z/gemma64.bun-package.warm.ir.compare.json)

## Additional benchmark outputs

Additional benchmark outputs also exist for ONNX Runtime (ORT) and broader compare surfaces.

![Doe ORT benchmark claims](assets/readme/ort-claims.svg)

Outputs:
- Native ORT, AMD Vulkan: [benchmark output](bench/out/native-ort-webgpu-provider/20260413T175708Z/basic-ops.compare.json) / [benchmark output](bench/out/native-ort-webgpu-provider/20260413T175708Z/basic-ops.claim.json)
- Node ORT, AMD Vulkan: [benchmark output](bench/out/node-ort-webgpu-provider-compare/20260413T191817Z/gemma270m.compare.json) / [benchmark output](bench/out/node-ort-webgpu-provider-compare/20260413T191817Z/gemma270m.claim.json)
- Bun ORT, AMD Vulkan: [benchmark output](bench/out/bun-ort-webgpu-provider-compare/gemma270m-prefill32-decode1.compare.json) / [benchmark output](bench/out/bun-ort-webgpu-provider-compare/gemma270m-prefill32-decode1.claim.json)
- Node ORT, Apple Metal: [benchmark output](bench/out/apple-metal-ort-node/20260415T005827Z/gemma270m.compare.json)
- Bun ORT, Apple Metal: [benchmark output](bench/out/apple-metal-ort-bun/20260415T005827Z/gemma270m-prefill32-decode1.compare.json)

## Current product surface

- Competitive today: native, package, embedded, and server-side JavaScript
  lanes.
- `doe-gpu/browser` is a browser shim over the browser's incumbent WebGPU
  implementation. Chromium replacement work lives under the experimental
  `browser/chromium/` lane.
- [`browser/chromium/`](browser/chromium/README.md) is an experimental future
  lane outside the current product surface.

## Start here

- Package consumers: [`packages/doe-gpu/README.md`](packages/doe-gpu/README.md)
- Runtime contributors: [`runtime/zig/README.md`](runtime/zig/README.md)
- Benchmarks and evidence: [`bench/README.md`](bench/README.md)
- Current status and claim boundaries: [`docs/status.md`](docs/status.md)
- Doppler Program Bundle ingest: [`docs/doppler-ingest.md`](docs/doppler-ingest.md)
- Cerebras lane (Doppler → Doe → Cerebras):
  [`docs/cerebras.md`](docs/cerebras.md). Progress, source, reproduce,
  hardware runbook, rationale.
- TSIR (Tiled Spatial IR) compiler work:
  [`docs/tsir-lowering-plan.md`](docs/tsir-lowering-plan.md),
  [`docs/loop-protocol.md`](docs/loop-protocol.md), live status at
  [`docs/status/tsir.md`](docs/status/tsir.md)
- Project rationale and boundaries: [`docs/thesis.md`](docs/thesis.md),
  [`docs/architecture.md`](docs/architecture.md),
  [`docs/process.md`](docs/process.md)
- Proof and trace pipeline: [`pipeline/lean/README.md`](pipeline/lean/README.md),
  [`pipeline/trace/README.md`](pipeline/trace/README.md),
  [`pipeline/agent/README.md`](pipeline/agent/README.md)

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

That smoke path checks load and export wiring without requiring a GPU.

## Legacy package names

These legacy package names are deprecated in favor of `doe-gpu`:

- `@simulatte/webgpu`
- `@simulatte/webgpu-doe`

## License

See [`docs/licensing.md`](docs/licensing.md).
