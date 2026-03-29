# Doe bench

Audience:

- internal operator tooling and contributor workflows
- not part of the public `doe-gpu` npm package contract

Canonical front doors:

- `run.py` — unified entry point (see Quick Start below)
- `run_compare.py` — config-backed compare front door
- `native-compare/compare_dawn_vs_doe.py`
- `runners/publish_apple_runtime_release.py`
- `run_release_pipeline.py`
- `run_blocking_gates.py`
- `generate_backend_workloads.py`

Canonical compare taxonomy:

- `docs/compare-taxonomy.md`
- `config/compare-taxonomy.json`
- `config/generated/compare-taxonomy-expanded.jsonl`

For public package usage, use `packages/doe-gpu/README.md`. For the public vs
repo-only tooling boundary, use `docs/internal-tooling.md`. For the Apple
runtime bundle receipt, use `docs/apple-metal-runtime-release.md`.

Purpose:
- run correctness and performance measurements against specialization outputs
- enforce blocking/advisory gate modes from `config/gates.json`

This module is self-contained and does not depend on external runtime code.

## Quick Start

`bench/run.py` is a unified entry point that dispatches to the right harness
script with the right config. All three positional arguments are optional and
order-independent. Backend auto-detects from platform (metal on macOS, vulkan
on Linux, d3d12 on Windows).

```sh
bench/run.py                            # compare metal smoke (macOS default)
bench/run.py breadth                    # compare metal breadth — full coverage, fast
bench/run.py compare vulkan release     # explicit harness + backend + preset
bench/run.py compile metal smoke        # WGSL compilation comparison (Doe vs Tint)
bench/run.py single metal --workload-id compute_dispatch_grid
bench/run.py compare metal --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.ir.json
python3 bench/run_compare.py --list
python3 bench/run_compare.py --surface native --backend apple-metal --preset compare
python3 bench/run_compare.py --surface direct --backend apple-metal --workload gemma270m-literal
python3 bench/run_compare.py --surface package --backend apple-metal --workload gemma64 --mode warm
python3 bench/runners/publish_apple_runtime_release.py --timestamp <YYYYMMDDTHHMMSSZ>
python3 bench/runners/exercise_runtime_numeric_stability.py
python3 bench/runners/exercise_in_path_numeric_stability.py
```

Positional arguments:

| Axis    | Values | Default |
|---------|--------|---------|
| Harness | `compare`, `single`, `compile`, `adhoc` | `compare` |
| Backend | `metal`, `vulkan`, `d3d12` | auto-detect |
| Preset  | `smoke`, `compare-dev`, `compare`, `frontier`, `explore`, `release`, `breadth` | `smoke` |

Extra `--flags` after the positionals are forwarded to the underlying harness
script. The runner warns if workload lane files are stale relative to the
catalog.

## Numeric-stability promotion and runtime exercise

Numeric-stability work now has three explicit repo runners:

- `bench/runners/promote_numeric_fragility_signatures.py`
  - lifts the latest corpus export into checked-in promoted signatures and the
    promoted fragility catalog
- `bench/runners/exercise_runtime_numeric_stability.py`
  - replays selected promoted prompt/control cases through the live Zig
    `doe_numeric_stability` service
  - writes runtime receipts plus bounded overhead summaries under
    `bench/out/apple-metal-runtime-numeric-stability/*`
  - updates selected signatures and the promoted catalog from `promoted` to
    `runtime-exercised`
- `bench/runners/exercise_in_path_numeric_stability.py`
  - replays selected promoted prompt/control cases through ordinary
    `doe-zig-runtime` `kernel_dispatch` execution with `numericStability`
    annotations
  - writes native trace artifacts, ordinary-execution receipts, and manifest
    summaries under `bench/out/apple-metal-in-path-numeric-stability/*`
  - is the current source of truth for native `runtime-exercised`
    `matmul.logits` signatures in the promoted catalog

The exercise lane is config-backed by:

- `config/runtime-numeric-stability-exercise.json`
- `config/runtime-numeric-stability-exercise.schema.json`
- `config/in-path-numeric-stability-exercise.json`
- `config/in-path-numeric-stability-exercise.schema.json`

## Terminology

Use this mental model when reading benchmark docs and reports:

- `Doe direct backend path`
  - This is just Doe doing its real job: implementing WebGPU semantics itself
    on a backend such as Metal, Vulkan, or D3D12.
  - On Apple Metal, this means Doe parses the workload, translates WGSL as
    needed, creates backend pipelines/resources itself, and records Metal
    command buffers directly.
- `Dawn delegate path`
  - This is the compare lane where the same workload contract is executed
    through the Dawn-backed path instead of Doe's own implementation.
- `Package-surface compare`
  - This is the JS/package lane where the same normalized plan is executed
    through public Node-facing providers rather than the direct backend
    executors.
  - Use this when the question is "what does a JS user experience?" rather
    than "which implementation wins at the backend boundary?"
- `Plan-backed comparable runtime row`
  - If a comparable runtime workload exposes `planPath`, the fair benchmark
    boundary is the normalized plan on both sides.
  - For claim-oriented `workloadUnitWall` comparisons, Doe and Dawn must both
    run direct plan executors. Generated compatibility `commandsPath` artifacts
    remain useful for debugging and legacy runtime paths, but they are not the
    comparable wall-time boundary for IR-backed rows.
- `Runtime workload`
  - A runtime row usually includes three kinds of work together:
    API/setup work, first-use kernel compilation/pipeline creation, and GPU
    dispatch execution.
  - Compilation-only rows are separate `runnerType: "compilation"` workloads.
- `Host-overhead breakdown`
  - Compare reports now also expose
    `timingInterpretation.hostOverheadBreakdown`.
  - This is a coarse once-per-sample breakdown of workload-unit wall overhead
    outside the selected execution timing, derived from trace-meta totals such
    as input read/parse, executor init, prewarm, command orchestration, and
    artifact finalization.

The important comparison split is therefore:

- Doe implementation path
- Dawn delegate path

not:

- "Doe native" versus "Doe non-native"

## Performance Strategy (Read First)

Before running or interpreting Dawn-vs-Doe performance results, read:

- `docs/performance-strategy.md`
- `docs/benchmark-taxonomy.md`
- `bench/docs/benchmark-writing-guide.md`

If you're adding or changing workloads/commands, treat the benchmark writing guide as the required authoring contract.

That document defines:

- claimability order and comparability invariants
- delta sign convention (`+` faster, `-` slower from Doe/left perspective)
- optimization priorities and anti-patterns

## Workload layout

- Canonical backend workload lanes live directly under `bench/workloads/`:
  - `workloads.apple.metal.json`
  - `workloads.apple.metal.smoke.json`
  - `workloads.amd.vulkan.json`
  - `workloads.amd.vulkan.smoke.json`
  - `workloads.local.d3d12.json`
  - `workloads.local.d3d12.smoke.json`
- The source of truth is `bench/workloads/metadata/backend-workload-catalog.json`.
- Generic and special-purpose projections live under `bench/workloads/specialized/`.
  Use those only when a tool or document explicitly calls for them.
- Compilation rows now live in the same workload contracts as runtime rows.
  The Doe-vs-Tint compiler harness resolves `runnerType: "compilation"` rows
  from the workload file instead of scanning an unrelated shader directory, so
  named compilation workloads can point at the real inference-pipeline WGSLs.
- Compilation rows now publish both:
  - raw Tint process-wall timings
  - a startup-corrected derived view that subtracts the Tint trivial-shader
    baseline `p50` from each raw Tint sample
- Compilation rows may also publish a real warm/in-process Tint view from
  Dawn's `tint_benchmark` target when the compare config provides
  `right.warmBinaryPath`.
- Raw Tint timings remain the auditable source metric; the corrected view is a
  presentation aid so process startup does not get mistaken for compile work.
  The warm view is separate again: it is a true in-process Tint measurement,
  not a correction derived from the raw CLI samples.
- The benchmark-corpus config for that warm compiler surface is:
  `bench/native-compare/compare_doe_vs_tint.benchmark-corpus.config.json`
- Apple Metal also carries Doe-owned Gemma-3-270M-shaped direct-backend runtime rows:
  `inference_gemma3_270m_prefill_32tok` and
  `inference_gemma3_270m_decode_1tok`. These are plain Doe command streams,
  not imported manifest schemas: they seed uniform/token buffers with explicit
  `buffer_write` commands and dispatch the retained inference WGSL kernels in
  the same compute shape as the real prefill/decode path.
- Neutral authored benchmark IR now lives under `bench/ir/`.
  - `bench/ir/gemma3_270m.json` is the current Gemma-shaped source of truth.
  - `bench/ir/gemma3_270m_literal.json` is the current Doe-owned
    literal-production-style 270M row: it stays synthetic, but it tracks the
    production-style kernel family, entry points, gated FFN, and tied LM head
    more closely than the shaped row.
  - Generated normalized plans live under `bench/plans/generated/`.
  - Compatibility command artifacts remain emitted for Doe runtime execution,
    but they are generated artifacts, not the authored benchmark layer.
  - For comparable IR-backed runtime rows, `planPath` is the strict apples-to-
    apples execution boundary. `commandsPath` compatibility artifacts are
    non-claim debugging surfaces for those rows.
- The old synthetic JS inference-pipeline benchmark surface was removed.
  For real model inference benchmarking, use Doe-owned runtime command streams
  and runtime example paths under `runtime/zig/examples/`, not a random-weight
  JS proxy.

## IR and executors

- `bench/ir/*.json`
  - neutral authored benchmark IR
- `bench/plans/generated/*.plan.json`
  - normalized executable plans derived from the IR
- `bench/executors/`
  - standalone executors that consume normalized plans
  - current direct executor coverage:
    - Doe direct backend via `runtime/zig/zig-out/bin/doe-plan-executor`
      for plan-backed comparable runtime rows
    - standalone direct Dawn/WebGPU executor via `runtime/zig/zig-out/bin/dawn-plan-executor`
    - standalone Node package executor via `bench/executors/run-node-webgpu-plan.js`
      for:
      - `doe-gpu` (`doe_node_webgpu`)
      - Dawn Node WebGPU (`dawn_node_webgpu`)

The compare harness can now resolve executor ids instead of only raw command
templates. The current Gemma-shaped end-to-end config is:

- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.ir.json`

That row compares:

- left: Doe direct Metal backend execution through the normalized plan executor
- right: standalone direct Dawn/WebGPU execution on Metal

over the same normalized `prefill64 + decode64` Gemma-shaped plan.

Package-surface configs now exist alongside the direct configs:

- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.node-package.ir.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.node-package.ir.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.node-package.warm.ir.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.node-package.warm.ir.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.bun-package.ir.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.bun-package.ir.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.bun-package.warm.ir.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.bun-package.warm.ir.json`

These compare public package providers over the same normalized plan:

- Node package rows
  - left: `doe-gpu`
  - right: Dawn Node WebGPU
- Bun package rows
  - left: `doe-gpu`
  - right: `bun-webgpu`

They are apples-to-apples for the package layer, but they are not direct
backend implementation claims.

The package lane now has two explicit timing boundaries:

- cold package lane (`*.node-package.ir.json`, `*.bun-package.ir.json`)
  - keeps package setup inside `selectedTiming`
  - keeps `workloadUnitWall` on the compare harness subprocess wall
  - represents first-use package cost from a JS caller point of view
- prepared-session package lane (`*.node-package.warm.ir.json`, `*.bun-package.warm.ir.json`)
  - builds the package runtime and cached WebGPU objects before the timed sample
  - keeps `selectedTiming` on the repeated workload steps only
  - switches `workloadUnitWall` to trace-meta `processWallMs` via
    `workloadUnitWallSource=trace-meta-process-wall`
  - represents steady-state package execution without silently redefining the
    cold metric

Package trace meta now emits explicit host and setup buckets for this lane,
including input read/parse, workload prepare, executor init, command
orchestration, artifact finalize, and package setup breakdowns such as shader
module creation and bind-group/pipeline creation.

Config-backed compare wrappers now sit above those raw configs. The catalog lives in:

- `config/promoted-compare-catalog.json`

And the front door is:

