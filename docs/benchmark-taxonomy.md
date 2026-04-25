# Benchmark taxonomy

## Purpose

This document defines the least-confusing benchmark model for Doe.

Use it when you need to answer:

- what is a workload?
- what is a surface?
- what is an executor?
- how do isolated runs and compare reports relate?

For the canonical axis language that powers promoted compare profiles, use
this document and `config/compare-taxonomy.json`.

## Canonical source of truth

The single source of truth for compare axis values is:

- `config/compare-taxonomy.json`

The schema that validates that source of truth is:

- `config/compare-taxonomy.schema.json`

The generated machine-readable expansion lives in:

- `config/generated/compare-taxonomy-expanded.jsonl`
- `config/compare-taxonomy-expanded-entry.schema.json`

Those generated files are derived artifacts, not parallel taxonomy
sources. The promoted catalog and governed benchmark catalog are
downstream consumers, not independent definitions:

- `config/promoted-compare-catalog.json`
- `config/governed-lanes.json`

If any of those disagree with `config/compare-taxonomy.json`, the
taxonomy file is authoritative and the derived wiring must be updated
to match it.

## 30-second mental model

Doe benchmarking has two operations:

1. **Run** one product on one workload with one executor.
2. **Compare** two or more run artifacts for the same workload and surface.

The benchmark primitive is always the isolated run artifact. Comparison is
post-hoc analysis over those artifacts.

## Glossary

- **Workload**
  - One benchmark definition.
  - Example: `compute_dispatch_grid` or
    `inference_gemma3_270m_prefill_32tok`.
- **Surface**
  - The execution boundary being tested.
  - Example: `backend`, `plan`, `package`.
- **Executor**
  - The concrete runner for one product on one surface.
  - Example: `doe_direct_metal`, `dawn_direct_metal`,
    `doe_node_webgpu`.
- **Run artifact**
  - The output of one isolated run.
  - It records timing, trace metadata, workload identity, and executor identity.
- **Compare report**
  - The output of joining two or more run artifacts for the same workload.
- **Cohort**
  - A named subset of workloads such as `smoke`, `regression`, or `governed`.

## Canonical axes

| # | Axis | Values | What it names |
|---|------|--------|---------------|
| 1 | `platform` | `apple-metal`, `amd-vulkan`, `local-d3d12` | Hardware/driver target |
| 2 | `surface` | `backend`, `plan`, `package`, `dropin`, `browser`, `compiler` | Execution boundary |
| 3 | `product` | `doe`, `dawn`, `tint`, `node_webgpu_package`, `bun_webgpu_package`, `deno_webgpu_package` | Implementation under test |
| 4 | `runtimeHost` | `none`, `node`, `bun`, `deno`, `chromium` | JS host runtime; `none` for backend/plan/dropin/browser/compiler surfaces |
| 5 | `temperature` | `default`, `cold`, `warm` | Session warmth |
| +1 | `targetKind` | `preset`, `workload` | Target selection mode |

Key distinctions:

- `surface` names the benchmark boundary, not the product.
- `product` names what is being benchmarked.
- `runtimeHost` names the JS host.
- Comparison is derived from choosing which products to compare over
  the same axes. It is not an axis itself.

The taxonomy records alias maps for user-facing vocabularies:

- surface names used by `bench/cli.py compare`
- repo surface names used by governed benchmark subsets and workload registry
- lower-level executor boundaries such as `backend_native`,
  `direct_plan`, `package_surface`, and `abi_dropin`

That mapping lives under `aliases` in `config/compare-taxonomy.json`.

## Terms to avoid in benchmark docs

These terms are not banned from machine contracts, but they are not the
canonical human model:

- `row`
- `baseline/comparison`
- `lane`

Use these instead:

- `workload`
- `surface`
- `executor`
- `run artifact`
- `compare report`
- `baseline/comparison` only when you specifically mean a compare report role

## Core model

Products are pluggable. Adding a new product means registering an executor,
not writing a new pair-specific harness.

"Compare Doe vs Dawn" is never a special runner. It always means:

1. run Doe
2. run Dawn
3. compare the resulting run artifacts

## Products

A product is an independently runnable WebGPU implementation or toolchain:

