# Doe

<p align="center">
  <img src="https://raw.githubusercontent.com/doe-gpu/doe/main/assets/doe-logo.svg" alt="Doe logo" width="96" />
</p>

Doe is a Zig-first WebGPU runtime for places where you cannot or do not want to
ship Dawn.

It is built to be lean, explicit, and fast. The repo combines the runtime, the
`doe-gpu` package surface, artifact-backed benchmark workflows, and the proof
and trace pipeline used to keep claims narrow and auditable.

If you want the published npm surface, start with
[`packages/doe-gpu/README.md`](packages/doe-gpu/README.md).

## Why Doe

- Lean runtime story: a Zig runtime with a small package layer instead of
  treating Chromium's in-tree Dawn stack as the default deployment model.
- Explicit behavior: no silent fallback, explicit runtime boundaries, and
  artifact-backed benchmarking instead of hand-wavy claims.
- Performance work with receipts: current results live in
  [`docs/status.md`](docs/status.md) and `bench/out/*`, not in prose.

## What we can claim today

Ready to claim means strict apples-to-apples evidence that is safe to cite.

| What | Platform | Status | Result | Proof |
| --- | --- | --- | --- | --- |
| Node package | AMD Vulkan | Ready to claim | Doe faster | [artifact](bench/out/amd-vulkan/20260410T235522Z/gemma270m.node-package.ir.compare.json) |
| Bun package | AMD Vulkan | Ready to claim | Doe faster | [artifact](bench/out/amd-vulkan/20260410T235541Z/gemma270m.bun-package.ir.compare.json) |
| Node package | Apple Metal | Ready to claim | Doe faster | [compare](bench/out/apple-metal/20260413T214410Z/gemma64.node-package.warm.ir.compare.json) / [claim](bench/out/apple-metal/20260413T214410Z/gemma64.node-package.warm.ir.claim.json) |
| Bun package | Apple Metal | Ready to claim | Doe faster | [compare](bench/out/apple-metal/20260413T214446Z/gemma64.bun-package.warm.ir.compare.json) / [claim](bench/out/apple-metal/20260413T214446Z/gemma64.bun-package.warm.ir.claim.json) |

## What is still experimental

Mixed results means real evidence exists, but not a broad win. Internal
benchmark means the evidence is useful and governed, but it is not a package
promise.

| What | Platform | Status | Result | Proof |
| --- | --- | --- | --- | --- |
| Native ORT | AMD Vulkan | Internal benchmark | Doe faster | [compare](bench/out/native-ort-webgpu-provider/20260413T175708Z/basic-ops.compare.json) / [claim](bench/out/native-ort-webgpu-provider/20260413T175708Z/basic-ops.claim.json) |
| Node ORT | AMD Vulkan | Internal benchmark | Doe faster | [compare](bench/out/node-ort-webgpu-provider-compare/20260413T191817Z/gemma270m.compare.json) / [claim](bench/out/node-ort-webgpu-provider-compare/20260413T191817Z/gemma270m.claim.json) |
| Bun ORT | AMD Vulkan | Internal benchmark | Doe faster | [compare](bench/out/bun-ort-webgpu-provider-compare/gemma270m-prefill32-decode1.compare.json) / [claim](bench/out/bun-ort-webgpu-provider-compare/gemma270m-prefill32-decode1.claim.json) |
| Browser ORT | Linux browser | Mixed results | Mixed | [artifact](bench/out/browser-ort-webgpu-compare/20260413T193605Z/browser.compare.json) |

Coverage snapshot:

| What | AMD Vulkan | Apple Metal |
| --- | --- | --- |
| Node package | Claimable win | Claimable win |
| Bun package | Claimable win | Claimable win |
| Native ORT | Internal benchmark | Not front-doored |
| Node ORT | Internal benchmark | Not front-doored |
| Bun ORT | Internal benchmark | Not front-doored |
| Browser ORT | Mixed | Not front-doored |

## Current product surface

- Competitive today: native, package, embedded, and server-side JavaScript
  lanes.
- `doe-gpu/browser` is a browser shim over the browser's incumbent WebGPU
  implementation. It is not the Chromium replacement story.
- [`browser/chromium/`](browser/chromium/README.md) is an experimental future
  lane, not the front-door product surface.

## Start here

- Package consumers: [`packages/doe-gpu/README.md`](packages/doe-gpu/README.md)
- Runtime contributors: [`runtime/zig/README.md`](runtime/zig/README.md)
- Benchmarks and evidence: [`bench/README.md`](bench/README.md)
- Current status and claim boundaries: [`docs/status.md`](docs/status.md)
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

That smoke path checks load and export wiring. It does not require a GPU.

## Legacy package names

These legacy package names are deprecated in favor of `doe-gpu`:

- `@simulatte/webgpu`
- `@simulatte/webgpu-doe`

## License

See [`docs/licensing.md`](docs/licensing.md).