- `python3 bench/run_compare.py --list`
- `python3 bench/run_compare.py --surface native --backend amd-vulkan --preset compare`
- `python3 bench/run_compare.py --surface native --backend apple-metal --preset release`
- `python3 bench/run_compare.py --surface native --backend local-d3d12 --preset smoke`
- `python3 bench/run_compare.py --surface direct --backend apple-metal --workload gemma64`
- `python3 bench/run_compare.py --surface direct --backend apple-metal --workload gemma1b`
- `python3 bench/run_compare.py --surface direct --backend apple-metal --workload gemma270m-literal`
- `python3 bench/run_compare.py --surface package --backend apple-metal --workload gemma64`
- `python3 bench/run_compare.py --surface package --backend apple-metal --workload gemma64 --mode warm`
- `python3 bench/run_compare.py --surface package --backend apple-metal --workload gemma64 --package-runtime bun`
- `python3 bench/run_compare.py --surface package --backend apple-metal --workload gemma64 --mode warm --package-runtime bun`

The matrix is explicit in config:

- `surface=native`
  - existing native command/delegate preset configs on Metal, Vulkan, and D3D12
- `surface=direct`
  - standalone Doe-plan vs standalone Dawn-plan compare rows
- `surface=package`
  - package-surface compare rows for `packageRuntime=node` or `packageRuntime=bun`, with `mode=cold` or `mode=warm`

The canonical axis vocabulary underneath those front doors is defined in
`config/compare-taxonomy.json`. Use that file, plus the generated expansion in
`config/generated/compare-taxonomy-expanded.jsonl`, when you need the unified
cartesian-product view instead of the promoted wrapper subset.

This wrapper does not replace `compare_dawn_vs_doe.py`; it resolves a friendly
config-backed matrix entry and then delegates to the existing compare runner
unchanged.

If you pass `--catalog` to `bench/run_compare.py`, relative `configPath`
entries resolve against that catalog file. The default repo catalog still
resolves its entries against repo root.

## Scripts

- `run_bench.py`
  - executes a configured workload command template, captures runtime timing samples, and emits measured metrics
  - computes timing statistics from wall time and trace-window timings when trace artifacts are present
  - emits reproducible run metadata with workload/artifact hashes and toolchain fields
  - compares against incumbent baseline ids from `config/benchmarks.json`
  - enforces host/backend compatibility before execution and fails fast on unsupported OS/backend mixes (for example: Vulkan on macOS, Metal on Linux/Windows, D3D12 on Linux/macOS).
- `check_correctness.py`
  - runs deterministic contract-level correctness checks
- `schema_gate.py`
  - validates schema-backed benchmark/config contracts as blocking release checks (`claim-cycle`, `webgpu-capability-inventory`, command coverage ledgers, Chromium integration overlay, benchmark methodology thresholds, substantiation policy, comparability obligation contracts, and all quirk examples).
- `run_blocking_gates.py`
  - canonical entrypoint for blocking gate order: schema -> correctness -> trace -> optional drop-in -> optional claim gate.
  - release-claim readiness evidence requires claim gate enabled (`--with-claim-gate`), and can be enforced with `--require-claim-gate`.
  - can run comparability verification parity fixtures with `--with-comparability-parity-gate`.
  - shader-artifact gating now treats SPIR-V validation as routine for SPIR-V-bearing manifests; `spirv-val` is auto-discovered from PATH when available.
- `comparability_obligation_parity_gate.py`
  - validates comparability obligation parity fixtures against Python evaluation and Lean obligation ID set alignment.
  - verifies fixture expectations (`expectedBlockingFailedObligations`, `expectedComparable`) from `bench/fixtures/comparability_obligation_fixtures.json`.
- `run_release_pipeline.py`
  - canonical entrypoint for CI/local release orchestration: preflight -> compare report generation -> compare HTML visualization (default on) -> optional smoke verification -> blocking gates (optional drop-in + optional claim gate).
  - when claim gate is enabled, it also emits claim rehearsal artifacts by default:
    claim gate result, tail-health table, timing-invariant audit, and contract-hash manifest.
  - when claim gate is enabled, cycle-lock/rollback enforcement runs by default via `cycle_gate.py` (disable only for diagnostics with `--no-with-cycle-gate`).
- `run_release_claim_windows.py`
  - runs repeated release pipeline windows and emits a trend summary (`comparisonStatus`, `claimStatus`, non-claimable/non-comparable workload IDs per window); can run `substantiation_gate.py` over that summary in one command.
  - forwards compare HTML generation per window by default; use `--no-compare-html-output` to disable.
  - forwards claim rehearsal artifact generation per window by default; use `--no-with-claim-rehearsal-artifacts` to disable.
  - forwards cycle-lock/rollback gate execution per window by default; use `--no-with-cycle-gate` to disable.
  - can forward optional substantiation status into cycle-gate evaluation via `--cycle-substantiation-report`.
- `build_test_inventory_dashboard.py`
  - scans Dawn-vs-Doe compare reports and emits:
    - canonical tested-profile inventory JSON (`vendor/api/deviceFamily/driver` coverage, matrix status history, report-level status rollups)
    - simple HTML dashboard for matrix status + performance delta vs Dawn
  - only includes conformant compare reports (`schemaVersion=5`, canonical comparability-obligation IDs, and valid `workloadContract.path/sha256` hash match).
  - profile combos are sourced from per-sample `traceMeta.profile` fields; sides without profile metadata are tracked as report status only (not hardware-profile coverage).
  - also writes stable latest paths (`bench/out/test-inventory.latest.json`, `bench/out/test-dashboard.latest.html`) for a single canonical source of truth.
  - excludes `bench/out/scratch/**` from canonical inventory aggregation.
- `build_baseline_dataset.py`
  - builds a canonical baseline trend package from historical comparison artifacts.
  - only includes conformant compare reports (`schemaVersion=5`, canonical comparability-obligation IDs, and valid `workloadContract.path/sha256` hash match).
  - emits timestamped JSON trend dataset + markdown summary plus stable latest outputs.
  - groups history by matrix/runtime pair and tracks latest/best/worst p50 delta snapshots.
- `build_benchmark_cube.py`
  - normalizes backend compare reports plus package-surface compare reports into a single benchmark cube contract.
  - emits timestamped JSON row artifacts, JSON cube summary, and markdown matrix slices under `bench/out/cube/<timestamp>/`.
  - also writes stable latest outputs under `bench/out/cube/latest/`.
  - preserves latest-history by default: it seeds the build with report paths referenced by the current `bench/out/cube/latest/cube.summary.json`, so explicit subset reruns cannot silently downgrade the latest mirror.
  - latest-cell selection now prefers broader evidence before newer evidence:
    canonical source conformance first, then larger row count, then better status, then newer timestamp.
    This keeps focused or subset reruns from replacing full-lane historical evidence in `latest/`.
  - use `--no-preserve-latest` only for intentionally isolated ad-hoc cube snapshots.
  - cube publication is lane-governed: every included row must resolve to governed lane IDs from `config/governed-lanes.json`.
  - backend rows carry the two source runtime lane IDs from report telemetry; package rows require explicit top-level `laneId` in the compare report.
  - package-surface compare harnesses (`bench/package-compare/node/compare.js`, `bench/package-compare/bun/compare.js`) now force workload validation prepasses before timing comparable rows so claimable package-surface artifacts fail early on readback/correctness drift.
  - `bench/package-compare/node/compare.js` now runs each workload in a fresh provider subprocess, preventing package-state carryover from contaminating later workload timings in the same compare report.
  - package surfaces can use explicit policy workload-id overrides (`config/benchmark-cube-policy.json`) so directional rows stay isolated from comparable workload-set cells.
  - backend rows preserve both canonical and legacy report history:
    - canonical rows come from fully conformant Dawn-vs-Doe reports.
    - legacy rows are kept when old reports still parse but no longer match the active workload-contract hash or obligation contract; these rows are marked `sourceConformance=legacy_nonconformant` and degrade to diagnostic in cube cells.
  - Node/Bun package rows stay explicit about maturity and missing-cell status instead of silently fabricating parity; package reports without governed `laneId` are excluded from canonical cube publication.
  - package rows now also normalize cross-surface aliases through `bench/workloads/metadata/workload-registry.json`, so package workload IDs like `buffer_upload_1kb` land in cube rows as canonical backend-aligned IDs such as `upload_write_buffer_1kb` while preserving `sourceWorkloadId`.
- `substantiation_gate.py`
  - validates claim substantiation evidence from one or more comparison reports and/or release-window summaries using `config/substantiation-policy.json` (minimum comparable+claimable report count and minimum unique left-side profile diversity).
  - `targetUniqueLeftProfiles` can now be enforced as blocking via `releaseEvidence.enforceTargetUniqueLeftProfiles` (default in repo policy: `true`).
- `dropin_symbol_gate.py`
  - validates candidate shared-library symbol completeness against `config/dropin_abi.symbols.txt`.
- `dropin_behavior_suite.py`
  - compiles and runs an artifact-linked black-box API behavior harness (instance/device creation, queue ops, error scopes, lifecycle release).
- `dropin_benchmark_suite.py`
  - compiles and runs artifact-linked micro + end-to-end benchmarks for drop-in runtime surfaces.
  - compilation contract is two translation units by default (`--source` harness + `--ops-source` operations), and the suite fails fast if only one distinct source is provided.
- `dropin_gate.py`
  - canonical drop-in compatibility entrypoint; runs symbol + behavior + benchmark suites, emits a consolidated report with per-step runtimes, and generates benchmark HTML with micro and end-to-end sections.
- `visualize_dropin_benchmark.py`
  - reads `dropin_benchmark_suite.py` JSON output and writes an HTML report that includes all benchmark rows grouped by class (`micro`, `end_to_end`).
- `compare_runtimes.py`
  - runs two runtime commands repeatedly (left/right), captures wall-time quantiles, and writes a comparison artifact.
- `bench/diagnostics/node/bench-headless-webgpu-comparison.mjs`
  - runs the four-way Node package-surface comparison for compute-heavy matmul:
    Dawn direct, Dawn + Doe helpers, Simulatte direct, and Simulatte + Doe helpers.
  - uses the same generated WGSL, matrix data, and chunk plan across all four runners.
  - the direct Simulatte lane now imports the addon-native `@simulatte/webgpu/native-direct` surface, and both helper lanes now bind the same standalone `@simulatte/webgpu-doe` helpers onto their respective raw devices. This keeps wrapper-model asymmetry out of the compare contract.
  - the helper lanes now use the same one-encoder, one-compute-pass, one-copy, one-submit, one-map round shape as the direct lanes; they no longer time `gpu.buffer.read(...)` as a second copy+submit path inside the measured round.
  - runs each GPU candidate in an isolated subprocess and prepares/tears it down sequentially so one candidate's buffers, pipelines, or provider state do not distort another candidate's measurement or stability.
  - prints per-runner phase means (`encode`, `submit+wait`, `readback`) so direct-vs-helper and Dawn-vs-Simulatte gaps can be attributed instead of treated as one opaque wall-time delta.
- `bench/diagnostics/node/bench-streaming-webgpu-comparison.mjs`
  - runs the four-way Node package-surface comparison for the streaming affine-transform workload.
  - uses the same addon-native `@simulatte/webgpu/native-direct` vs Dawn direct pairing and the same standalone `@simulatte/webgpu-doe` helper implementation on both helper lanes.
  - the helper lanes now use the same one-encoder, one-compute-pass, one-copy, one-submit, one-map round shape as the direct lanes; they no longer time `gpu.buffer.read(...)` as a second copy+submit path inside the measured round.
  - runs each GPU candidate in an isolated subprocess and prepares/tears it down sequentially so the four-way compare stays apples-to-apples without concurrent package/device resource pressure or package-state carryover.
  - run one package-surface streaming compare process at a time on a host. Concurrent ad-hoc scenario runs are diagnostic-only because overlapping package/device processes can materially distort `submit+wait` and readback timings even when each compare keeps its own candidates sequential.
  - prints per-runner phase means (`encode`, `submit+wait`, `readback`, `validation`) plus timed-sample variance (`stddev`, `CV`, `range`) for submission-heavy diagnosis.
  - supports explicit attribution scenarios via `--scenario=`:
    - `default`: 64 dispatches, full-range 16 MiB readback
    - `single-dispatch-full-readback`: 1 dispatch, full-range 16 MiB readback
    - `many-dispatches-tiny-readback`: 64 dispatches, 1 KiB readback
    - `raw-per-pipeline-bindgroups`: 64 dispatches, full-range 16 MiB readback, one direct-path bind group per pipeline
  - use those scenarios to separate dispatch-count cost, readback-byte cost, and bind-group-shape cost without changing the provider pair under test.
- `bench/diagnostics/node/bench-doe-routines-vs-cpu.mjs`
  - compares the Doe one-shot compute helper against the CPU worker baseline for the streaming workload.