- `doe` — Doe backend runtime or package/runtime surface
- `dawn` — Dawn delegate or standalone Dawn executor
- `tint` — Dawn WGSL compiler
- `node_webgpu_package` — `node-webgpu` package surface
- `bun_webgpu_package` — Bun WebGPU binding
- `deno_webgpu_package` — Deno WebGPU binding

Each product can have multiple executors, because the same product may run on
multiple surfaces.

## Surfaces

A surface is the execution boundary being tested:

- `backend` — Doe or Dawn running at the backend/runtime command level
- `plan` — Doe or Dawn running the normalized plan executor
- `package` — package-facing JS execution through Node, Bun, or Deno
- `dropin` — shared-library ABI surface
- `browser` — browser process execution
- `compiler` — WGSL compilation toolchain

## Example workflows

### 1. Doe-only backend benchmark

You want to measure Doe Metal directly on `render_draw_throughput_200k`.

- workload: `render_draw_throughput_200k`
- surface: `backend`
- executor: `doe_direct_metal`
- output: one Doe run artifact

No comparison is involved.

### 2. Doe vs Dawn backend benchmark

You want an apples-to-apples backend compare for the same workload.

- workload: `render_draw_throughput_200k`
- surface: `backend`
- Doe executor: `doe_direct_metal`
- Dawn executor: `dawn_delegate_metal`

Run both products independently, then compare the two run artifacts.

### 3. Plan-backed Gemma benchmark on plan executors

You want to compare Gemma inference on Metal using the normalized plan surface.

- workload: `inference_gemma3_270m_prefill_32tok`
- surface: `plan`
- Doe executor: `doe_direct_plan_metal`
- comparison executors:
  - `dawn_direct_metal`
  - `webkit_webgpu_native_metal`

This workload is plan-backed because the benchmark contract exposes a
`planPath`. The fair surface is the normalized plan on both sides.

### 4. The same Gemma workload on the Node package surface

You want the package-user view of the same benchmark.

- workload: `inference_gemma3_270m_prefill_32tok`
- surface: `package`
- Doe executor: `doe_node_webgpu`
- comparison executor: `node_webgpu_package`

The workload is the same. The surface is different.

### 5. Prepared-session package benchmark

You want the same Node package benchmark, but excluding initial session setup.

- workload: `inference_gemma3_270m_prefill_32tok`
- surface: `package`
- Doe executor: `doe_node_webgpu_prepared`
- comparison executor: `node_webgpu_package_prepared`
- temperature: `warm`

Again, the workload stays the same. The session temperature changes.

## Plan-backed workloads

A workload is **plan-backed** when its benchmark contract exposes `planPath`.

That means:

- the authored benchmark unit is the normalized plan
- the comparable execution boundary is the normalized plan
- compatibility `commandsPath` artifacts may still exist for debugging or
  legacy runtime tooling, but they are not the claim-oriented benchmark
  boundary for that workload

## Comparison is post-hoc

Comparison is never baked into a runner. The comparison framework:

1. ingests independent run artifacts for the same workload and surface
2. enforces comparability and claimability contracts
3. produces one compare report

Adding a third product never requires a new compare harness. It is just:

1. run the third product
2. feed its run artifact into compare

## Correctness surfaces stay separate

Correctness evidence is not performance evidence.

Examples:

- browser smoke
- ABI drop-in validation
- `zig build test`
- `zig build test-wgsl`

These produce correctness artifacts, not benchmark comparisons.

## Practical decision rule

When adding a benchmark-related feature:

1. Is this a new workload?
   Add or update a workload contract.
2. Is this a new surface?
   Define the run contract for that surface.
3. Is this a new product?
   Register an executor.
4. Is this a new comparison?
   Do not write a new pair-specific harness. Run both products and compare the
   resulting artifacts.

## Boundaries underneath surfaces

Surface is the human-facing benchmark term.

Some tooling also carries a lower-level executor boundary field:

- `backend` surface -> `backend_native` boundary
- `plan` surface -> `direct_plan` boundary
- `package` surface -> `package_surface` boundary

That boundary field exists so executors and older artifacts can describe the
exact runtime contract. It is not the primary vocabulary for benchmark docs or
front doors.

## Migration status

The canonical benchmark flow already follows this model:

1. isolated runs emit immutable run artifacts
2. compare joins those artifacts post-hoc into a compare report

`bench/cli.py` is the only live benchmark front door. Release scripts and
governed profiles resolve through `bench/cli.py compare`, but the execution
model is still the same artifact-first run/compare flow.
