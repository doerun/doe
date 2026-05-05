# Doe thesis

## What Doe is

Doe is a Zig-first WebGPU runtime for cases where you want a direct, explicit
runtime instead of shipping Dawn.

Dawn is the WebGPU runtime baseline used in Chromium and most browser-shaped
deployments. Doe targets the lanes where a lighter, more explicit runtime is
useful today: package, embedded, native, and server-side JavaScript runtimes
such as Node.js and Bun. The near-term scope is not "replaces browser WebGPU";
it is matched-workload comparison against Dawn in those lanes.

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

- Dawn is the comparison baseline
- Doe targets package, native, embedded, and server-side JavaScript runtime
  lanes
- Chromium/browser replacement is a future lane, not the current proof point

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

Dawn and wgpu are comparison baselines, not runtime dependencies.

That matters for how Doe should be evaluated. The immediate question is not
"has Doe replaced the browser runtime?" The immediate question is whether Doe
provides a better runtime boundary than Dawn in the package, native, and
embedded shapes it targets directly, measured under matched-workload contracts.

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

## Related docs

- [`problems-addressed.md`](./problems-addressed.md) for specific practitioner
  pain points and how Doe handles them
- [`architecture.md`](./architecture.md) for system surfaces
- [`performance-strategy.md`](./performance-strategy.md) for Dawn comparison
  methodology

## Non-goals

Doe is not trying to:

- replace browser/process sandbox policy with theorem proving
- claim Doe is already the browser runtime standard
- treat package wrappers, browser shims, and native runtime lanes as one surface
- claim wins from non-comparable benchmark runs
- hide policy or fallback behavior in undocumented runtime branches