- `compare_dawn_vs_doe.py`
  - executes shared workload files against two explicit command templates (default Doe backend runtime on the left side + configurable Dawn/competitor runtime).
  - outputs per-run trace artifacts (`--trace-jsonl` and `--trace-meta` when templates provide these placeholders) plus workload-level and overall quantile summaries.
  - when both sides emit Doe-native semantic operator manifests, the compare report now also includes per-workload `operatorDiff` summaries and a top-level `operatorDiffSummary` that point at the first structural divergence (or structural match) from `.operators.json` artifacts.
  - enforces host/backend compatibility before execution and fails fast on unsupported OS/backend mixes (for example: Vulkan on macOS, Metal on Linux/Windows, D3D12 on Linux/macOS).
  - current repo compare configs default to command-stream Dawn delegate lanes (`dawn_delegate`) for apples-to-apples strict workloads; `dawn_benchmark_adapter.py` remains available for gtest-filter diagnostics.
  - core logic is now split into dedicated helper modules under `bench/native_compare_modules/`:
    `timing_selection.py`, `comparability.py`, `claimability.py`, `reporting.py`.
  - see `bench/docs/operator-diff-demo-runbook.md` for the currently validated
    scratch-harness proof path covering structural match, semantic identity
    mismatch, and capture digest mismatch.
- `run_reduction_order_counterexample.py`
  - runs multiple explicit command-stream variants of the same micro workload
    through Doe and Dawn, then compares the captured output bytes per variant
    instead of only asking whether one fixed command stream is stable.
  - this is the first metal-level counterexample lane:
    same fixed dot product, same inputs, different declared accumulation
    policy, distinct stable output bytes.
  - current bundled fixture:
    - `bench/fixtures/determinism/apple-metal-reduction-order-dot-product.json`
  - example:
    - `python3 bench/runners/run_reduction_order_counterexample.py --fixture bench/fixtures/determinism/apple-metal-reduction-order-dot-product.json --runs 3`
  - use the generated report to answer:
    whether alternate accumulation modes change bytes on the same exact micro
    workload, whether each policy is stable across repeats, and whether Doe and
    Dawn stay aligned for each named policy.
- `run_reduction_order_logit_flip.py`
  - promotes the same idea to a tiny logits operator:
    the runner executes three explicit accumulation policies for the same
    2-row matmul, captures the 2-logit output plus sampled token, and reports
    whether the winning row and sampled token flip when only the accumulation
    contract changes.
  - this is the operator-level bridge from numeric drift to token selection:
    same hidden state, same nominal logits op, different declared accumulation
    policy, different top token.
  - current bundled fixture:
    - `bench/fixtures/determinism/apple-metal-reduction-order-logit-flip.json`
    - `bench/fixtures/determinism/apple-metal-rmsnorm-slice-logit-flip.json`
  - example:
    - `python3 bench/runners/run_reduction_order_logit_flip.py --fixture bench/fixtures/determinism/apple-metal-reduction-order-logit-flip.json --runs 3`
    - `python3 bench/runners/run_reduction_order_logit_flip.py --fixture bench/fixtures/determinism/apple-metal-rmsnorm-slice-logit-flip.json --runs 3`
  - use the generated report to answer:
    whether alternate accumulation modes change logits bytes, whether those
    changed logits flip scalar argmax and sampled token, whether each policy is
    stable across repeats, and whether Doe and Dawn stay aligned for each named
    policy.
  - the `rmsnorm` family fixture is the current real operator-family promotion:
    first divergence is `rmsnorm.output`, the downstream selected token flips,
    and the exact-reference path stays on the tree/fast side.
- `run_real_lm_head_slice_hunt.py`
  - promotes the same numeric-sensitivity search onto a real prompt state:
    the runner harvests a real browser/Doppler prefill embedding plus logits,
    resolves real output rows from the model artifact, evaluates multiple
    accumulation contracts over that exact LM-head slice, and promotes the best
    case into both:
    - a reduction-order logit-flip receipt
    - a selective stable-rerun receipt
  - this is the first real prompt/operator/rerun bridge:
    same natural prompt state, same real LM-head rows, different declared
    accumulation policy, different selected token, then an explicit route
    decision over the real operator family.
  - current bundled fixture:
    - `bench/fixtures/determinism/apple-metal-real-lm-head-slice-hunt.gemma270m.red-go-stop-answer.json`
  - example:
    - `python3 bench/runners/run_real_lm_head_slice_hunt.py --fixture bench/fixtures/determinism/apple-metal-real-lm-head-slice-hunt.gemma270m.red-go-stop-answer.json --runs 3 --top-candidates 4`
  - the current flagship report is the explicit-choice traffic-light prompt:
    the real bounded `{ go, stop }` slice stays on ` go` under the f32
    policies, flips to ` stop` under `f16accum`, and the selective rerun route
    correctly prefers the stable serial policy on both Doe and Dawn.
- `export_numeric_fragility_corpus.py`
  - normalizes the current Apple Metal prompt-flip, policy-boundary, and
    operator-control evidence into one JSONL corpus plus a companion manifest.
  - the exporter keeps a stable row shape and now adds the token-level metrics
    needed to compare numeric fragility against uncertainty:
    - bounded-answer renormalized probability
    - bounded-answer surprisal (`-log p`) for the exact/reference token and the
      `f16accum` token
    - bounded-answer entropy and margin
    - global top-candidate context, including outsider lead versus the bounded
      pair
    - global reference-token surprisal when the source report persisted full
      logits; otherwise the row records why it is unavailable
  - route fields are intentionally split:
    - `routeExpectation`: hunt-derived expectation only, with explicit status
      (`hypothetical-from-hunt` vs `realized-in-promotion`)
    - `routeDecision`: realized route from a promoted rerun or policy artifact
  - promoted prompt rows now use the promoted hunt report as
    `sourceArtifactPath`; the earlier representative hunt artifact is preserved
    separately as `sourceSearchArtifactPath`
  - the prompt-flip rows are deduped by full prompt text across
    `prompt-choice` and `answer-set` candidates, while the curated
    `top-prefix-only` rows remain a separate lane.
  - example:
    - `python3 bench/runners/export_numeric_fragility_corpus.py`
  - current output root:
    - `bench/out/apple-metal-numeric-fragility-corpus/<timestamp>/`
  - use the manifest as the source of truth for the current corpus size and the
    current mix of:
    - `prompt-lm-head-flip`
    - `prompt-top-prefix-flip`
    - `policy-boundary`
    - `operator-control`
- `promote_numeric_fragility_signatures.py`
  - promotes the current numeric-fragility corpus into checked-in config for
    the contract side of numeric stability.
  - the promotion ladder is governed by:
    - `config/fragility-promotion-policy.json`
  - checked-in outputs are:
    - `config/promoted-fragility-catalog.json`
    - `config/fragility-signatures/promoted/*.json`
  - each signature is validated against:
    - `config/fragility-signature.schema.json`
  - example:
    - `python3 bench/runners/promote_numeric_fragility_signatures.py`
  - interpretation:
    - this freezes promoted bench evidence into a runtime-consumable config
      shape without claiming that the runtime already enforces it
    - native `matmul.logits` novelty is now exercised through the in-path
      runner; broader operator families and package/browser ordinary execution
      still remain future work
- `run_selective_stable_rerun_probe.py`
  - consumes a reduction-order source report and applies a versioned
    numeric-stability route policy instead of only stopping at "the bytes
    changed".
  - records the full governance path:
    first divergence op, fast-vs-stable digests, selected-token consequence,
    trigger checks, and the final route decision.
  - the route policy is now proof-linked:
    the report also records `proofArtifactPath`, `routeTaxonomyVersion`,
    explicit trigger/route proof links, and route-to-selection proof links
    from `config/numeric-stability-policy.json`.
  - current bundled fixture:
    - `bench/fixtures/determinism/apple-metal-selective-stable-rerun-logit-flip.json`
    - `bench/fixtures/determinism/apple-metal-selective-stable-rerun-attention-slice.json`
    - `bench/fixtures/determinism/apple-metal-selective-stable-rerun-rmsnorm-slice.json`
  - example:
    - `python3 bench/runners/run_selective_stable_rerun_probe.py --fixture bench/fixtures/determinism/apple-metal-selective-stable-rerun-logit-flip.json --source-report bench/out/apple-metal-reduction-order-logit-flip/<timestamp>/apple_metal_reduction_order_logit_flip.reduction-order-logit-flip.json`
  - use the generated report to answer:
    where the first sensitive divergence begins, whether the stable rerun
    restores the exact-reference top token, and whether the declared route
    policy should keep the fast or stable result.
  - the attention-slice fixture is the current real-operator-family negative
    control:
    it proves the pipeline can say "no first divergence, keep fast path"
    instead of forcing every named operator family into a false-positive wedge.
  - the `rmsnorm` fixture is the current real-operator-family `accept-fast`
    control:
    the operator is sensitive, the selected token changes, but the strict-
    serial rerun still loses to the exact-reference path, so the route keeps
    the tree/fast result.
- `run_determinism_probe.py`
  - runs explicit determinism stages against Doe and Dawn on the same
    host/backend using the existing semantic-operator artifact path.
  - supported modes are:
    - `receipt`: emit a one-run semantic capture receipt for the sampled-token
      boundary
    - `stable-token`: rerun a greedy sampling boundary and prove token-byte
      stability across runs
    - `stable-decode-step`: rerun a decode step and prove both final-logits and
      sampled-token byte stability across runs
  - the runner can infer semantic capture points directly from ordinary command
    streams, so the bundled fixtures no longer depend on hand-authored capture
    indices for sample-boundary probes.
  - captures are only accepted when semantic execution succeeded:
    if a captured operator reports any `execution.status` other than `ok`, the
    runner fails the lane instead of producing misleading stability receipts.
  - writes an annotated command stream plus per-run trace/meta/operator-manifest
    artifacts and a final report that separates:
    Doe repeated-byte stability, Dawn repeated-byte stability, and cross-lane
    byte equality.
  - for `stable-decode-step` reports, the runner also emits a `tieBreakAudit`
    section that derives the expected greedy token from the captured logits
    buffer (`lowest index among max logits`) and flags whether each lane's
    sampled token matches that sequencing rule.
  - current bundled fixtures are:
    - `bench/fixtures/determinism/apple-metal-greedy-sample-receipt.json`
      for the one-run `receipt` stage on the real `sample.wgsl`
      greedy-argmax kernel
    - `bench/fixtures/determinism/apple-metal-greedy-sample-clear-winner.json`
      for the `stable-token` stage on the real `sample.wgsl`
      greedy-argmax kernel with explicit non-zero logits
    - `bench/fixtures/determinism/apple-metal-gemma3-270m-decode1tok.json`
      for the `stable-decode-step` stage on a Gemma-shaped decode slice on the
      generated compat command stream
  - example:
    - `python3 bench/runners/run_determinism_probe.py --fixture bench/fixtures/determinism/apple-metal-greedy-sample-receipt.json`
    - `python3 bench/runners/run_determinism_probe.py --fixture bench/fixtures/determinism/apple-metal-greedy-sample-clear-winner.json`
    - `python3 bench/runners/run_determinism_probe.py --fixture bench/fixtures/determinism/apple-metal-gemma3-270m-decode1tok.json`
  - use the generated report to make narrow claims only:
    fixed-host, fixed-input byte stability for named probes; not universal LM
    determinism, not cross-platform determinism, and not automatically “more
    deterministic than Dawn”
