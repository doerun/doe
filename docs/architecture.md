# Doe architecture

## System surfaces

Doe has three user-facing/runtime-adjacent surfaces and two supporting layers.

1. `runtime/zig`
   The core Doe runtime: WGSL pipeline, backend execution, runtime artifacts,
   and shared-library outputs.
2. `packages/doe-gpu`
   The JavaScript package surface for Node.js, Bun, Deno, and browser-facing
   wrappers.
3. `browser/chromium`
   The Chromium lane: docs, contracts, scripts, and probes for the future
   browser-runtime integration path.
4. `bench`
   Compare harnesses, gates, and evidence workflows.
5. `pipeline/*` plus `config/*`
   Quirk mining, proof artifacts, trace/replay contracts, schemas, and policy.

These surfaces are related, but they are not interchangeable.

## Product boundary rules

The important boundary distinctions are:

- `runtime/zig` is the real runtime implementation
- `doe-gpu` is the package surface over that runtime
- `doe-gpu/browser` is a browser wrapper, not the Doe runtime running inside the browser
- `browser/chromium` is the future browser-runtime lane, not the current package wrapper
- `bench` measures surfaces; it is not itself a product surface

That separation is deliberate. It keeps package ergonomics, runtime behavior,
and browser integration from getting blurred together in docs or benchmarks.

## Core module flow

At a high level, Doe works like this:

1. `pipeline/agent`
   Mines upstream quirk/workaround signals and normalizes them into structured
   records.
2. `config`
   Holds schemas, policies, workload contracts, and versioned control data.
3. `pipeline/lean`
   Formalizes selected obligations and emits proof artifacts when enabled.
4. `runtime/zig`
   Consumes config and optional proof artifacts, then executes the runtime on
   Metal, Vulkan, or D3D12.
5. `bench` and `pipeline/trace`
   Verify correctness, comparability, replayability, and claimability from
   emitted artifacts.

The current Lean theorem inventory is recorded in
`pipeline/lean/artifacts/proven-conditions.json`; architecture docs should
refer to that artifact rather than restating counts.

## Execution model

Doe is designed around explicit runtime behavior:

- backend selection is policy/config driven
- strict lanes do not silently fallback
- unsupported capabilities fail with typed, actionable errors
- hot-path behavior stays in Zig unless it can be hoisted out by proof/config

Current native backend identities are:

- `doe_metal`
- `doe_vulkan`
- `doe_d3d12`
- `dawn_delegate` as the incumbent compare lane

## Verification boundary

Doe supports two broad modes:

1. Ahead-of-time verified execution
   Selected invariants are proven offline and used to remove runtime work.
2. Runtime-checked execution
   Zig keeps the necessary dynamic checks for untrusted inputs.

The design rule is:

1. implement deterministic behavior in Zig first
2. measure it
3. move conditions into proof/config only when that lets Doe delete runtime
   branches safely

## Browser lane split

There are two distinct browser-related paths:

1. `packages/doe-gpu/browser`
   A JS shim that forwards to the browser's own WebGPU objects. No Doe Zig
   runtime executes there.
2. `browser/chromium`
   The Track A lane that aims to make browser `navigator.gpu` run on Doe
   instead of Dawn.

Those paths answer different questions and should not be described as the same
thing.

## Build and evidence outputs

A useful Doe build/run can emit:

- runtime artifact(s)
- run metadata
- trace or trace-meta artifacts
- benchmark reports
- optional proof artifacts and hashes

The artifact chain matters as much as the code. Doe treats claims as valid only
when they are tied back to those emitted contracts.

## Related docs

- [`docs/problems-addressed.md`](./problems-addressed.md) for practitioner pain points and how Doe handles them
- [`docs/thesis.md`](./thesis.md) for project rationale
- [`docs/process.md`](./process.md) for stage order and gates
- [`docs/numeric-stability-runtime-roadmap.md`](./numeric-stability-runtime-roadmap.md) for the numeric-stability integration path from bench evidence to live runtime contract
- [`docs/numeric-stability-claim-ladder.md`](./numeric-stability-claim-ladder.md) for the current and target claim boundary around numeric stability
- [`docs/numeric-stability-demo-ladder.md`](./numeric-stability-demo-ladder.md) for the first live demo set and promotion rules
- [`docs/numeric-stability-moat-plan.md`](./numeric-stability-moat-plan.md) for the route-effect boundary between a runtime feature and a moat
- [`pipeline/lean/README.md`](../pipeline/lean/README.md) for Lean proof categories and the artifact boundary
- [`bench/README.md`](../bench/README.md) for compare and claim workflows
- [`runtime/zig/README.md`](../runtime/zig/README.md) for runtime details
- [`browser/chromium/README.md`](../browser/chromium/README.md) for the Chromium lane
