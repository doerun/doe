# Benchmark harness taxonomy

## Purpose

This document defines the benchmark and comparison harness classes in Fawn, the question each class answers, and which classes may share code versus remain separate.

The key rule is:

- keep separate anything that changes the contract under test
- share code only where the contract stays the same

Do not collapse these harnesses into one generic runner. That would blur evidence classes and make failures harder to interpret.

## Harness classes

### 1. Single-runtime measurement

- Primary entrypoint: `bench/single-runtime/run_bench.py`
- Question: "How does one runtime perform on a configured workload?"
- Contract: one runtime, one workload template, measured timing artifact
- Allowed outputs:
  - single-runtime benchmark artifacts
  - baseline-relative measurement
- Not for:
  - claimable Doe-vs-Dawn comparison
  - package-surface comparison
  - browser projection evidence

### 2. Left/right runtime comparison

- Primary entrypoint: `bench/native-compare/compare_dawn_vs_doe.py`
- Question: "Given the same workload contract, is Doe comparable to and faster/slower than Dawn?"
- Contract:
  - explicit left/right executors or runtime templates
  - left is normally Doe's direct backend implementation path
  - right may be either Doe's Dawn delegate path or a standalone non-Doe WebGPU executor
  - timing-source selection
  - comparability obligations
  - claimability status
- Allowed outputs:
  - canonical Doe-vs-Dawn compare reports
  - `comparisonStatus`
  - `claimStatus`
- This is the main claim-grade compare harness.
- The current executor architecture is:
  - authored neutral benchmark IR
  - normalized executable plan
  - executor-specific implementation
  - shared compare/report contract

### 3. Generic ad hoc runtime comparison

- Primary entrypoint: `bench/native-compare/compare_runtimes.py`
- Question: "How do these two commands compare if I just want repeated wall-time measurements?"
- Contract: generic two-command repeated execution
- Allowed outputs:
  - diagnostic left/right comparison artifacts
- Not for:
  - claim-grade comparability
  - workload-contract substantiation

### 4. Package-surface comparison

- Primary entrypoints:
  - `bench/package-compare/node/compare.js`
  - `bench/package-compare/bun/compare.js`
  - `bench/package-compare/deno/compare.js`
- Question: "How does the package surface behave and perform for users of Node/Bun/Deno WebGPU APIs?"
- Contract:
  - provider-level validation prepass
  - package runtime execution through per-provider runners
  - package compare report
- Allowed outputs:
  - package-surface compare reports
  - cube-ingestable package rows
- Separate from runtime compare because the execution surface is the package API, not the Doe runtime CLI.

### 5. Targeted JS attribution experiments

- Primary entrypoints:
  - `bench/diagnostics/node/bench-headless-webgpu-comparison.mjs`
  - `bench/diagnostics/node/bench-streaming-webgpu-comparison.mjs`
  - `bench/diagnostics/node/bench-doe-routines-vs-cpu.mjs`
- Question: "Why is this path fast or slow?"
- Contract:
  - targeted experiment
  - often multi-runner or CPU-vs-GPU
  - phase-attribution output
- Allowed outputs:
  - engineering diagnosis
  - wrapper-model comparisons
  - phase breakdowns
- Not for:
  - canonical claim lanes
  - release substantiation

### 6. ABI / drop-in benchmark validation

- Primary entrypoint: `bench/drop-in/dropin_benchmark_suite.py`
- Question: "How does the drop-in shared-library surface behave and perform?"
- Contract:
  - artifact-linked ABI surface
  - micro and end-to-end drop-in benchmarks
- Allowed outputs:
  - drop-in benchmark reports
  - drop-in gate evidence
- Separate from native/package/browser lanes because the test surface is the shared-library ABI.

### 7. Browser smoke correctness