- `run_real_logit_hunt.py`
  - harvests real final-logits receipts from Doppler's browser advanced API
    (`prefillWithLogits()` / `decodeStepLogits()`) against a real model
    artifact, then ranks prompt/step candidates by exact-max ties, greedy-token
    flips, byte drift, and top-2 margin.
  - uses `bench/executors/harvest-doppler-browser-logits.js` under the hood and
    now supports explicit browser repeat isolation through
    `browser.repeatIsolation`:
    - `reuse-page`: keep one page alive across repeats
    - `new-page`: open a fresh page for each repeat within one browser
    - `new-browser`: relaunch Chromium for each repeat
  - use `new-page` or `new-browser` when hunting real small-margin prompts; the
    older `reuse-page` mode is still useful as a lifecycle-bug detector but is
    not a safe default for determinism claims.
  - current bundled fixture:
    - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.json`
    - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.natural-stakes.json`
    - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.choice-primer.json`
    - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.choice-breadth.json`
    - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.seatbelt-safe-unsafe.json`
  - example:
    - `python3 bench/runners/run_real_logit_hunt.py --runs 3 --top-candidates 12`
    - `python3 bench/runners/run_real_logit_hunt.py --runs 3 --top-candidates 12 --persist-logits`
  - use the generated report to separate:
    real prompt/step candidates with small greedy margins from browser/model
    lifecycle faults that can otherwise masquerade as nondeterministic logits.
  - the dedicated `red-go-stop-answer` fixture is the current real source lane
    for the promoted LM-head slice above.
- `run_semantic_pair_hunt.py`
  - scans one or more real-logit hunt reports for semantically meaningful token
    pairs such as ` not` vs ` safe` or ` public` vs ` private`, then ranks the
    matches by pairwise logit gap and proximity to the current top token.
  - it now has two explicit input modes:
    - `--source-report`: the original hand-declared pair-fixture path
    - `--mined-report`: promote pair-agnostic mined cases into decode-state
      receipts without a handwritten pair list
  - emits a token-level decode-state recipe for each match:
    `promptTokenIds`, the already-decoded greedy prefix, and the exact
    `currentIds` sequence needed to reconstruct an equivalent decode boundary on
    the same model/runtime path.
  - bundled fixture:
    - `bench/fixtures/determinism/apple-metal-semantic-pair-hunt.gemma270m.json`
    - `bench/fixtures/determinism/apple-metal-semantic-pair-hunt.gemma270m.choice-breadth.json`
  - example:
    - `python3 bench/runners/run_semantic_pair_hunt.py --source-report bench/out/apple-metal-real-logit-hunt/<timestamp>/apple_metal_real_logit_hunt_gemma270m_choice_primer.real-logit-hunt.json --source-report bench/out/apple-metal-real-logit-hunt/<timestamp>/apple_metal_real_logit_hunt_gemma270m_natural_stakes.real-logit-hunt.json`
    - `python3 bench/runners/run_semantic_pair_hunt.py --mined-report bench/out/apple-metal-pair-agnostic-mine/<timestamp>/apple_metal_pair_agnostic_mine_gemma270m.pair-agnostic-mine.json`
  - use the generated report to answer:
    where the model already places meaningful alternatives near the top, and
    which exact decode states are worth carrying forward into sample-only
    stable-token probes.
- `run_pair_agnostic_pair_miner.py`
  - consumes one or more broad scout receipts from `run_real_logit_hunt.py` and
    mines plausible single-token answer pairs directly from each step's `topK`
    surface instead of requiring a predeclared pair library.
  - mining is gated by a tokenizer-aware bounded answer-set registry plus a
    versioned trigger-policy config, so the runner does not promote arbitrary
    numerically-close pairs.
  - the miner keeps explicit provenance on every promoted case:
    `candidateSetSource=mined-topk-v1`, canonical token IDs, source report path,
    source repeat index, prompt/phase/step identity, source logits
    artifact digest/path, `discoveryMode`, `promotionBucket`,
    `triggerPolicyId`, `triggerEvaluation`, and stage-specific stability.
  - the current bundled fixture is conservative by design:
    - `bench/fixtures/determinism/apple-metal-pair-agnostic-mine.gemma270m.json`
  - example:
    - `python3 bench/runners/run_pair_agnostic_pair_miner.py --source-report bench/out/apple-metal-real-logit-hunt/<timestamp>/apple_metal_real_logit_hunt_gemma270m_choice_breadth.real-logit-hunt.json --source-report bench/out/apple-metal-real-logit-hunt/<timestamp>/apple_metal_real_logit_hunt_gemma270m_seatbelt_safe_unsafe.real-logit-hunt.json --source-report bench/out/apple-metal-real-logit-hunt/<timestamp>/apple_metal_real_logit_hunt_gemma270m_high_stakes.real-logit-hunt.json`
  - use the generated report to answer:
    which prompt-bounded pairs are useful enough to promote into decode-state
    receipts without hardcoding the answer pair in advance.
  - zero promotions are a valid result:
    if the registry-gated pairs never survive the usefulness and stability
    filters, the report should stay empty instead of manufacturing a demo.
- `run_semantic_pair_mutation_search.py`
  - takes a promoted semantic-pair report, mutates only the shortlist, reruns a
    cheap real-logit scout over those prompt variants, and writes both:
    - a mutation-search report with promotions and negative controls
    - a companion mined-pair report containing only the improved cases
  - this keeps the later pipeline stages unchanged:
    `run_semantic_pair_hunt.py --mined-report ...` can consume the companion
    mined report directly, and the negative controls remain first-class
    artifacts instead of disappearing.
  - bundled fixture:
    - `bench/fixtures/determinism/apple-metal-semantic-pair-mutation-search.gemma270m.json`
  - example:
    - `python3 bench/runners/run_semantic_pair_mutation_search.py --source-report bench/out/apple-metal-semantic-pair-hunt/<timestamp>/apple_metal_pair_agnostic_mine_gemma270m.semantic-pair-hunt.json --case-count 3 --runs 1`
  - use the generated report to answer:
    whether small prompt edits actually preserve and improve a useful semantic
    pair, or whether they collapse into format/list tokens and should stay as
    negative controls.
  - mutation-derived promotions remain a separate provenance lane:
    they carry `discoveryMode=mutation-derived`,
    `promotionBucket=mutation-assisted`, and source prompt metadata instead of
    being mixed into natural discoveries.
- `run_sample_only_tie_break_probe.py`
  - reuses persisted real-logit hunt artifacts and synthesizes a minimal
    `sample.wgsl` command stream so Doe and Dawn can be compared on the same
    exact input logits bytes.
  - the fixture now also declares an explicit Doe stable-token receipt config
    under `doeStableToken`; the runner invokes
    `bench/executors/run-doe-stable-token.js` so each case carries a Doe
    helper receipt in addition to the raw Doe/Dawn sample receipts.
  - fixtures may also declare an optional `doeStableChoice` section; the
    runner invokes `bench/executors/run-doe-stable-choice.js` so each case can
    carry a bounded-policy ambiguity-resolution receipt alongside the raw and
    stable-token receipts.
  - fixtures may also declare an optional `doeReviewedChoice` section; the
    runner invokes `bench/executors/run-doe-reviewed-choice.js` so each case
    can carry an explicit reviewed-decision receipt alongside the raw,
    stable-token, and stable-choice receipts.
  - stable-choice receipts now include explicit policy provenance:
    `triggerPolicyId`, `candidateSetId`, and `candidateSetSource`.
  - reviewed-choice receipts keep the same trigger and candidate-set
    provenance, but add explicit decision provenance:
    `reviewerId`, optional decision IDs/refs, acceptance, and fallback reason.
  - keeps the same lane methodology as `run_determinism_probe.py`:
    one annotated command stream per case, repeated runs per lane, semantic
    token capture, per-lane stability summary, and cross-lane byte/token
    equality checks.
  - supports controlled mutations on the top-ranked logits before upload:
    - `as-captured`
    - `force-top2-exact-tie`
    - `force-top4-exact-tie`
    - `force-top1-wins-by-1ulp`
    - `force-top2-wins-by-1ulp`
    - `explicit_tokens_exact_tie`
      - ties an explicit semantic token set from the source report, selected by
        token IDs or token texts, at one `f32` ULP above the original global
        max so the chosen tokens control the greedy boundary
  - fixtures can now pin exact source cases with `sourceCases` instead of
    taking the first `N` candidates from the report
  - the runner audits those cases against a scalar `f32` argmax model
    (`cpu_f32_first_max`) so exact-tie stress cases can be separated from
    simple Doe-vs-Dawn parity.
  - the Doe stable-token receipt path uses the public `gpu.determinism.stableToken(...)`
    helper from `doe-gpu`, not an internal Python-only audit branch.
  - the repo-only Doe determinism executors now also emit adjacent zero-row
    `trace_meta` companions (`doe.stable-token.trace-meta.json`,
    `doe.stable-choice.trace-meta.json`, `doe.reviewed-choice.trace-meta.json`)
    whose `determinism` block carries the same policy registry path/version,
    policy IDs, trigger IDs, evaluator IDs, and proof theorem list as the
    public receipts.
  - bundled fixture:
    - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.gemma270m.json`
    - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.brakes-safe-unsafe.gemma270m.json`
    - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.driving-not-good.gemma270m.json`
    - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.patch-public-private.gemma270m.json`
    - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.red-go-stop.gemma270m.json`
    - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.snow-winter-summer.gemma270m.json`
    - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.seatbelt-not-safe.gemma270m.json`
  - example:
    - `python3 bench/runners/run_sample_only_tie_break_probe.py --source-report bench/out/apple-metal-real-logit-hunt/<timestamp>/apple_metal_real_logit_hunt_gemma270m.real-logit-hunt.json`
    - `python3 bench/runners/run_sample_only_tie_break_probe.py --fixture bench/fixtures/determinism/apple-metal-sample-only-tie-break.brakes-safe-unsafe.gemma270m.json --source-report bench/out/apple-metal-real-logit-hunt/<timestamp>/apple_metal_real_logit_hunt_gemma270m_choice_primer.real-logit-hunt.json`
    - `python3 bench/runners/run_sample_only_tie_break_probe.py --fixture bench/fixtures/determinism/apple-metal-sample-only-tie-break.seatbelt-not-safe.gemma270m.json --source-report bench/out/apple-metal-real-logit-hunt/<timestamp>/apple_metal_real_logit_hunt_gemma270m_seatbelt_safe_unsafe.real-logit-hunt.json`
  - use the generated report to answer three different questions:
    - do Doe and Dawn pick the same sampled token on the exact same logits?
    - does the real GPU sample kernel stay aligned with scalar CPU argmax
      semantics under forced exact-tie stress?
    - does Doe `stable-token` recover the scalar expected token on those same
      exact logits when the raw GPU sample kernel does not?
    - can Doe keep the bounded ambiguity detector fixed but switch the
      evaluator from a deterministic program (`stable-choice`) to an explicit
      reviewed decision (`reviewed-choice`) with a separate receipt?
    - can that exact-tie stress be expressed on a real prompt with meaningful
      answer tokens such as ` not` vs ` safe`, not just anonymous `topK`
      positions?
    - which semantic tie families actually differentiate on Apple Metal and
      which ones remain raw Doe/Dawn parity even under a controlled exact tie?
    - can Doe apply a separate bounded-policy `stable-choice` decision on a
      real near-ambiguous prompt without claiming that the underlying model or
      raw sampler became more deterministic?
  - if a refreshed source scout no longer keeps the bounded candidate set in
    `topK`, pin explicit token IDs in the fixture rather than silently
    broadening the source evidence.
