# Benchmark taxonomy

## Purpose

This document defines the benchmark model for Doe: how products are run,
how results are compared, and which surfaces exist.

For the canonical axis language, use `docs/compare-taxonomy.md` and
`config/compare-taxonomy.json`.

## Core model

Two operations, not specialized per-pair harnesses:

1. **Run** — execute one product on one workload under one axis combination.
   Produces an independent run artifact.
2. **Compare** — ingest N independent run artifacts for the same workload and
   axes and produce comparison evidence under comparability and claimability
   contracts.

Products are pluggable. Adding a new product means registering an executor,
not writing a new harness. "Compare A vs B" is never a harness — it is
"run A, run B, compare."

## Products

A product is an independently runnable WebGPU implementation or toolchain:

- `doe` — Doe direct backend (Zig runtime)
- `dawn` — Dawn delegate or standalone Dawn executor
- `tint` — Dawn's WGSL compiler (compilation surface only)
- `dawn_node_webgpu` — Dawn's Node WebGPU binding
- `bun_webgpu` — Bun's native WebGPU
- `deno_webgpu` — Deno's native WebGPU

Each product has one or more executors that implement the run contract for
a given surface.

## Surfaces

A surface is the execution boundary being tested:

- `backend_native` — direct backend implementation (Zig/C++ runtime CLI)
- `direct_plan` — normalized plan executor (plan-backed comparable rows)
- `package` — JS package API (Node/Bun/Deno providers)
- `abi_dropin` — shared-library ABI surface
- `browser` — real browser process (Playwright)
- `compiler` — WGSL compilation toolchain

## Comparison is post-hoc

Comparison is never baked into a runner. A runner produces an artifact for
one product. The comparison framework:

1. Ingests independent run artifacts for the same workload and axes
2. Enforces comparability contracts (timing class, structural equivalence,
   normalization parity)
3. Produces comparison reports with claimability status

Adding product C to an existing A-vs-B comparison is just "run C, feed
all three to compare" — no new harness needed.

## Correctness surfaces

Correctness gates are separate from performance:

- Browser smoke (Playwright) — "does WebGPU work in a real browser?"
- ABI drop-in validation — "does the shared-library surface behave correctly?"
- Runtime test suites — `zig build test`, `zig build test-wgsl`

These produce correctness evidence, not performance artifacts.

## What must remain separate

- Run and compare operations (a runner never contains comparison logic)
- Performance and correctness surfaces
- Claim-grade evidence and diagnostic/attribution experiments

## Practical decision rule

When adding a new benchmark:

1. Is this a new product? Register an executor.
2. Is this a new surface? Define the run contract.
3. Is this a new comparison? Run both products and feed to compare.

If you find yourself writing a new `compare_X_vs_Y` script, stop — that is
the old model. Run X, run Y, compare.

## Migration status

The current harness code (`compare_dawn_vs_doe.py`, package compare scripts,
etc.) still uses the old pair-based model internally. Migration to the
product-based model is tracked in `docs/status.md`. The taxonomy and axis
language defined here and in `docs/compare-taxonomy.md` are the target
architecture.
