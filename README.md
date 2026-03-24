# Doe

Doe is a Zig-first WebGPU runtime built as an explicit, performance-oriented
alternative to Dawn.

If you want to use the published package:

- [`doe-gpu`](packages/doe-gpu/README.md): WebGPU for Node.js, Bun, and Deno,
  with the Doe runtime and Doe helper API

```js
import { gpu } from 'doe-gpu';           // full (default)
import { gpu } from 'doe-gpu/compute';   // compute-only
import { gpu } from 'doe-gpu/browser';   // browser shim
```

If you are working on the runtime itself, this repo carries the runtime, package
surfaces, browser bring-up, proof artifacts, tracing, and benchmarking.

## What this repo contains

- [`runtime/zig`](runtime/zig/README.md): the Doe runtime, WGSL pipeline, and
  native backend execution paths
- [`packages/doe-gpu`](packages/doe-gpu/README.md): the npm package for
  headless WebGPU
- [`browser/chromium`](browser/chromium/README.md): browser-owned and
  Chromium-oriented integration work
- [`pipeline/agent`](pipeline/agent/README.md): quirk mining and normalization
- [`pipeline/lean`](pipeline/lean/README.md): proof artifacts that can remove
  runtime checks ahead of time
- [`pipeline/trace`](pipeline/trace/README.md): reproducible trace and replay
  tooling
- [`bench`](bench/README.md): Dawn-vs-Doe comparison harnesses and artifacts

## Project split by feature, backend, and packaging

See [runtime/zig/README.md](runtime/zig/README.md), and this package mapping:

- API surface split (`compute`/`headless`/`full`) is defined in the runtime build system and runtime surface docs.
- Backend routing (`metal`/`vulkan`/`d3d12`) is documented in backend architecture docs and source.
- Package entrypoint split is documented in:
  - [doe-gpu package README](packages/doe-gpu/README.md)
  - package exports in [doe-gpu package.json](packages/doe-gpu/package.json)

## Why Doe

Doe is built around a simple split: checks that can be resolved ahead of time
should move out of the hot path, and the checks that must stay live should stay
explicit in the runtime.

That shows up in a few project-wide choices:

- explicit native backend paths instead of opaque bridge layers
- config-first policy and schema-backed behavior
- optional Lean-backed proof elimination at build time, not a runtime proof
  interpreter
- benchmark claims grounded in replayable artifacts instead of prose summaries

## Current status

Doe currently targets Vulkan, Metal, and D3D12. It is intentionally focused on
modern GPU APIs and modern workloads rather than broad legacy-backend coverage.

Benchmarking and claim discipline are important here, but the repo README is not
the right place for artifact-by-artifact inventory. The current ground truth
lives in:

- [`docs/status.md`](docs/status.md)
- [`docs/process.md`](docs/process.md)
- [`docs/performance-strategy.md`](docs/performance-strategy.md)
- [`bench/out/`](bench/out/)

One distinction matters up front: package-surface results are not treated as a
substitute for backend-native Dawn-vs-Doe evidence. Those lanes are tracked
separately.

## Working in the repo

Pick the README that matches the surface you are touching.

For package consumers:

- use [`packages/doe-gpu/README.md`](packages/doe-gpu/README.md)

For runtime contributors:

- start with [`runtime/zig/README.md`](runtime/zig/README.md)
- then read [`bench/README.md`](bench/README.md) if your change affects
  performance or comparability

## Validation clusters and preferred order

When changes affect runtime behavior and performance claims, use this cluster order:

1. Runtime correctness tests (`runtime/zig/tests`) via [`runtime/zig/README.md`](runtime/zig/README.md).
2. Benchmark and comparison harnesses (native/package/drop-in/diagnostic) in [`bench/README.md`](bench/README.md).
3. Claim and comparability gates in [`bench/README.md`](bench/README.md) (blocking/release gate cluster).
4. Pipeline and generated-artifact tests:
   [`pipeline/agent/test_mine_quirks.py`](pipeline/agent/test_mine_quirks.py),
   [`pipeline/trace/test_trace_tools.py`](pipeline/trace/test_trace_tools.py),
   Lean pipeline tests in [`pipeline/lean`](pipeline/lean/README.md).
5. Browser tracks (`browser/chromium`):
   smoke, projection, and browser-gate workflows are in
   [`browser/chromium/README.md`](browser/chromium/README.md) and stay separate
   from native/package claim lanes.

This order keeps the repo moving from implementation correctness → performance claim
production → proof/instrumentation validation → browser evidence.

Suggested command surface:

1) Runtime correctness tests

```bash
cd runtime/zig
zig build test
```

2) Benchmarks and comparison harnesses (native/package/drop-in/diagnostic)

```bash
python3 bench/native-compare/compare_dawn_vs_doe.py --help
python3 bench/run_bench.py --help
python3 bench/package-compare/node/compare.js --help
```

3) Claim and comparability gates

```bash
python3 bench/run_blocking_gates.py --help
```

4) Pipeline and generated-artifact tests

```bash
python3 -m pytest \
  pipeline/agent/test_mine_quirks.py \
  pipeline/trace/test_trace_tools.py \
  pipeline/lean/test_proof_pipeline.py \
  pipeline/lean/test_lean_source.py
```

5) Browser tracks (preflight + smoke/bench)

```bash
python3 browser/chromium/scripts/run-smoke.sh --help
python3 bench/browser/browser_gate.py --help
```

Evidence cube (optional, run after comparable report generation)

```bash
python3 bench/build_benchmark_cube.py --report-glob "bench/out/**/dawn-vs-doe*.json"
```

The cube is not for “smarter benchmarking”; it is an evidence normalization layer.
It is useful for release-grade comparison visibility across lanes and workload
coverage, and it tracks conformance/legacy provenance (`sourceConformance`) per row.

## Quick start

Published package:

```bash
npm install doe-gpu
```

Local runtime work:

```bash
cd runtime/zig
zig build test
zig build dropin
```

Doe currently requires Zig 0.15.2. See
[`config/toolchains.json`](config/toolchains.json).

If you are working on Dawn-vs-Doe comparisons, use the benchmark tooling in
[`bench/README.md`](bench/README.md) rather than treating this README as the
operational guide.

## Deprecated packages

The following packages are deprecated and replaced by `doe-gpu`:

- `@simulatte/webgpu` — use `doe-gpu` instead
- `@simulatte/webgpu-doe` — merged into `doe-gpu`

## Documentation

- [`docs/architecture.md`](docs/architecture.md): system overview
- [`docs/process.md`](docs/process.md): stage order, gates, and release policy
- [`docs/status.md`](docs/status.md): current status and tracked follow-ups
- [`docs/thesis.md`](docs/thesis.md): project thesis and framing
- [`runtime/zig/README.md`](runtime/zig/README.md): runtime development guide
- [`bench/README.md`](bench/README.md): benchmark workflows and evidence lanes
- [`packages/doe-gpu/README.md`](packages/doe-gpu/README.md): npm package

## License

See [`docs/licensing.md`](docs/licensing.md).