- `run_package_determinism_receipt.py`
  - replays one persisted real-logit determinism case through the ordinary
    Node/package executor instead of the helper-only sample probe.
  - preserves semantic capture metadata in the package plan, captures the
    logits/token buffers through the normal readback path, and emits a real
    package `trace_meta` receipt whose `determinism` block matches the public
    `doe-gpu` policy contract.
  - use this runner when a helper/sample-only result needs to be re-proven on
    the actual package lane before it becomes part of a public claim.
  - bundled fixture:
    - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.pool-safe-unsafe.gemma270m.json`
  - example:
    - `python3 bench/runners/run_package_determinism_receipt.py --fixture bench/fixtures/determinism/apple-metal-sample-only-tie-break.pool-safe-unsafe.gemma270m.json --source-report bench/out/apple-metal-real-logit-hunt/<timestamp>/apple_metal_real_logit_hunt_gemma270m_policy_breadth.real-logit-hunt.json --prompt-id pool-safe-unsafe --phase prefill --step-index 0 --mutation-id as-captured --mode stable-choice`
  - fresh natural supporting package receipts:
    - `bench/out/apple-metal-package-determinism/20260328T212103Z/pool-safe-unsafe-prefill-as-captured-stable-token/pool-safe-unsafe-prefill-as-captured-stable-token.package-determinism.json`
    - `bench/out/apple-metal-package-determinism/20260328T212034Z/pool-safe-unsafe-prefill-as-captured-stable-choice/pool-safe-unsafe-prefill-as-captured-stable-choice.package-determinism.json`
    - `bench/out/apple-metal-package-determinism/20260328T212034Z/pool-safe-unsafe-prefill-as-captured-reviewed-choice/pool-safe-unsafe-prefill-as-captured-reviewed-choice.package-determinism.json`
- `cleanup_out.py`
  - prunes legacy untimestamped artifacts from `bench/out` and can optionally prune old timestamped run folders by retention window.
- `organize_out_by_timestamp.py`
  - migrates legacy timestamp-suffixed top-level artifacts into timestamp folders (`bench/out/<timestamp>/...`) for chronological directory listing.
- `backfill_run_manifests.py`
  - writes inferred `run_manifest.json` files for historical timestamp folders that predate manifest emission.
- `list_out_runs.py`
  - prints a concise chronological index of timestamp folders (`timestamp`, `scope`, `runType`, `status`, summary) using `run_manifest.json`.
- `visualize_dawn_vs_doe.py`
  - reads a `compare_dawn_vs_doe.py` report and writes a self-contained HTML visualization plus optional analysis JSON.
  - includes ECDF overlays, workload×percentile delta heatmap, KS statistic/p-value, Wasserstein distance, probability of superiority `P(left<right)`, and bootstrap CIs for delta `p50`/`p95`/`p99`.
- `claim_gate.py`
  - validates a comparison report against required claim contract fields (`claimabilityPolicy.mode`, `comparisonStatus`, `claimStatus`, per-workload claimability, and comparability-obligation schema/blocking-pass state) for blocking release CI gates.
  - validates comparability obligation IDs against the canonical contract in `config/comparability-obligations.json`.
  - validates claim-row hash linkage (`claimRowHash` + `claimRowHashChain`) across workload contract hash, config hash, benchmark policy hash, and trace-meta hash lists.
  - for claimable lanes, independently enforces positive required tail deltas (`p50`/`p95`/`p99` in release mode) and timed-sample floors per workload.
- `build_claim_rehearsal_artifacts.py`
  - builds machine-readable claim rehearsal artifacts from a compare report:
    claim gate result, tail-health table, timing-invariant audit, contract-hash manifest, and a rehearsal manifest linking all outputs.
- `build_claim_scope_report.py`
  - emits citation-safe claim scope artifacts from a compare report:
    per-workload status (`comparisonStatus`, `claimStatus`, comparability/claimability flags), selected-timing scope vs headline process-wall context, backend/profile metadata, and trace-meta/report paths.
  - fails fast when top-level report status is not explicitly claimable/comparable as required by CLI arguments.
- `cycle_gate.py`
  - validates active cycle contract hash locks (`workloadContract`, benchmark policy, compare config, substantiation policy), methodology invariants, and comparable/directional workload partition.
  - validates claim-lane report conformance + hash-link invariants, evaluates rollback criteria, and enforces artifact namespace policy (`bench/out/...` canonical vs `bench/out/scratch/...` diagnostics).
- `measure_runtime_footprint.py`
  - measures Doe-vs-Dawn runtime artifact footprint (`rawSizeBytes`, optional stripped size, dependency counts/list) and optional build wall times.
  - emits JSON + markdown reports suitable for embedded/runtime sizing evidence.
- `pipeline-concurrency-bench.py`
  - runs a repeated pipeline/concurrency command under configurable parallelism and emits p50/p95/max timing artifacts.
  - intended as the first evidence harness for async pipeline creation throughput, cold-start contention, and future single-flight/cache wins.
- `run_cts_subset.py`
  - executes a configured WebGPU CTS query subset and emits per-query pass/fail + wall-time artifacts (JSON + markdown).
  - query configs can now carry structured query metadata (`id`, `bucket`, `notes`) plus preflight requirements, so reports include per-bucket pass/fail counts instead of a flat raw-query list.
  - preferred Doe CTS config is `bench/fixtures/cts_subset.fawn-node.json` (literal current compatibility filename), which drives the vendored WebGPU CTS through Doe via `cts/fawn-node-gpu-provider.js`.
  - supports `--dry-run`, `--stop-on-fail`, and bounded query execution via `--max-queries`.
- `run_csl_governed_lane.py`
  - runs the non-hardware CSL smoke lane:
    fresh HostPlan lowering from the Gemma fixture -> simulator-plan materialization -> external simulator-driver invocation -> governed JSON/markdown report.
  - emits explicit compile/run/parity status without fabricating simulator trace output; blocked toolchain/runtime states remain diagnostic instead of silently passing.
  - accepts explicit environment/toolchain wiring when available:
    - `$DOE_CSL_SIM_EXECUTABLE` -> external driver
    - `$DOE_CSLC_EXECUTABLE` -> `cslc`
    - `$DOE_CSL_RUNTIME_EXECUTABLE` -> real simulator/runtime command
- `csl_governed_lane_gate.py`
  - validates governed CSL lane reports against schema and explicit parity/compile/run requirements.
  - intended for `run_blocking_gates.py --with-csl-governed-lane-gate` once the report path is available.
  - use `--require-compile-success` and `--require-run-success` once the SDK lane is available.
- `build_model_capacity_matrix.py`
  - builds a hardware×model capacity matrix artifact from measured AI workload/Doe runs, including status classes (`pass`, `fail`, `oom`, `unsupported`) and per-hardware max passable model size.
  - emits JSON + markdown summaries for explicit model-size ceiling disclosure.
- `run_market_readiness_bundle.py`
  - one-command orchestrator for release evidence packaging:
    release pipeline -> claim scope report -> runtime footprint -> CTS subset -> optional model-capacity matrix.
  - writes a manifest linking all generated artifacts and exits non-zero on any failed step.
- `check_full39_claim_readiness.py`
  - validates the full AMD Vulkan frontier-comparable matrix against strict done criteria (exact comparable workload identity from the canonical main catalog, `comparisonStatus=comparable`, `claimStatus=claimable`, and zero left unsupported/error counters).
  - the `full39` name is legacy; the script now derives the active frontier comparable set from `bench/workloads/workloads.amd.vulkan.json`.
  - prints worst p95/p99 tail regressions plus non-claimable workload reasons to accelerate tail-fix loops.
- `run_full39_evidence_bundle.sh`
  - post-run orchestrator for frontier-matrix claim-grade artifacts: readiness check -> blocking gates (pipeline/trace/correctness/schema + drop-in + claim) -> repeated claim windows + substantiation -> inventory and baseline refresh.
  - the `full39` name is legacy; the script now validates against the canonical AMD Vulkan main catalog.
- `generate_feature_benchmark_table.py`
  - builds a markdown table joining `config/webgpu-capability-inventory.json`, workload contracts, and Dawn filter mappings for Dawn-vs-Doe feature/benchmark coverage auditing.
  - emits both overall comparable-coverage and eligible-only comparable-coverage metrics; eligibility is config-driven via `benchmarkClass` (`comparable` vs `directional`) in `config/webgpu-capability-inventory.json`.
  - treats coverage `status=tracked` as spec-inventory-complete (audited/contracted) but not runtime-semantic implementation.
- `verify_smoke_gpu_usage.py`
  - validates AMD Vulkan smoke reports include explicit GPU probe evidence (`gpuMemoryProbeAvailable`, sample counts, and VRAM peak fields) on both sides.

Template placeholders:
`{commands}`, `{quirks}`, `{vendor}`, `{api}`, `{family}`, `{driver}`, `{workload}`, `{dawn_filter}`, `{trace_jsonl}`, `{trace_meta}`, `{extra_args}`.

Benchmark/report-producing scripts now timestamp outputs by default (`YYYYMMDDTHHMMSSZ`) and write artifacts under grouped per-run folders (`bench/out/<group>/<timestamp>/...`) to avoid clobbering, keep related runs together, and preserve chronological history inside each group. Use `--no-timestamp-output` when you intentionally need an exact fixed output path.

Each timestamped run folder now includes `run_manifest.json` with run metadata (`runType`, `config`, `fullRun`, `claimGateRan`, `dropinGateRan`, status fields).
Compare runs that finish but miss claimability now record `status=diagnostic` in the manifest while still exiting non-zero when claimability mode is enabled.
For performance/claim benchmarking, build `runtime/zig/zig-out/bin/doe-zig-runtime` with `zig build -Doptimize=ReleaseFast` before running compare lanes; the optimized build materially reduces the AMD Vulkan `upload_write_buffer_1kb` gap on this host, but the governed release lane still remains performance-bound on that row.

Ad-hoc/manual artifact names (for example `*layoutcheck*`, `*contractcheck*`, `tmp.*`) are routed to `bench/out/scratch/<timestamp>/...` so canonical runs stay clean.

Not every run folder contains HTML. Compare-report runs do (`dawn-vs-doe*.html`, default-on in release pipeline), while gate-only/trace-workspace runs may only contain JSON/NDJSON plus `run_manifest.json`.

Benchmark cube output follows the same discipline:

- timestamped run folder: `bench/out/cube/<timestamp>/`
- stable latest mirror: `bench/out/cube/latest/`
- current artifacts:
  - `cube.rows.json`
  - `cube.summary.json`
  - `cube.matrix.md`
  - `cube.dashboard.html` (HTML dashboard with inline SVG heatmaps)

## Artifact cleanup

```bash
# normalize existing legacy top-level timestamp-suffixed artifacts into grouped run folders
python3 bench/organize_out_by_timestamp.py

# backfill historical run manifests where missing
python3 bench/backfill_run_manifests.py

# show what would be removed
python3 bench/tools/cleanup_out.py --dry-run

# remove legacy untimestamped bench/out entries
python3 bench/tools/cleanup_out.py

# scratch namespace holds manual/ad-hoc outputs
ls bench/out/scratch

# show a readable run index across grouped timestamp folders
python3 bench/tools/list_out_runs.py --limit 25

# additionally prune timestamped artifacts older than 14 days
python3 bench/tools/cleanup_out.py --retention-days 14
```

### Retention policy

- `bench/out/scratch/` directories are ephemeral and can be cleaned at any time.
- Timestamped directories under `bench/out/{backend}/` (e.g. `bench/out/amd-vulkan/`, `bench/out/apple-metal/`) are evidence artifacts and should be retained for audit and trend analysis.
- The latest artifact per lane is authoritative; older timestamped runs in the same lane are historical evidence and should not be deleted without explicit retention-window pruning via `cleanup_out.py --retention-days`.
- Ad-hoc directories (e.g. `bench/out/node-doe-vs-dawn-*`) follow the same evidence retention rules as backend lanes.
- Do not manually delete benchmark outputs outside of `bench/out/scratch/` without running `cleanup_out.py` to preserve manifest and inventory consistency.

## Workload presets

- `bench/workloads/specialized/workloads.generic.json` defines the generic replay workload view, default profiles, and command seed artifacts.
- workload IDs must follow the immutable naming contract from `bench/docs/benchmark-writing-guide.md`:
  `domain_subject_shape_variant` (status-free, no lifecycle/maturity prefixes).
- each workload includes `comparable` to declare whether mapping quality is apples-to-apples (`true`) or directional (`false`).
- directional workloads may include `directionalReason` to distinguish incumbent limits (`dawn_limit`, `dawn_missing_contract`, `dawn_no_execution`) from transferability or host-only issues (`path_asymmetry`, `host_instability`, `methodology_gap`).
- workloads may set `allowLeftNoExecution: true` to allow strict comparability for deterministic feature-gated paths when left runtime reports unsupported/skipped execution evidence and zero execution errors.
- each workload can include `default: false`; these extended workloads are skipped unless `--include-extended-workloads` or explicit `--workload-filter` is provided.
- workloads are tagged with `domain` and `comparabilityNotes` for report transparency.
- directional workloads that are likely parity-promotion targets can declare `comparabilityCandidate` metadata.
- use `--workload-cohort comparability-candidates` to isolate that candidate set for directional parity work (requires `--include-noncomparable-workloads`).
- use `--workload-cohort doe-advantage` to isolate governed directional Doe-vs-Dawn rows; this keeps the same strict operation timing basis but reports non-claimable incumbent-limited evidence separately from apples-to-apples lanes.
- canonical cross-surface workload identity now lives in `bench/workloads/metadata/workload-registry.json`.
- backend-native execution contracts still live in `bench/workloads*.json`.
- canonical source of workload intent is `bench/workloads/metadata/backend-workload-catalog.json`.
- generated workload artifacts are `bench/workloads*.json`, `bench/workloads/metadata/workload-overlap-map.json`, and `bench/workloads/metadata/workload-origin-map.json`.
- catalog refresh is [below](#workload-catalog-refresh).

## Workload catalog refresh

Use this exact sequence for any workload intent change:

1. Edit workload intent only in `bench/workloads/metadata/backend-workload-catalog.json`.
2. Regenerate all generated artifacts.
3. Verify generated outputs are canonical and drift-free.
4. Run catalog invariants checks.

```bash
python3 bench/tools/generate_backend_workloads.py
python3 bench/tools/generate_workload_overlap_map.py
python3 bench/tools/generate_backend_workloads.py --emit-workload-origins bench/workloads/metadata/workload-origin-map.json
python3 bench/tools/generate_backend_workloads.py --verify
python3 bench/tools/generate_workload_overlap_map.py --verify
python3 bench/tests/test_backend_workload_catalog.py
```

`test_backend_workload_catalog.py` is an optional invariants check for schema and expected IDs.

Rules:

- do not hand-edit files matching `bench/workloads*.json`; they are generated views.
- keep lane manifests and overlap/origin artifacts in sync with the catalog in the same change.
- do not run release compares or gate-only runs until regenerate + verify steps pass.
- if workload IDs or contract fields change, rerun the workflow before publishing evidence.
- backend-native execution contracts still live in `bench/workloads*.json`.
- Node/Bun package execution stays in `bench/package-compare/node/workloads.js`.
- registry alias normalization still lands in `bench/workloads/metadata/workload-registry.json` and canonicalizes package IDs like `buffer_upload_1kb` to `upload_write_buffer_1kb`.
- D3D12 managed lane files are also generated:
  `bench/workloads/workloads.local.d3d12.json` and `bench/workloads/workloads.local.d3d12.smoke.json`.
- `bench/workloads/workloads.local.d3d12.json` is the canonical D3D12 catalog. Strict D3D12 compare/release lanes select the governed comparable subset from that file via `selector.cohorts=["governed"]` and `selector.benchmarkClass=["comparable"]`.
- D3D12 preset configs now live in: `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.compare-dev.json`, `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.compare.json`, `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.frontier.json`, `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.explore.json`, `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.release.json`, and `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.smoke.json`.
- Windows D3D12 host workflow remains: `python3 bench/runners/preflight_d3d12_host.py --json`, `python3 bench/runners/run_local_d3d12_lane.py`.
- current comparable default matrix is upload scaling: `buffer_upload_{1kb,64kb,1mb,4mb,16mb}`.
- exploration domains include render/draw, shader/pipeline, texture-raster, and compute suites that are not yet in the governed comparable cohort.

## Dawn-vs-Doe example

Dawn does not publish a dedicated single-purpose `dawn-cli` binary. Use the benchmark
binary built from source (`dawn_perf_tests`) and a filter mapping by workload.

Build Dawn in this repo:

```bash
python3 bench/bootstrap_dawn.py \
  --source-dir bench/vendor/dawn \
  --build-dir bench/vendor/dawn/out/Release \
  --build-system gn \
  --branch main \
  --targets dawn_perf_tests \
  --parallel 8
