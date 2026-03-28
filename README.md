# Doe

<p align="center">
  <img src="assets/doe-logo.svg" alt="Doe logo" width="96" />
</p>

Doe is a Zig-first WebGPU runtime built as an explicit, performance-oriented
alternative to Dawn.

This repo contains the runtime, the `doe-gpu` package surface, benchmarking and
gate tooling, proof artifacts, trace/replay tooling, and the Chromium browser
lane. If you want the published package surface, start with
[`packages/doe-gpu/README.md`](packages/doe-gpu/README.md).

## Start here

- Package consumers: [`packages/doe-gpu/README.md`](packages/doe-gpu/README.md)
- Runtime contributors: [`runtime/zig/README.md`](runtime/zig/README.md)
- Benchmarking and gates: [`bench/README.md`](bench/README.md)
- Browser lane: [`browser/chromium/README.md`](browser/chromium/README.md)
- Proof and pipeline work: [`pipeline/lean/README.md`](pipeline/lean/README.md), [`pipeline/trace/README.md`](pipeline/trace/README.md), [`pipeline/agent/README.md`](pipeline/agent/README.md)
  Current Lean theorem inventory: [`pipeline/lean/artifacts/proven-conditions.json`](pipeline/lean/artifacts/proven-conditions.json)
- Public vs repo-only tooling boundary: [`docs/internal-tooling.md`](docs/internal-tooling.md)

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
