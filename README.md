# Doe

<p align="center">
  <img src="assets/doe-logo.svg" alt="Doe logo" width="96" />
</p>

Doe is a Zig-first WebGPU runtime built as an explicit, performance-oriented
alternative to Dawn.

This repo contains the runtime, package surfaces, browser integration work,
proof pipeline, trace tooling, and benchmarking infrastructure. If you want the
published package surface, start with
[`packages/doe-gpu/README.md`](packages/doe-gpu/README.md).

## Start here

Pick the README that matches the surface you are touching.

- Package consumers:
  [`packages/doe-gpu/README.md`](packages/doe-gpu/README.md)
- Internal operator tooling:
  [`docs/internal-tooling.md`](docs/internal-tooling.md)
- Runtime contributors:
  [`runtime/zig/README.md`](runtime/zig/README.md)
- Benchmarking, comparability, and claim gates:
  [`bench/README.md`](bench/README.md)
- Browser integration:
  [`browser/chromium/README.md`](browser/chromium/README.md)
- Proof and pipeline work:
  [`pipeline/lean/README.md`](pipeline/lean/README.md),
  [`pipeline/trace/README.md`](pipeline/trace/README.md),
  [`pipeline/agent/README.md`](pipeline/agent/README.md)

## Repo layout

- [`runtime/zig`](runtime/zig/README.md): runtime, WGSL pipeline, and native
  backend execution paths
- [`packages/doe-gpu`](packages/doe-gpu/README.md): npm package surface
- [`bench`](bench/README.md): Dawn-vs-Doe comparison harnesses, gates, and
  evidence workflows
- [`browser/chromium`](browser/chromium/README.md): Chromium-oriented
  integration and browser tracks
- [`pipeline/lean`](pipeline/lean/README.md): proof artifacts and proof-driven
  elimination pipeline
- [`pipeline/trace`](pipeline/trace/README.md): deterministic trace and replay
  tooling
- [`pipeline/agent`](pipeline/agent/README.md): quirk mining and normalization

## Design direction

Doe keeps runtime behavior explicit:

- native backend paths instead of opaque bridge layers
- config-first policy and schema-backed behavior
- optional Lean-backed proof elimination at build time, not a runtime proof
  interpreter
- replayable benchmark artifacts instead of prose-only claims

## Current status

Doe currently targets Vulkan, Metal, and D3D12. It is intentionally focused on
modern GPU APIs and modern workloads rather than broad legacy-backend coverage.

For current status, process, and performance policy, use:

- [`docs/status.md`](docs/status.md)
- [`docs/process.md`](docs/process.md)
- [`docs/performance-strategy.md`](docs/performance-strategy.md)

Package-surface results are tracked separately from backend-native Dawn-vs-Doe
evidence.

## Quick start

For package install and JS usage, use
[`packages/doe-gpu/README.md`](packages/doe-gpu/README.md).

For local runtime work:

```bash
cd runtime/zig
zig build test
zig build dropin
```

Doe currently requires Zig 0.15.2. See
[`config/toolchains.json`](config/toolchains.json).

For benchmark, compare, and gate workflows, use
[`bench/README.md`](bench/README.md) instead of treating this README as the
operational guide.

## Deprecated packages

The following packages are deprecated and replaced by `doe-gpu`:

- `@simulatte/webgpu`
- `@simulatte/webgpu-doe`

## More docs

- [`docs/thesis.md`](docs/thesis.md): project thesis and framing
- [`docs/architecture.md`](docs/architecture.md): system overview
- [`docs/internal-tooling.md`](docs/internal-tooling.md): public vs repo-only tooling boundary
- [`docs/process.md`](docs/process.md): stage order, gates, and release policy
- [`docs/status.md`](docs/status.md): current status and tracked follow-ups

## License

See [`docs/licensing.md`](docs/licensing.md).