```

```bash
python3 bench/native-compare/compare_dawn_vs_doe.py \
  --left-command-template "env LD_LIBRARY_PATH=bench/vendor/dawn/out/Release:$LD_LIBRARY_PATH runtime/zig/zig-out/bin/doe-zig-runtime --commands {commands} --quirks {quirks} --vendor {vendor} --api {api} --family {family} --driver {driver} --backend native --execute --trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta} {extra_args}" \
  --right-command-template "python3 bench/native-compare/dawn_benchmark_adapter.py --dawn-state bench/fixtures/dawn_runtime_state.json --dawn-filter {dawn_filter} --dawn-filter-map bench/dawn_workload_map.json --workload {workload} --dawn-extra-args --backend=vulkan --dawn-extra-args --adapter-vendor-id=0x1002 --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}" \
  --comparability strict \
  --require-timing-class operation \
  --resource-probe rocm-smi \
  --resource-sample-ms 100 \
  --resource-sample-target-count 104 \
  --iterations 3 \
  --warmup 1 \
  --out bench/out/dawn-vs-doe.json
```

Run broader engineering slices:

```bash
python3 bench/native-compare/compare_dawn_vs_doe.py \
  --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.explore.json \
  --workload-filter compute_workgroup_atomic_1024,compute_workgroup_non_atomic_1024,compute_matvec_32768x2048_f32,compute_matvec_32768x2048_f32_swizzle1,compute_matvec_32768x2048_f32_workgroupshared_swizzle1,pipeline_compile_stress,render_draw_throughput_baseline,texture_sampling_raster_baseline \
  --out bench/out/dawn-vs-doe.amd.vulkan.explore.slice.json
```

With Doe's default binary path:

```bash
python3 bench/native-compare/compare_dawn_vs_doe.py \
  --right-name "chromium-dawn" \
  --right-command-template "/path/to/dawn-wrapper {commands} --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}"
```

## Comparability guardrails

`compare_dawn_vs_doe.py` marks each workload as comparable/non-comparable and can fail hard:

- `--comparability strict` (default): exit non-zero when timing classes are mixed or mismatched.
- strict mode also exits non-zero when a selected workload contract is explicitly marked non-comparable (`comparable=false`).
- comparability evaluation is emitted as machine-checkable obligations per workload (`comparability.obligations` with `blockingFailedObligations`), and comparability status is derived from blocking-obligation pass/fail (not only free-form reason text).
- `--require-timing-class operation` (default): require operation-level timings on both sides.
- use `--require-timing-class process-wall` only for diagnostic end-to-end overhead studies.
- `--allow-left-no-execution`: opt out if left trace-meta has no `executionSuccessCount`/`executionRowCount`.
- workload-level `allowLeftNoExecution: true` provides the same opt-out per workload contract and still requires explicit unsupported/skipped execution evidence when no successful execution samples are present.
- strict mode rejects samples with runtime execution failures (`executionErrorCount > 0`) on either side.
- Dawn adapter now fails fast when a gtest filter matches zero tests (`Running 0 tests` / filter no-match warning) so startup-only runs cannot be reported as comparable timings.
- non-comparable workload mappings are excluded by default using `workloads.json` `comparable: false`.
- use `--include-noncomparable-workloads` only for directional investigation runs.
- `--workload-cohort comparability-candidates` filters to workloads with `comparabilityCandidate.enabled=true`; this does not promote those workloads to strict comparable lanes.
- `--workload-cohort doe-advantage` filters to workloads with `benchmarkClass=directional`; these runs are governed Doe-vs-Dawn diagnostics and must not be presented as strict comparable claims.
- non-default workload entries are excluded unless `--include-extended-workloads` is set.
- strict mode now rejects contract-domain workloads as comparable unless explicitly promoted by contract policy.
  for guarded contract domains (`pipeline-async`, `p0-resource`, `p0-compute`, `p0-render`, `p1-capability`,
  `p1-resource-table`, `p1-capability-macro`, `p2-lifecycle`, `p2-lifecycle-macro`, `surface`), promotion
  requires `applesToApplesVetted=true` in workload config.
- strict upload comparability now preflights the executed `doe-zig-runtime` binary:
  it must expose `--upload-buffer-usage` and `--upload-submit-every`, reject invalid values for both flags, and not be older than key upload/runtime Zig sources (`runtime/zig/src/main.zig`, `runtime/zig/src/execution.zig`, `runtime/zig/src/wgpu_commands.zig`, `runtime/zig/src/webgpu_ffi.zig`).
  when a workload contract sets `--queue-wait-mode`, strict preflight also requires runtime support and validation for `--queue-wait-mode process-events|wait-any`.
- strict render comparability now selects encode-only operation timing on the Doe side for workload domains
  `render` and `render-macro` (`timingSource=doe-execution-encode-ns`) when encode is a plausible share of total execution.
  render-bundle workloads use total execution timing because bundle encode timing proved scope-asymmetric on Apple Metal.
- claimability reliability mode is available:
  `--claimability local|release` enforces sample-floor and positive-tail checks for claimable speed reports.
  use `--claim-min-timed-samples N` to override mode defaults loaded from `config/benchmark-methodology-thresholds.json` (`claimabilityDefaults.localMinTimedSamples`, `claimabilityDefaults.releaseMinTimedSamples`).
  claimability failures return non-zero exit status (`3`) and report `claimStatus=diagnostic`.
  workloads whose selected timing scope is `narrow-hot-path` keep `deltaPercent` as an engineering diagnostic, but claimability now evaluates `timingInterpretation.workloadUnitWall.deltaPercent` when that full workload-unit metric is available. `workloadUnitWall` is normalized by `commandRepeat` and `timingNormalizationDivisor`, so repeat-asymmetric lanes still compare one workload unit to one workload unit.
- trace replay gate supports semantic parity lanes:
  `bench/gates/trace_gate.py --semantic-parity-mode auto|required`.
  use `required` only for runtime-to-runtime parity artifacts (for example Doe vs Dawn traces), because Dawn comparison traces are not semantic-envelope compatible.
- optional resource profiling is available via `--resource-probe rocm-smi` and is applied equally to both sides.
- when resource probe is enabled, strict comparability also checks probe quality:
  use fixed `N vs N` probing via `--resource-sample-target-count N`.
  strict mode requires `N > 0`; both sides must match `N` and must not be truncated.

Reliability guardrails for performance claims:

- strict comparability is necessary but not sufficient; claimable "faster" runs also need reliability checks.
- use at least 7 timed samples per side for local claims (`iterations - warmup >= 7`); target 15+ for release/CI claims.
- speed claims must be positive in tails, not only median:
  require positive `deltaPercent` at least for `p50` and `p95` (and `p99` for release/CI claims).
- if percentile signs are mixed or tails are negative, classify as diagnostic even when comparability is green.
- for upload claims, mixed-scope derived timing sources are not apples-to-apples; strict comparability now marks these runs non-comparable and claimability marks them diagnostic.

Quick reliability recheck pattern:

```bash
python3 bench/native-compare/compare_dawn_vs_doe.py \
  --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.compare.json \
  --workload-filter upload_write_buffer_64kb \
  --iterations 10 \
  --warmup 1 \
  --out bench/out/dawn-vs-doe.64kb.recheck.json
