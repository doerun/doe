# Doe thesis

## What Doe is

Doe is a Zig-first WebGPU runtime and compiler for replacing hidden,
heavyweight GPU execution stacks with a source-preserving, receipt-backed
accelerator path.

Dawn is the WebGPU runtime baseline used in Chromium and most browser-shaped
deployments. Tint is Dawn's shader compiler. Doe's flagship strategic target is
to beat that Dawn/Tint stack on claimable compiler, runtime, and browser-lane
evidence, then become the best open-source WebGPU implementation path for
Chromium-family browsers.

That target does not mean Doe is already the browser default. Package, embedded,
native, and server-side JavaScript lanes such as Node.js and Bun are the proof
ladder: they establish strict Dawn-vs-Doe methodology, hot-path behavior,
compiler correctness, traces, and receipts before browser promotion.

One concrete integration lane for that scope is a Doe-backed ONNX Runtime
plugin EP — a native ML-host surface, not a claim that Doe has displaced
Chromium's runtime stack.

The project goal is not "rewrite WebGPU in Zig" for its own sake. The goal is
to reduce hot-path CPU cost, keep runtime behavior explainable from config and
artifacts, and make correctness/performance claims reproducible.

## Core thesis

Doe is built around one technical split:

1. Hoist what can be decided or proven ahead of time.
2. Keep truly dynamic behavior explicit in Zig.
3. Use Lean only where proof work removes runtime branches or discharges
   blocking obligations.

That gives Doe two intended properties relative to general-purpose WebGPU
runtimes:

- less recurring runtime work on hot paths
- smaller, more auditable implementation boundaries

Scope boundary:

- Dawn and Tint are the incumbent runtime/compiler baselines.
- Package, native, embedded, and server-side JavaScript lanes are evidence
  ladders, not the final product ceiling.
- Chromium/browser replacement is the flagship product target, but claims only
  promote from browser-lane artifacts that pass compatibility, trace,
  correctness, and comparability gates.

## Why this exists

Industrial WebGPU stacks pay recurring CPU-side cost from:

- repeated validation
- abstraction layering
- runtime policy branching
- process and bridge overhead in some deployment shapes

Those costs matter most on small, frequent GPU workloads where dispatch,
submission, and setup overhead dominate.

## Operating model

Doe is self-contained:

- the runtime is implemented in Zig
- policy lives in config and schema-backed artifacts
- proof work lives in Lean
- benchmarking, traces, and gates provide the evidence surface

Current Lean theorem inventory is tracked in
`pipeline/lean/artifacts/proven-conditions.json`; `pipeline/lean/README.md`
describes the proof categories and integration boundary.

Dawn, Tint, and wgpu are comparison baselines, not runtime dependencies.

That matters for how Doe should be evaluated. The immediate question is not
"has Doe replaced the browser runtime?" The immediate question is whether each
evidence lane closes a concrete gap toward a forced-Doe Chromium path: compiler
quality against Tint, runtime behavior against Dawn, browser compatibility at
the `navigator.gpu` seam, and diagnostic receipts that explain failures instead
of hiding them behind fallback.

## Verification stance

Formal methods are a tool for shrinking runtime logic, not a substitute for
sandboxing or deployment boundaries.

Doe supports two broad verification profiles:

1. Ahead-of-time verified inputs
   Lean proves selected invariants offline, and Zig executes the resulting
   specialized path.
2. Dynamic runtime verification
   Zig keeps the necessary runtime checks for untrusted or late-bound inputs.

The rule is Zig first, then prove away branches when the proof work is worth
it.

## Evidence standard

Doe only treats performance claims as real when they are backed by:

- matched workload contracts
- explicit comparability and claimability status
- reproducible run metadata
- traceable benchmark artifacts

Narrative claims without those artifacts are not part of the project contract.

## What success looks like

For v0, success is trend-based rather than slogan-based:

- lower hot-path overhead on targeted workloads
- deterministic replay and traceability
- explicit unsupported behavior instead of silent fallback
- improving CTS and benchmark evidence
- proof coverage only where it deletes meaningful runtime logic
- browser-lane progress that keeps the Chromium fork delta small and WebGPU
  focused

## Related docs

- [`problems-addressed.md`](./problems-addressed.md) for specific practitioner
  pain points and how Doe handles them
- [`architecture.md`](./architecture.md) for system surfaces
- [`chromium-webgpu-task-list.md`](./chromium-webgpu-task-list.md) for the
  Dawn/Tint/Chromium task list
- [`performance-strategy.md`](./performance-strategy.md) for Dawn comparison
  methodology

## Non-goals

Doe is not trying to:

- replace browser/process sandbox policy with theorem proving
- claim Doe is already the browser runtime standard
- fork Chromium broadly outside WebGPU runtime integration boundaries
- treat package wrappers, browser shims, and native runtime lanes as one surface
- claim wins from non-comparable benchmark runs
- hide policy or fallback behavior in undocumented runtime branches