- Primary entrypoints:
  - `browser/chromium/scripts/run-smoke.sh`
  - `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- Question: "Does WebGPU work correctly in a real Chromium browser process?"
- Contract:
  - Playwright-driven real browser execution
  - compute and render smoke checks
- Allowed outputs:
  - browser correctness evidence
  - browser gate evidence
- Separate from browser benchmark lanes because smoke is correctness-first, not performance projection.

### 8. Browser benchmark projection

- Primary entrypoints:
  - `browser/chromium/scripts/run-bench.sh`
  - `browser/chromium/scripts/run-browser-benchmark-superset.py`
  - `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- Question: "How do browser-layer projections of core workloads behave in real Chromium execution?"
- Contract:
  - generated projections from core workloads
  - layered browser benchmark classes (`L1`, `L2`)
  - browser-local diagnostic evidence unless explicitly promoted
- Allowed outputs:
  - layered browser benchmark reports
  - browser promotion evidence
- Separate from package-surface and native lanes because the execution surface is an actual browser process with browser lifecycle overhead.

### 9. WGSL compilation comparison

- Primary entrypoints:
  - `bench/native-compare/compare_doe_vs_tint_compilation.py`
  - also dispatchable via `compare_dawn_vs_doe.py` with `runnerType: "compilation"` catalog entries
- Question: "How does Doe's WGSL compiler compare to Tint (Dawn's compiler) for shader compilation speed?"
- Contract:
  - left: Doe `doe-compilation-bench` binary
  - right: Tint CLI
  - per-shader WGSL-to-target (MSL/SPIR-V) compilation timing
  - named workload rows from `bench/workloads/*.json` are the canonical source
    for what gets compiled
  - compiler rows may point at the standalone compilation corpus or at real
    `bench/inference-pipeline/kernels/*.wgsl` model kernels
- Allowed outputs:
  - per-shader compilation time deltas
  - directional Doe-vs-Tint compilation reports
- Not for:
  - claim-grade runtime performance comparison
  - runtime dispatch or execution evidence
- Separate from runtime compare because the surface is the compiler toolchain, not the GPU runtime. Different codebases (Doe ~13.7K LOC vs Tint ~200K LOC) make strict comparability structurally impossible; all results are directional.

## What may share code

These are valid consolidation targets because they keep the same contract class:

- Node, Bun, and Deno compare orchestration
  - shared package-compare core
  - thin `bench/package-compare/node/compare.js`, `bench/package-compare/bun/compare.js`, and `bench/package-compare/deno/compare.js` wrappers
- Targeted JS attribution benches
  - shared experiment driver
  - workload-specific scenario modules
- Internal helper modules inside `bench/native-compare/modules/`
  - timing/reporting/comparability/claimability are already the right level of sharing

## What must remain separate

Do not merge these classes:

- `run_bench.py` with `compare_dawn_vs_doe.py`
- runtime compare with package compare
- package compare with browser Playwright harnesses
- browser smoke with browser benchmark projection
- claim lanes with targeted attribution experiments
- drop-in benchmark suite with runtime/package/browser harnesses
- compilation comparison with runtime comparison

If these are merged, the same artifact format would start mixing different contracts, which makes status interpretation unreliable.

## Retirement criteria

The only obvious retirement candidate is `bench/native-compare/compare_runtimes.py`.

Keep it only if it still has an active niche:

- fast ad hoc left/right diagnostics
- situations where full workload-contract comparability is unnecessary

If all active users actually need workload-contract evidence, it can be retired in favor of `bench/native-compare/compare_dawn_vs_doe.py`.

## Practical decision rule

When adding a new harness, decide by the first question:

1. What surface is being tested?
   - runtime implementation path
   - package API
   - browser
   - ABI/drop-in
   - compiler toolchain
2. Is this correctness smoke, canonical comparison, or diagnostic attribution?
3. Does it need claim-grade status, or only engineering guidance?

If the answer changes any of those three, add a separate harness class.
If not, extend or refactor within the existing class.