```

Timing classes:

- `operation`: `doe-execution-dispatch-window-ns`, `doe-execution-encode-ns`, `doe-execution-total-ns`, `doe-execution-row-total-ns`, `doe-trace-window`, `dawn-perf-wall-time`
- `process-wall`: `wall-time`

Process-wall comparability policy:

- when `--require-timing-class process-wall` is set, `compare_dawn_vs_doe.py` forces both sides to use outer command wall-time for measurement selection (no trace-meta substitution).
- if trace-meta also reports `timingSource=wall-time`, it is treated as auxiliary metadata and not as the primary timing value.
- process/resource sampling avoids fixed sleep quantization for open-ended runs by waiting on process completion with timeout polling.
- per-workload timing normalization divisors (`leftTimingDivisor`/`rightTimingDivisor`) are only applied in non-process-wall timing modes; process-wall runs use a normalization divisor of `1.0`.
- strict comparable workloads can also declare `strictNormalizationUnit` when the comparable unit is not raw command-row count:
  - `dispatch`: divisor must match repeated dispatch count
  - `cycle`: divisor must match repeated full-workload cycles
  - default/omitted: divisor must match repeated command-row count
  strict compare fails fast when the configured divisor and trace-derived physical-op count disagree for the declared unit.

Use `process-wall` only for startup/runtime-overhead studies, not per-op claims.

## Resource Bench (1:1)

`compare_dawn_vs_doe.py` can capture resource metrics for both sides from the same external source:

- `processPeakRssKb`: per-run peak process RSS (`/usr/bin/time` max-RSS when available, with `/proc/<pid>/status` sampling fallback).
- `gpuVramUsed{Before,After,Peak}Bytes` and `gpuVramDeltaPeakFromBeforeBytes`:
  sampled from `rocm-smi --showmeminfo vram --json` when `--resource-probe rocm-smi` is enabled.

Use `--resource-sample-target-count N` to force fixed-count resource probing (`N vs N`) per run.
If a side runs longer than the probe budget, strict comparability fails with a truncation reason.

This is a 1:1 contract because the probe is outside both runtimes and identical for Dawn and Doe.
Interpret VRAM deltas as device-level signals (global GPU usage), not isolated per-process accounting.

## What Is Being Tested

- default comparable Dawn-vs-Doe runs currently test upload throughput scaling with
  `buffer_upload_{1kb,64kb,1mb,4mb,16mb}`.
- each workload is timed at operation-level when available:
  Dawn adapter uses benchmark `*RESULT ... wall_time` samples and takes median;
  Doe timing source is selected by `compare_dawn_vs_doe.py` policy from trace metadata
  (`executionGpuTimestampTotalNs` -> `executionEncodeTotalNs+executionSubmitWaitTotalNs` -> `executionTotalNs`)
  with fallback to trace-window/wall-time when required fields are unavailable.
  In strict operation mode, webgpu-ffi execution samples must resolve to native execution-span timing
  sources (`doe-execution-*`); fallback timing is treated as non-comparable.
  tiny dispatch-window timings (`<minDispatchWindowNsWithoutEncode` and `<minDispatchWindowCoveragePercentWithoutEncode` of `executionTotalNs`) are rejected as bookkeeping noise whenever `executionTotalNs` is available, and `executionTotalNs` is used instead (`dispatchWindowSelectionRejected` in timing metadata).
  when ignore-first is enabled and applied, source is reported as `doe-execution-row-total-ns+ignore-first-ops`.
- compare reports now also emit `timingInterpretation` per workload:
  - `selectedTiming` describes what `deltaPercent` actually measures (`operation-total`, `operation-encode`, `process-wall`, etc.).
  - `workloadUnitWall` reports the timed-command process-wall view for the full workload unit, normalized to one workload unit via `commandRepeat` and `timingNormalizationDivisor`.
  - when `selectedTiming.scopeClass=narrow-hot-path`, `deltaPercent` stays a phase-specific diagnostic while claimability uses `workloadUnitWall.deltaPercent` for full workload-unit evaluation when available.
- per-workload timing normalization is config-driven via `leftTimingDivisor` / `rightTimingDivisor`
  in `workloads.json` (matvec uses `leftTimingDivisor=100` and `rightTimingDivisor=1` because Dawn already reports per-dispatch via `iterationsPerStep=100`).
  repeat-asymmetric benchmark runs also normalize counter-derived operation totals and workload-unit wall by `commandRepeat`, so `repeat=100` vs `repeat=1` still compares a single workload unit on both sides.
- non-comparable mappings can be explicitly flagged in workload contracts and excluded by default.

Extended workload domains now include:

- render/draw throughput and state-set variants (`DrawCallPerf` mappings for base, dynamic bind-group, redundant pipeline/bind-group, draw-indexed proxy, and render-bundle dynamic variants).
- shader compile/pipeline stress (`ShaderRobustnessPerf` mapping, comparable, fixed single-test filter + per-step normalization).
- texture/raster and texture API contract workloads (`SubresourceTrackingPerf` mappings) including explicit sampler create/destroy, queue write texture, texture query assertions, and texture destroy lifecycle commands.
- async pipeline diagnostics and most P0/P1/P2 API contracts are directional-only in the AMD extended matrix unless/until a directly matched Dawn contract is available.
- promoted macro contracts now treated as strict comparable include `render_draw_throughput_200k`, `texture_sampler_write_query_destroy_500`, `resource_table_immediates_500`, and `render_pixel_local_storage_barrier_500`.
- hard-gated pilot promotions now treated as strict comparable include `render_multidraw` and `render_multidraw_indexed` (`applesToApplesVetted=true`).
- hard-gated contract promotions now also include `resource_lifecycle` and `compute_indirect_timestamp` (`applesToApplesVetted=true`).
- `surface_presentation` is directional-only (`comparable=false`) because Dawn perf coverage does not expose a matching create/release-surface benchmark contract.
- AMD native Vulkan now executes `surface_presentation` through a Doe-owned
  headless surface lifecycle/present path, and executes `resource_table_immediates`
  / `render_pixel_local_storage_barrier` through explicit native emulation when
  the workload contract opts into `featurePolicy=emulate_when_unavailable`.
- `compute_concurrent_execution_single` is the strict comparable replacement for Dawn `ConcurrentExecutionTest ... RunSingle`.
- compute kernels matched to Dawn compute suites: `WorkgroupAtomicPerf` (atomic/non-atomic) and `MatrixVectorMultiplyPerf` (Rows=32768, Cols=2048, F32/F32 Naive).
  Matvec variants in config:
  `compute_matvec_32768x2048_f32` (Naive Swizzle=0),
  `compute_matvec_32768x2048_f32_swizzle1` (Naive Swizzle=1),
  `compute_matvec_32768x2048_f32_workgroupshared_swizzle1` (WorkgroupShared Swizzle=1).
  Doe matvec command files set `kernel_dispatch.repeat=100` to match Dawn's `kNumDisptaches=100` step structure.

Use report `domain`, `workloadComparable`, and `comparabilityNotes` fields to separate
strict claimable slices from engineering diagnostics.

## Release hard gate (mandatory)

Release CI should treat replay validation as a blocking gate.
After each `compare_dawn_vs_doe.py` run, fail CI if schema, correctness, or replay
validation fails. For claimable release statements, also fail CI unless
the report is explicitly `claimability.mode=release`, `comparisonStatus=comparable`,
and `claimStatus=claimable`. Then generate an HTML visualization artifact:

```bash
# canonical one-command release pipeline:
python3 bench/runners/run_release_pipeline.py \
  --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json \
  --strict-amd-vulkan \
  --trace-semantic-parity-mode auto \
  --with-claim-gate
# emits claim rehearsal artifacts next to the report by default:
# <report>.claim-rehearsal.{claim-gate-result,tail-health,timing-invariant-audit,contract-hash-manifest,manifest}.json

# drop-in compatibility + benchmark suite against a built shared-library artifact:
python3 bench/drop-in/dropin_gate.py \
  --artifact runtime/zig/zig-out/lib/libwebgpu_doe.<so|dylib> \
  --report bench/out/dropin_report.json

# optional standalone drop-in benchmark visualization (micro vs end-to-end sections):
python3 bench/drop-in/visualize_dropin_benchmark.py \
  --report bench/out/dropin_benchmark_report.json \
  --out bench/out/dropin_benchmark_report.html

# run release pipeline and include drop-in gating:
python3 bench/runners/run_release_pipeline.py \
  --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json \
  --strict-amd-vulkan \
  --trace-semantic-parity-mode auto \
  --with-dropin-gate \
  --dropin-artifact runtime/zig/zig-out/lib/libwebgpu_doe.<so|dylib> \
  --with-claim-gate

# optional repeated release windows for trend evidence:
python3 bench/runners/run_release_claim_windows.py \
  --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json \
  --windows 5 \
  --strict-amd-vulkan \
  --trace-semantic-parity-mode auto \
  --with-dropin-gate \
  --dropin-artifact runtime/zig/zig-out/lib/libwebgpu_doe.<so|dylib> \
  --with-substantiation-gate \
  --substantiation-policy config/substantiation-policy.json
# disable per-window claim rehearsal artifacts only when intentionally running diagnostics:
#   --no-with-claim-rehearsal-artifacts

# optional standalone substantiation gate from existing window summaries/reports:
python3 bench/substantiation_gate.py \
  --policy config/substantiation-policy.json \
  --summary bench/out/release-claim-windows.json

# tested-profile inventory database + simple dashboard:
python3 bench/tools/build_test_inventory_dashboard.py \
  --report-glob "bench/out/**/dawn-vs-doe*.json"

# baseline trend package (JSON + markdown):
python3 bench/tools/build_baseline_dataset.py \
  --report-glob "bench/out/**/dawn-vs-doe*.json"

# optional visualization after the pipeline report exists:
python3 bench/native-compare/visualize_dawn_vs_doe.py --report bench/out/dawn-vs-doe.amd.vulkan.release.json --out bench/out/dawn-vs-doe.amd.vulkan.release.html
# optional machine-readable distribution analysis:
python3 bench/native-compare/visualize_dawn_vs_doe.py --report bench/out/dawn-vs-doe.amd.vulkan.release.json --analysis-out bench/out/dawn-vs-doe.amd.vulkan.release.distribution.json
```

## Building dawn_perf_tests

Use the upstream source:

- https://dawn.googlesource.com/dawn (canonical mirror: https://github.com/google/dawn)

Prerequisites:

- `git`
- `cmake` (3.21+ recommended) when using `--build-system cmake`
- `depot_tools` (`gn`, `autoninja`) when using `--build-system gn`
- working C/C++ compiler + linker

If `gn` is missing, install depot_tools and re-run:

```bash
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git ~/depot_tools
export PATH="$HOME/depot_tools:$PATH"
```

Or point scripts at explicit binaries:

```bash
python3 bench/bootstrap_dawn.py --build-system gn --gn-bin /path/to/gn --ninja-bin /path/to/ninja ...
```

Preferred bootstrap flow (run from this repo):

```bash
python3 bench/bootstrap_dawn.py --build-system gn --targets dawn_perf_tests
```

If bootstrap fails with:

```text
Could not find gn executable at: .../buildtools/.../gn/gn
```

run the same command again; this repo now auto-populates `buildtools` from Dawn’s `DEPS` and
attempts a CIPD install of GN.

If your environment cannot write `bench/vendor/dawn/buildtools`, use explicit standalone
binaries.

If this exact message persists:

```text
gn.py: Unable to find gn in your $PATH
gn.py: Could not find gn executable at: .../buildtools/.../gn/gn
```

this usually means the `depot_tools` wrapper cannot initialize itself. Use a dedicated standalone gn for this step:

```bash
brew install gn ninja
python3 bench/bootstrap_dawn.py \
  --build-system gn \
  --gn-bin $(which gn) \
  --ninja-bin $(which ninja) \
  --source-dir bench/vendor/dawn \
  --build-dir bench/vendor/dawn/out/Release \
  --targets dawn_perf_tests \
  --parallel 8
```

Then rerun with the normal command (explicit gn args are optional once cache is warm):

```bash
python3 bench/bootstrap_dawn.py --build-system gn --targets dawn_perf_tests
```

For an already checked-out Dawn tree, you can also run manifest-only after a successful first bootstrap:

```bash
python3 bench/bootstrap_dawn.py --manifest-only --build-system gn --targets dawn_perf_tests
```

You can disable bootstrap of Dawn buildtools if you prefer:

```bash
python3 bench/bootstrap_dawn.py --build-system gn --skip-gn-bootstrap ...
```

That produces `bench/vendor/dawn/out/Release/dawn_perf_tests` (or your configured build dir)
and writes `bench/fixtures/dawn_runtime_state.json`.

Once built, discover test names and then wire one of them through `dawn_workload_map.json`:

```bash
bench/vendor/dawn/out/Release/dawn_perf_tests --gtest_list_tests
bench/vendor/dawn/out/Release/dawn_perf_tests --gtest_filter=DrawCallPerf.Run/Vulkan__e_skip_validation
```

`dawn_workload_map.json` in this directory holds workload-to-filter mappings.

## Dawn state artifact

`bench/fixtures/dawn_runtime_state.json` is emitted by `bootstrap_dawn.py` and records the checkout path, branch, build type, generator, and resolved binary paths.

## v0 Intent

The scripts are minimal harnesses to establish deterministic I/O contracts early.
They are expanded into real GPU benchmark/test runners as implementation matures.

## Dawn filter resolution policy (fail-fast by default)

`dawn_benchmark_adapter.py` now treats filter selection as an explicit contract:

- Explicit `--dawn-filter` always wins.
- Otherwise the adapter reads `--dawn-filter-map` at `filters.<workload>` only (no implicit default key fallback).
- Autodiscovery is **disabled by default**.
- Autodiscovery runs only when the selected map value is the literal token `@autodiscover`.
- If no filter is resolved and autodiscovery was not explicitly requested, the adapter exits non-zero.

This prevents silent fallback behavior and avoids reporting non-comparable startup timings as valid benchmark results.

### Opt-in autodiscovery

Use `@autodiscover` in your map only where you want dynamic filter selection:

```json
{
  "schemaVersion": 1,
  "filters": {
    "upload_write_buffer_1kb": "@autodiscover"
  }
}
```

### Explicit mapping (no autodiscovery)

```json
{
  "schemaVersion": 1,
  "filters": {
    "upload_write_buffer_1kb": "BufferUploadPerf.Run/Vulkan_AMD_Radeon_Graphics__RADV_GFX1151__WriteBuffer_BufferSize_1KB"
  }
}
```

### Hard-fail guardrails in adapter

Adapter exits non-zero when any of the following occur:

- requested adapter backend/vendor does not exist in detected Dawn adapters
- gtest filter matches zero tests (`Running 0 tests` or no-match warning)
- selected benchmark test is skipped/unsupported (for example `Info: Test unsupported:`)

These failures are intentional and indicate the run is not comparable.

## Config-first runner (recommended)

`compare_dawn_vs_doe.py` supports a JSON config so you do not need to pass long placeholder-heavy templates inline.

Use:

```bash
python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.example.json
```

Config fields (CLI-compatible, config-first):

```json
{
  "workloads": "bench/workloads/specialized/workloads.generic.json",
  "left": {
    "name": "doe",
    "commandTemplate": "env LD_LIBRARY_PATH=bench/vendor/dawn/out/Release:$LD_LIBRARY_PATH runtime/zig/zig-out/bin/doe-zig-runtime --commands {commands} --quirks {quirks} --vendor {vendor} --api {api} --family {family} --driver {driver} --backend native --execute --trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta} {extra_args}"
  },
  "right": {
    "name": "dawn",
    "commandTemplate": "python3 bench/native-compare/dawn_benchmark_adapter.py --dawn-state bench/fixtures/dawn_runtime_state.json --dawn-filter-map bench/dawn_workload_map.json --workload {workload} --dawn-extra-args=--backend=vulkan --dawn-extra-args=--adapter-vendor-id=0x1002 --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}"
  },
  "run": {
    "iterations": 3,
    "warmup": 1,
    "out": "bench/out/dawn-vs-doe.ryzen.json",
    "workspace": "bench/out/runtime-comparisons.ryzen",
    "workloadCohort": "all"
  },
  "comparability": {
    "mode": "strict",
    "requireTimingClass": "operation",
    "allowLeftNoExecution": false
  },
  "resource": {
    "probe": "none",
    "sampleMs": 100,
    "sampleTargetCount": 0
  }
}
```

Notes:

- `right.commandTemplate` is required (either via CLI or config).
- CLI flags still work and keep precedence when explicitly provided.
- When `--config` is present, missing CLI fields are filled from config.

## AMD + Vulkan preset (config-driven)

A ready-to-run AMD Vulkan governed compare preset is now included:

- config: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.compare.json`
- workloads: `bench/workloads/workloads.amd.vulkan.json`
- Dawn filter map: `bench/dawn_workload_map.amd.autodiscover.json`
- AMD quirks list (empty/no-op baseline): `examples/quirks/amd_radv_noop_list.json`

Additional AMD Vulkan presets:

- compare-dev: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.compare-dev.json`
- release claim mode on the governed comparable cohort: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json`
- comparable-only frontier diagnostics outside the governed cohort: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.frontier.json`
- mixed comparable/directional engineering runs: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.explore.json`
- diagnostic smoke sanity set: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.smoke.json`

Preset behavior:

- Doe side is AMD-profiled in workload fields (`vendor=amd`, `api=vulkan`, `family=gfx11`, `driver=24.0.0`). The default Doe runtime currently expects `driver` to be a semver string.
- Dawn side is constrained to Vulkan + AMD vendor id (`--backend=vulkan`, `--adapter-vendor-id=0x1002`).
- Dawn filter selection is config-controlled and explicit via `@autodiscover` in the map.
- Autodiscovery is opt-in only (from map token `@autodiscover`); otherwise adapter fails fast.
- Compare/release presets use strict operation-level timing (`mode=strict`, `requireTimingClass=operation`).
- strict mode will fail fast if the configured Doe runtime binary does not support upload knobs or appears stale relative to upload/runtime Zig sources.
- Governed upload workloads are configured for strict apples-to-apples matching against Dawn `BufferUploadPerf WriteBuffer`:
  `leftUploadBufferUsage=copy-dst`, `leftIgnoreFirstOps=1`, and explicit per-size
  `leftCommandRepeat`/`leftTimingDivisor`/`leftUploadSubmitEvery` values in
  `bench/workloads/workloads.amd.vulkan.json`.

Run from `` directory:

```bash
python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.compare.json
```

Additional AMD Vulkan runs:

```bash
# diagnostic smoke sanity
python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.smoke.json

# governed release claim matrix (15 timed samples)
python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json

# all comparable rows from the main catalog, including non-governed frontier rows
python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.frontier.json

# mixed comparable/directional engineering space
python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.explore.json

# focused engineering slice from the explore preset
python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.explore.json --workload-filter render_draw_throughput_baseline,texture_sampling_raster_baseline

# canonical one-command variants:
python3 bench/runners/run_release_pipeline.py --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json --strict-amd-vulkan --with-claim-gate
# disable compare HTML generation when you only want JSON/workspace artifacts:
python3 bench/runners/run_release_pipeline.py --config bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json --no-compare-html-output
```

If Dawn cannot access an AMD Vulkan adapter on the host (for example, missing `/dev/dri` access),
run fails by design and is reported as non-comparable.

Quick host preflight (recommended before strict runs):

```bash
python3 bench/runners/preflight_bench_host.py --strict-amd-vulkan
```

Strict AMD preflight now includes a Dawn adapter probe (`dawn_perf_tests --gtest_list_tests`
with `--backend=vulkan --adapter-vendor-id=0x1002`) plus a Doe-side adapter probe resolved
through `vulkaninfo --summary`. Strict runs fail early unless Doe and Dawn agree on the same
AMD vendor/device identity. This catches cases where `/dev/dri/renderD128` appears readable
via OS-level checks but the two runtimes would land on different effective adapters.

## Apples-to-apples timing configuration

Workloads can now control per-run command stream expansion:

- `leftCommandRepeat` (default `1`)
- `rightCommandRepeat` (default `1`)
- `leftIgnoreFirstOps` / `rightIgnoreFirstOps` (default `0`)
- `leftUploadBufferUsage` / `rightUploadBufferUsage` (default `copy-dst-copy-src`, valid: `copy-dst-copy-src`, `copy-dst`)
- `leftUploadSubmitEvery` / `rightUploadSubmitEvery` (default `1`)

When repeat is greater than `1`, `compare_dawn_vs_doe.py` expands the workload command JSON array for that side before execution and runs the larger stream in a single sample. Use this with timing divisors to compare on the same unit:

- `leftTimingDivisor`
- `rightTimingDivisor`

Example strategy for upload workloads:

- set `leftCommandRepeat: 50`
- set explicit `leftUploadSubmitEvery` per workload size (for example, `50`, `2`, `1`, `4`)
- set `leftUploadBufferUsage: "copy-dst"`
- set `leftIgnoreFirstOps: 1`
- set `leftTimingDivisor: 50`
- keep Dawn benchmark metric as per-iteration (`dawn-perf-wall-time`)

This reduces one-command overhead distortion and reports per-upload timing units.

The AMD Vulkan preset (`bench/workloads/workloads.amd.vulkan.json`) applies this upload microbenchmark mode by default.

Strict comparability fail-fast rules for Dawn `BufferUploadPerf ... WriteBuffer` workloads:

- `leftUploadBufferUsage` must be `copy-dst`.
- `leftCommandRepeat` must be divisible by `leftUploadSubmitEvery`.
- (generic rule) `rightCommandRepeat` must be divisible by `rightUploadSubmitEvery`.

## Dawn-vs-Doe apples-to-apples contract

Claimable Dawn-vs-Doe performance results must satisfy this contract.

- run with `comparability.mode=strict` and `comparability.requireTimingClass=operation`
- for claimable speed statements, also run with `claimability.mode=local|release`
- keep matched workload semantics across both sides: backend/adapter constraints, operation shape, repeat accounting, and timing unit normalization
- use explicit workload config knobs for methodology; do not rely on implicit runtime behavior
- for upload workloads, explicitly set and report:
  `leftIgnoreFirstOps`/`rightIgnoreFirstOps`,
  `leftUploadBufferUsage`/`rightUploadBufferUsage`,
  `leftUploadSubmitEvery`/`rightUploadSubmitEvery`,
  `leftTimingDivisor`/`rightTimingDivisor`
- strict mode must fail fast on mismatched comparability settings or adapter/filter/test validity failures

Two benchmark intents are supported and must be reported separately:

- `apples-to-apples`: implementation-parity workloads (`workloadComparable=true`) with strict comparability.
- `doe-advantage`: Doe-optimized workloads (directional by workload contract) that still use the same strict timing basis (`operation`) for fairness.

Important:

- Dawn-vs-Doe strict runs do not allow mixed timing mechanisms for claim-grade evidence.
- For claim-grade apples-to-apples runs, keep strict operation timing. Use `process-wall` only for diagnostic overhead views.

Directional investigation runs are allowed, but they must be explicitly marked non-comparable (`workloadComparable=false` or `--include-noncomparable-workloads`) and must not be presented as apples-to-apples claims.

## Delta sign convention

Performance deltas are reported from the left-runtime perspective using ratio-style speedup:

- formula: `((rightMs / leftMs) - 1) * 100`
- positive percent: left runtime is faster
- negative percent: left runtime is slower
- zero: parity

For default Dawn-vs-Doe runs (`left=doe`, `right=dawn`), this means:

- positive percent: Doe is faster than Dawn
- negative percent: Doe is slower than Dawn

Interpretation examples:

- `+300%` => left is `4x` faster
- `+400%` => left is `5x` faster
- `-50%` => left is `2x` slower

`compare_dawn_vs_doe.py` and `compare_runtimes.py` emit `deltaPercentConvention` in reports and now write `schemaVersion: 5`.

`schemaVersion: 5` percentile summaries include fast-end, median, tail metrics, and the clearer `workloadUnitWall` timing name:

- workload stats include `p10Ms`, `p50Ms`, `p95Ms`, `p99Ms`
- workload deltas include `p10Percent`, `p50Percent`, `p95Percent`, `p99Percent`
- overall delta summary includes `p10Approx`, `p50Approx`, `p95Approx`, `p99Approx`
- workload timing interpretation includes selected-scope metadata and a workload-unit wall view (`timingInterpretation.selectedTiming`, `timingInterpretation.workloadUnitWall`)
- reports may also include `overallWorkloadUnitWall` for end-to-end process-wall aggregation across comparable workloads
- legacy aliases remain during migration: `timingInterpretation.headlineProcessWall` and `overallHeadlineProcessWall`
- HTML visualization emphasizes `p10/p50/p95/p99`
- claimability metadata fields are included:
  `claimabilityPolicy`, workload `claimability`, `claimabilitySummary`, `claimStatus`

Historical note:

- `schemaVersion: 3` used p5-oriented floor fields and is superseded.
- `schemaVersion: 2` uses the same sign convention but does not include the full percentile summary fields above.
- `schemaVersion: 1` used the inverse sign convention.

## Local Metal strict lanes

Additive local-metal presets:

- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.compare.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.release.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.frontier.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.explore.json`
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.smoke.json`

Host preflight:

```bash
python3 bench/runners/preflight_metal_host.py
```

Single-workload strict sweep (repeat one workload and emit median/tail deltas):

```bash
python3 bench/runners/run_single_workload_sweep.py \
  --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.compare.json \
  --workload upload_write_buffer_64kb \
  --repeats 5
```

Blocking gate sequence for strict Apple Metal comparable/release lanes:

```bash
python3 bench/runners/run_blocking_gates.py \
  --report bench/out/dawn-vs-doe.apple.metal.compare.json \
  --with-backend-selection-gate \
  --with-shader-artifact-gate \
  --with-metal-sync-conformance-gate \
  --with-metal-timing-policy-gate \
  --backend-runtime-policy config/backend-runtime-policy.json \
  --backend-timing-policy config/backend-timing-policy.json
```

For release claims, enforce backend telemetry in claim gate:

```bash
python3 bench/native-compare/compare_dawn_vs_doe.py \
  --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.release.json

python3 bench/gates/claim_gate.py \
  --report bench/out/dawn-vs-doe.apple.metal.release.json \
  --require-comparison-status comparable \
  --require-claim-status claimable \
  --require-claimability-mode release \
  --require-min-timed-samples 15 \
  --require-backend-telemetry \
  --expected-backend-id doe_metal
```

## Market-readiness evidence bundle

Use this when you need scoped external evidence, not just a raw compare report.

Canonical command:

```bash
python3 bench/runners/run_market_readiness_bundle.py \
  --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.release.json \
  --report bench/out/metal.npm.compare.json \
  --cts-config bench/fixtures/cts_subset.fawn-node.json
```

Outputs (prefix defaults to `<report>.market-readiness.*`):

- claim scope: `*.claim-scope.json`, `*.claim-scope.md`
- footprint: `*.footprint.json`, `*.footprint.md`
- CTS subset: `*.cts.json`, `*.cts.md`
- manifest: `*.manifest.json`

Optional model ceiling matrix artifact:

```bash
python3 bench/runners/run_market_readiness_bundle.py \
  --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.release.json \
  --report bench/out/metal.npm.compare.json \
  --cts-config bench/fixtures/cts_subset.fawn-node.json \
  --model-capacity-config bench/fixtures/model_capacity_matrix.template.json
```

Model matrix source contract (example template):
- `bench/fixtures/model_capacity_matrix.template.json`

Vendored CTS prerequisite:

```bash
cd bench/vendor/dawn/third_party/webgpu-cts
npm install
```

## Governed CSL smoke lane

Use this to exercise the non-hardware CSL prep path end to end:

```bash
python3 bench/runners/run_csl_governed_lane.py \
  --config bench/csl_governed_lane.gelu.smoke.json \
  --with-gate
```

What it does:
- builds `doe-csl-bundle-emitter` and `doe-csl-sim-runner`
- emits a real smoke `layout.csl` / `pe_program.csl` bundle from WGSL
- materializes a `csl_simulator_plan`
- probes the external Cerebras SDK driver contract
- writes a governed CSL lane report plus referenced artifacts

Without `cslc` and the Cerebras SDK installed, this lane should finish as
`blocked` / diagnostic with explicit blocker reasons rather than pretending to run.
