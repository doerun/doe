# Fawn Bench Module

Purpose:
- run correctness and performance measurements against specialization outputs
- enforce blocking/advisory gate modes from `fawn/config/gates.json`

This module is self-contained and does not depend on external runtime code.

## Performance Strategy (Read First)

Before running or interpreting Dawn-vs-Doe performance results, read:

- `fawn/performance-strategy.md`
- `bench/benchmark-writing-guide.md`

If you're adding or changing workloads/commands, treat the benchmark writing guide as the required authoring contract.

That document defines:

- claimability order and comparability invariants
- delta sign convention (`+` faster, `-` slower from Doe/left perspective)
- optimization priorities and anti-patterns

## Scripts

- `run_bench.py`
  - executes a configured workload command template, captures runtime timing samples, and emits measured metrics
  - computes timing statistics from wall time and trace-window timings when trace artifacts are present
  - emits reproducible run metadata with workload/artifact hashes and toolchain fields
  - compares against incumbent baseline ids from `fawn/config/benchmarks.json`
  - enforces host/backend compatibility before execution and fails fast on unsupported OS/backend mixes (for example: Vulkan on macOS, Metal on Linux/Windows, D3D12 on Linux/macOS).
- `check_correctness.py`
  - runs deterministic contract-level correctness checks
- `schema_gate.py`
  - validates schema-backed benchmark/config contracts as blocking release checks (`claim-cycle`, `webgpu-spec-coverage`, benchmark methodology thresholds, substantiation policy, comparability obligation contracts, and all quirk examples).
- `run_blocking_gates.py`
  - canonical entrypoint for blocking gate order: schema -> correctness -> trace -> optional drop-in -> optional claim gate.
  - release-claim readiness evidence requires claim gate enabled (`--with-claim-gate`), and can be enforced with `--require-claim-gate`.
  - can run comparability verification parity fixtures with `--with-comparability-parity-gate`.
- `comparability_obligation_parity_gate.py`
  - validates comparability obligation parity fixtures against Python evaluation and Lean obligation ID set alignment.
  - verifies fixture expectations (`expectedBlockingFailedObligations`, `expectedComparable`) from `bench/comparability_obligation_fixtures.json`.
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
  - only includes conformant compare reports (`schemaVersion=4`, canonical comparability-obligation IDs, and valid `workloadContract.path/sha256` hash match).
  - profile combos are sourced from per-sample `traceMeta.profile` fields; sides without profile metadata are tracked as report status only (not hardware-profile coverage).
  - also writes stable latest paths (`bench/out/test-inventory.latest.json`, `bench/out/test-dashboard.latest.html`) for a single canonical source of truth.
  - excludes `bench/out/scratch/**` from canonical inventory aggregation.
- `build_baseline_dataset.py`
  - builds a canonical baseline trend package from historical comparison artifacts.
  - only includes conformant compare reports (`schemaVersion=4`, canonical comparability-obligation IDs, and valid `workloadContract.path/sha256` hash match).
  - emits timestamped JSON trend dataset + markdown summary plus stable latest outputs.
  - groups history by matrix/runtime pair and tracks latest/best/worst p50 delta snapshots.
- `build_benchmark_cube.py`
  - normalizes backend compare reports plus package-surface compare reports into a single benchmark cube contract.
  - emits timestamped JSON row artifacts, JSON cube summary, and markdown matrix slices under `bench/out/cube/<timestamp>/`.
  - also writes stable latest outputs under `bench/out/cube/latest/`.
  - package-surface compare harnesses (`bench/node/compare.js`, `bench/bun/compare.js`) now force workload validation prepasses before timing comparable rows so claimable package-surface artifacts fail early on readback/correctness drift.
  - package surfaces can use explicit policy workload-id overrides (`config/benchmark-cube-policy.json`) so directional rows stay isolated from comparable workload-set cells.
  - backend rows preserve both canonical and legacy report history:
    - canonical rows come from fully conformant Dawn-vs-Doe reports.
    - legacy rows are kept when old reports still parse but no longer match the active workload-contract hash or obligation contract; these rows are marked `sourceConformance=legacy_nonconformant` and degrade to diagnostic in cube cells.
  - Node/Bun package rows stay explicit about maturity and missing-cell status instead of silently fabricating parity.
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
- `compare_dawn_vs_doe.py`
  - executes shared workload files against two explicit command templates (default Doe backend runtime on the left side + configurable Dawn/competitor runtime).
  - outputs per-run trace artifacts (`--trace-jsonl` and `--trace-meta` when templates provide these placeholders) plus workload-level and overall quantile summaries.
  - enforces host/backend compatibility before execution and fails fast on unsupported OS/backend mixes (for example: Vulkan on macOS, Metal on Linux/Windows, D3D12 on Linux/macOS).
  - current repo compare configs default to command-stream Dawn delegate lanes (`dawn_delegate`) for apples-to-apples strict workloads; `dawn_benchmark_adapter.py` remains available for gtest-filter diagnostics.
  - core logic is now split into dedicated helper modules under `bench/compare_dawn_vs_doe_modules/`:
    `timing_selection.py`, `comparability.py`, `claimability.py`, `reporting.py`.
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
- `run_cts_subset.py`
  - executes a configured WebGPU CTS query subset and emits per-query pass/fail + wall-time artifacts (JSON + markdown).
  - supports `--dry-run`, `--stop-on-fail`, and bounded query execution via `--max-queries`.
- `build_model_capacity_matrix.py`
  - builds a hardware×model capacity matrix artifact from measured Doppler/Doe runs, including status classes (`pass`, `fail`, `oom`, `unsupported`) and per-hardware max passable model size.
  - emits JSON + markdown summaries for explicit model-size ceiling disclosure.
- `run_market_readiness_bundle.py`
  - one-command orchestrator for release evidence packaging:
    release pipeline -> claim scope report -> runtime footprint -> CTS subset -> optional model-capacity matrix.
  - writes a manifest linking all generated artifacts and exits non-zero on any failed step.
- `check_full39_claim_readiness.py`
  - validates a full-matrix compare report against strict done criteria (exact comparable workload identity from contract, `comparisonStatus=comparable`, `claimStatus=claimable`, and zero left unsupported/error counters).
  - prints worst p95/p99 tail regressions plus non-claimable workload reasons to accelerate tail-fix loops.
- `run_full39_evidence_bundle.sh`
  - post-run orchestrator for claim-grade artifacts: readiness check -> blocking gates (trace/correctness/schema + drop-in + claim) -> repeated claim windows + substantiation -> inventory and baseline refresh.
- `generate_feature_benchmark_table.py`
  - builds a markdown table joining `config/webgpu-spec-coverage.json`, workload contracts, and Dawn filter mappings for Dawn-vs-Doe feature/benchmark coverage auditing.
  - emits both overall comparable-coverage and eligible-only comparable-coverage metrics; eligibility is config-driven via `benchmarkClass` (`comparable` vs `directional`) in `config/webgpu-spec-coverage.json`.
  - treats coverage `status=tracked` as spec-inventory-complete (audited/contracted) but not runtime-semantic implementation.
- `verify_smoke_gpu_usage.py`
  - validates AMD Vulkan smoke reports include explicit GPU probe evidence (`gpuMemoryProbeAvailable`, sample counts, and VRAM peak fields) on both sides.

Template placeholders:
`{commands}`, `{quirks}`, `{vendor}`, `{api}`, `{family}`, `{driver}`, `{workload}`, `{dawn_filter}`, `{trace_jsonl}`, `{trace_meta}`, `{extra_args}`.

Benchmark/report-producing scripts now timestamp outputs by default (`YYYYMMDDTHHMMSSZ`) and write artifacts under grouped per-run folders (`bench/out/<group>/<timestamp>/...`) to avoid clobbering, keep related runs together, and preserve chronological history inside each group. Use `--no-timestamp-output` when you intentionally need an exact fixed output path.

Each timestamped run folder now includes `run_manifest.json` with run metadata (`runType`, `config`, `fullRun`, `claimGateRan`, `dropinGateRan`, status fields).

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
python3 fawn/bench/organize_out_by_timestamp.py

# backfill historical run manifests where missing
python3 fawn/bench/backfill_run_manifests.py

# show what would be removed
python3 fawn/bench/cleanup_out.py --dry-run

# remove legacy untimestamped bench/out entries
python3 fawn/bench/cleanup_out.py

# scratch namespace holds manual/ad-hoc outputs
ls fawn/bench/out/scratch

# show a readable run index across grouped timestamp folders
python3 fawn/bench/list_out_runs.py --limit 25

# additionally prune timestamped artifacts older than 14 days
python3 fawn/bench/cleanup_out.py --retention-days 14
```

## Workload presets

- `fawn/bench/workloads.json` defines replay workloads, default profiles, and command seed artifacts.
- workload IDs must follow the immutable naming contract from `bench/benchmark-writing-guide.md`:
  `domain_subject_shape_variant` (status-free, no lifecycle/maturity prefixes).
- each workload includes `comparable` to declare whether mapping quality is apples-to-apples (`true`) or directional (`false`).
- workloads may set `allowLeftNoExecution: true` to allow strict comparability for deterministic feature-gated paths when left runtime reports unsupported/skipped execution evidence and zero execution errors.
- each workload can include `default: false`; these extended workloads are skipped unless `--include-extended-workloads` or explicit `--workload-filter` is provided.
- workloads are tagged with `domain` and `comparabilityNotes` for report transparency.
- directional workloads that are likely parity-promotion targets can declare `comparabilityCandidate` metadata.
- use `--workload-cohort comparability-candidates` to isolate that candidate set for directional parity work (requires `--include-noncomparable-workloads`).
- current comparable default matrix is upload scaling: `buffer_upload_{1kb,64kb,1mb,4mb,16mb}`.
- extended domains include render/draw, shader/pipeline, texture-raster, and compute suites.

## Dawn-vs-Doe example

Dawn does not publish a dedicated single-purpose `dawn-cli` binary. Use the benchmark
binary built from source (`dawn_perf_tests`) and a filter mapping by workload.

Build Dawn in this repo:

```bash
python3 fawn/bench/bootstrap_dawn.py \
  --source-dir fawn/bench/vendor/dawn \
  --build-dir fawn/bench/vendor/dawn/out/Release \
  --build-system gn \
  --branch main \
  --targets dawn_perf_tests \
  --parallel 8
```

```bash
python3 fawn/bench/compare_dawn_vs_doe.py \
  --left-command-template "env LD_LIBRARY_PATH=fawn/bench/vendor/dawn/out/Release:$LD_LIBRARY_PATH fawn/zig/zig-out/bin/doe-zig-runtime --commands {commands} --quirks {quirks} --vendor {vendor} --api {api} --family {family} --driver {driver} --backend native --execute --trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta} {extra_args}" \
  --right-command-template "python3 fawn/bench/dawn_benchmark_adapter.py --dawn-state fawn/bench/dawn_runtime_state.json --dawn-filter {dawn_filter} --dawn-filter-map fawn/bench/dawn_workload_map.json --workload {workload} --dawn-extra-args --backend=vulkan --dawn-extra-args --adapter-vendor-id=0x1002 --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}" \
  --comparability strict \
  --require-timing-class operation \
  --resource-probe rocm-smi \
  --resource-sample-ms 100 \
  --resource-sample-target-count 104 \
  --iterations 3 \
  --warmup 1 \
  --out fawn/bench/out/dawn-vs-doe.json
```

Run extended suites (non-default domains):

```bash
python3 fawn/bench/compare_dawn_vs_doe.py \
  --include-extended-workloads \
  --include-noncomparable-workloads \
  --comparability warn \
  --workload-filter compute_workgroup_atomic_1024,compute_workgroup_non_atomic_1024,compute_matvec_32768x2048_f32,compute_matvec_32768x2048_f32_swizzle1,compute_matvec_32768x2048_f32_workgroupshared_swizzle1,pipeline_compile_stress,render_draw_throughput_baseline,texture_sampling_raster_baseline \
  --right-command-template "python3 fawn/bench/dawn_benchmark_adapter.py --dawn-state fawn/bench/dawn_runtime_state.json --dawn-filter {dawn_filter} --dawn-filter-map fawn/bench/dawn_workload_map.json --workload {workload} --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}" \
  --out fawn/bench/out/dawn-vs-doe.extended.json
```

With Doe's default binary path:

```bash
python3 fawn/bench/compare_dawn_vs_doe.py \
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
- non-default workload entries are excluded unless `--include-extended-workloads` is set.
- strict mode now rejects contract-domain workloads as comparable unless explicitly promoted by contract policy.
  for guarded contract domains (`pipeline-async`, `p0-resource`, `p0-compute`, `p0-render`, `p1-capability`,
  `p1-resource-table`, `p1-capability-macro`, `p2-lifecycle`, `p2-lifecycle-macro`, `surface`), promotion
  requires `applesToApplesVetted=true` in workload config.
- strict upload comparability now preflights the executed `doe-zig-runtime` binary:
  it must expose `--upload-buffer-usage` and `--upload-submit-every`, reject invalid values for both flags, and not be older than key upload/runtime Zig sources (`zig/src/main.zig`, `zig/src/execution.zig`, `zig/src/wgpu_commands.zig`, `zig/src/webgpu_ffi.zig`).
  when a workload contract sets `--queue-wait-mode`, strict preflight also requires runtime support and validation for `--queue-wait-mode process-events|wait-any`.
- strict render comparability now selects encode-only operation timing on the Doe side for workload domains
  `render` and `render-bundle` (`timingSource=doe-execution-encode-ns`) to align with Dawn DrawCallPerf CPU-timing semantics.
  submit/wait totals remain in trace-meta for diagnostics but are not used as the primary per-op claim metric in those domains.
- claimability reliability mode is available:
  `--claimability local|release` enforces sample-floor and positive-tail checks for claimable speed reports.
  use `--claim-min-timed-samples N` to override mode defaults loaded from `config/benchmark-methodology-thresholds.json` (`claimabilityDefaults.localMinTimedSamples`, `claimabilityDefaults.releaseMinTimedSamples`).
  claimability failures return non-zero exit status (`3`) and report `claimStatus=diagnostic`.
  workloads whose selected timing scope is `narrow-hot-path` are non-claimable in all claim modes even when comparability is green; they are engineering diagnostics, not end-to-end speed claims.
- trace replay gate supports semantic parity lanes:
  `bench/trace_gate.py --semantic-parity-mode auto|required`.
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
python3 fawn/bench/compare_dawn_vs_doe.py \
  --config fawn/bench/compare_dawn_vs_doe.config.amd.vulkan.json \
  --workload-filter upload_write_buffer_64kb \
  --iterations 10 \
  --warmup 1 \
  --out fawn/bench/out/dawn-vs-doe.64kb.recheck.json
```

Timing classes:

- `operation`: `doe-execution-dispatch-window-ns`, `doe-execution-encode-ns`, `doe-execution-total-ns`, `doe-execution-row-total-ns`, `doe-trace-window`, `dawn-perf-wall-time`
- `process-wall`: `wall-time`

Process-wall comparability policy:

- when `--require-timing-class process-wall` is set, `compare_dawn_vs_doe.py` forces both sides to use outer command wall-time for measurement selection (no trace-meta substitution).
- if trace-meta also reports `timingSource=wall-time`, it is treated as auxiliary metadata and not as the primary timing value.
- process/resource sampling avoids fixed sleep quantization for open-ended runs by waiting on process completion with timeout polling.
- per-workload timing normalization divisors (`leftTimingDivisor`/`rightTimingDivisor`) are only applied in non-process-wall timing modes; process-wall runs use a normalization divisor of `1.0`.

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
  - `headlineProcessWall` reports the timed-command process-wall view for honest end-to-end ranking.
  - when `selectedTiming.scopeClass=narrow-hot-path`, `deltaPercent` is a phase-specific diagnostic and the workload is not claimable; use `headlineProcessWall.deltaPercent` for top-line comparisons instead.
- per-workload timing normalization is config-driven via `leftTimingDivisor` / `rightTimingDivisor`
  in `workloads.json` (matvec uses `leftTimingDivisor=100` and `rightTimingDivisor=1` because Dawn already reports per-dispatch via `iterationsPerStep=100`).
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
python3 fawn/bench/run_release_pipeline.py \
  --config fawn/bench/compare_dawn_vs_doe.config.amd.vulkan.release.json \
  --strict-amd-vulkan \
  --trace-semantic-parity-mode auto \
  --with-claim-gate
# emits claim rehearsal artifacts next to the report by default:
# <report>.claim-rehearsal.{claim-gate-result,tail-health,timing-invariant-audit,contract-hash-manifest,manifest}.json

# drop-in compatibility + benchmark suite against a built shared-library artifact:
python3 fawn/bench/dropin_gate.py \
  --artifact fawn/zig/zig-out/lib/libwebgpu_doe.so \
  --report fawn/bench/out/dropin_report.json

# optional standalone drop-in benchmark visualization (micro vs end-to-end sections):
python3 fawn/bench/visualize_dropin_benchmark.py \
  --report fawn/bench/out/dropin_benchmark_report.json \
  --out fawn/bench/out/dropin_benchmark_report.html

# run release pipeline and include drop-in gating:
python3 fawn/bench/run_release_pipeline.py \
  --config fawn/bench/compare_dawn_vs_doe.config.amd.vulkan.release.json \
  --strict-amd-vulkan \
  --trace-semantic-parity-mode auto \
  --with-dropin-gate \
  --dropin-artifact fawn/zig/zig-out/lib/libwebgpu_doe.so \
  --with-claim-gate

# optional repeated release windows for trend evidence:
python3 fawn/bench/run_release_claim_windows.py \
  --config fawn/bench/compare_dawn_vs_doe.config.amd.vulkan.release.json \
  --windows 5 \
  --strict-amd-vulkan \
  --trace-semantic-parity-mode auto \
  --with-dropin-gate \
  --dropin-artifact fawn/zig/zig-out/lib/libwebgpu_doe.so \
  --with-substantiation-gate \
  --substantiation-policy fawn/config/substantiation-policy.json
# disable per-window claim rehearsal artifacts only when intentionally running diagnostics:
#   --no-with-claim-rehearsal-artifacts

# optional standalone substantiation gate from existing window summaries/reports:
python3 fawn/bench/substantiation_gate.py \
  --policy fawn/config/substantiation-policy.json \
  --summary fawn/bench/out/release-claim-windows.json

# tested-profile inventory database + simple dashboard:
python3 fawn/bench/build_test_inventory_dashboard.py \
  --report-glob "fawn/bench/out/**/dawn-vs-doe*.json"

# baseline trend package (JSON + markdown):
python3 fawn/bench/build_baseline_dataset.py \
  --report-glob "fawn/bench/out/**/dawn-vs-doe*.json"

# optional visualization after the pipeline report exists:
python3 fawn/bench/visualize_dawn_vs_doe.py --report fawn/bench/out/dawn-vs-doe.amd.vulkan.release.json --out fawn/bench/out/dawn-vs-doe.amd.vulkan.release.html
# optional machine-readable distribution analysis:
python3 fawn/bench/visualize_dawn_vs_doe.py --report fawn/bench/out/dawn-vs-doe.amd.vulkan.release.json --analysis-out fawn/bench/out/dawn-vs-doe.amd.vulkan.release.distribution.json
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
python3 fawn/bench/bootstrap_dawn.py --build-system gn --gn-bin /path/to/gn --ninja-bin /path/to/ninja ...
```

Preferred bootstrap flow (run from this repo):

```bash
python3 fawn/bench/bootstrap_dawn.py --build-system gn --targets dawn_perf_tests
```

If bootstrap fails with:

```text
Could not find gn executable at: .../buildtools/.../gn/gn
```

run the same command again; this repo now auto-populates `buildtools` from Dawn’s `DEPS` and
attempts a CIPD install of GN.

If your environment cannot write `fawn/bench/vendor/dawn/buildtools`, use explicit standalone
binaries.

If this exact message persists:

```text
gn.py: Unable to find gn in your $PATH
gn.py: Could not find gn executable at: .../buildtools/.../gn/gn
```

this usually means the `depot_tools` wrapper cannot initialize itself. Use a dedicated standalone gn for this step:

```bash
brew install gn ninja
python3 fawn/bench/bootstrap_dawn.py \
  --build-system gn \
  --gn-bin $(which gn) \
  --ninja-bin $(which ninja) \
  --source-dir fawn/bench/vendor/dawn \
  --build-dir fawn/bench/vendor/dawn/out/Release \
  --targets dawn_perf_tests \
  --parallel 8
```

Then rerun with the normal command (explicit gn args are optional once cache is warm):

```bash
python3 fawn/bench/bootstrap_dawn.py --build-system gn --targets dawn_perf_tests
```

For an already checked-out Dawn tree, you can also run manifest-only after a successful first bootstrap:

```bash
python3 fawn/bench/bootstrap_dawn.py --manifest-only --build-system gn --targets dawn_perf_tests
```

You can disable bootstrap of Dawn buildtools if you prefer:

```bash
python3 fawn/bench/bootstrap_dawn.py --build-system gn --skip-gn-bootstrap ...
```

That produces `fawn/bench/vendor/dawn/out/Release/dawn_perf_tests` (or your configured build dir)
and writes `fawn/bench/dawn_runtime_state.json`.

Once built, discover test names and then wire one of them through `dawn_workload_map.json`:

```bash
fawn/bench/vendor/dawn/out/Release/dawn_perf_tests --gtest_list_tests
fawn/bench/vendor/dawn/out/Release/dawn_perf_tests --gtest_filter=DrawCallPerf.Run/Vulkan__e_skip_validation
```

`dawn_workload_map.json` in this directory holds workload-to-filter mappings.

## Dawn state artifact

`fawn/bench/dawn_runtime_state.json` is emitted by `bootstrap_dawn.py` and records the checkout path, branch, build type, generator, and resolved binary paths.

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
python3 fawn/bench/compare_dawn_vs_doe.py --config fawn/bench/compare_dawn_vs_doe.config.json
```

Config fields (CLI-compatible, config-first):

```json
{
  "workloads": "fawn/bench/workloads.json",
  "left": {
    "name": "doe",
    "commandTemplate": "env LD_LIBRARY_PATH=fawn/bench/vendor/dawn/out/Release:$LD_LIBRARY_PATH fawn/zig/zig-out/bin/doe-zig-runtime --commands {commands} --quirks {quirks} --vendor {vendor} --api {api} --family {family} --driver {driver} --backend native --execute --trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta} {extra_args}"
  },
  "right": {
    "name": "dawn",
    "commandTemplate": "python3 fawn/bench/dawn_benchmark_adapter.py --dawn-state fawn/bench/dawn_runtime_state.json --dawn-filter-map fawn/bench/dawn_workload_map.json --workload {workload} --dawn-extra-args=--backend=vulkan --dawn-extra-args=--adapter-vendor-id=0x1002 --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}"
  },
  "run": {
    "iterations": 3,
    "warmup": 1,
    "out": "fawn/bench/out/dawn-vs-doe.ryzen.json",
    "workspace": "fawn/bench/out/runtime-comparisons.ryzen",
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

A ready-to-run AMD Vulkan preset is now included:

- config: `bench/compare_dawn_vs_doe.config.amd.vulkan.json`
- workloads: `bench/workloads.amd.vulkan.json`
- Dawn filter map: `bench/dawn_workload_map.amd.autodiscover.json`
- AMD quirks list (empty/no-op baseline): `examples/quirks/amd_radv_noop_list.json`

Additional AMD Vulkan presets:

- release claim mode on the AMD native-supported strict comparable matrix (release sample floor): `bench/compare_dawn_vs_doe.config.amd.vulkan.release.json`
- local-claim preset for the same AMD native-supported strict comparable matrix: `bench/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json`
- directional diagnostics (remaining non-claim macro set): `bench/compare_dawn_vs_doe.config.amd.vulkan.directional.json`
- directional macro diagnostics (focused non-claim macro subset): `bench/compare_dawn_vs_doe.config.amd.vulkan.macro.directional.json`
- strict AMD smoke + GPU probe preset (16MB upload): `bench/compare_dawn_vs_doe.config.amd.vulkan.smoke.gpu.json`
- adapter-agnostic local comparable matrix (no fixed AMD vendor-id requirement): `bench/compare_dawn_vs_doe.config.local.vulkan.extended.comparable.json`
- local Vulkan directional diagnostics: `bench/compare_dawn_vs_doe.config.local.vulkan.directional.json`
- local Vulkan comparable matrix (legacy alias): `bench/compare_dawn_vs_doe.config.local.vulkan.comparable.json`
- local Vulkan release claim mode: `bench/compare_dawn_vs_doe.config.local.vulkan.release.json`

Preset behavior:

- Doe side is AMD-profiled in workload fields (`vendor=amd`, `api=vulkan`, `family=gfx11`, `driver=24.0.0`). The default Doe runtime currently expects `driver` to be a semver string.
- Dawn side is constrained to Vulkan + AMD vendor id (`--backend=vulkan`, `--adapter-vendor-id=0x1002`).
- Dawn filter selection is config-controlled and explicit via `@autodiscover` in the map.
- Autodiscovery is opt-in only (from map token `@autodiscover`); otherwise adapter fails fast.
- Comparability policy is strict operation-level timing (`mode=strict`, `requireTimingClass=operation`).
- strict mode will fail fast if the configured Doe runtime binary does not support upload knobs or appears stale relative to upload/runtime Zig sources.
- Upload workloads are configured for strict apples-to-apples matching against Dawn `BufferUploadPerf WriteBuffer`:
  `leftUploadBufferUsage=copy-dst`, `leftIgnoreFirstOps=1`, and explicit per-size
  `leftCommandRepeat`/`leftTimingDivisor`/`leftUploadSubmitEvery` values in
  `bench/workloads.amd.vulkan.extended.json`.

Run from `fawn/` directory:

```bash
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.json
```

Extended AMD Vulkan runs:

```bash
# comparable extended matrix local-claim preset (upload + compute + render + texture + render-bundle + async)
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json

# release claim gate matrix (extended comparable set, 15 timed samples)
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.release.json

# diagnostic slice (workload-filter driven; same strict comparable matrix contract)
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.directional.json

# diagnostic macro slice (high-volume render/texture + P0 PLS stress)
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.macro.directional.json

# directional comparability-candidate cohort (8 targeted Dawn parity candidates)
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.comparability-candidates.directional.json

# strict AMD smoke + GPU probe evidence check
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.smoke.gpu.json
python3 bench/verify_smoke_gpu_usage.py --report bench/out/dawn-vs-doe.amd.vulkan.smoke.gpu.16mb.json --require-comparable

# canonical one-command variants:
python3 bench/run_release_pipeline.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.release.json --strict-amd-vulkan --with-claim-gate
python3 bench/run_release_pipeline.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.smoke.gpu.json --strict-amd-vulkan --verify-smoke-report bench/out/dawn-vs-doe.amd.vulkan.smoke.gpu.16mb.json --verify-smoke-require-comparable
# disable compare HTML generation when you only want JSON/workspace artifacts:
python3 bench/run_release_pipeline.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.release.json --no-compare-html-output

# local adapter-agnostic comparable matrix (strict, no vendor-id pin)
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.local.vulkan.extended.comparable.json

# local Vulkan lanes
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.local.vulkan.directional.json
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.local.vulkan.comparable.json
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.local.vulkan.release.json
```

If Dawn cannot access an AMD Vulkan adapter on the host (for example, missing `/dev/dri` access),
run fails by design and is reported as non-comparable.

Quick host preflight (recommended before strict runs):

```bash
python3 bench/preflight_bench_host.py --strict-amd-vulkan
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

The AMD Vulkan preset (`bench/workloads.amd.vulkan.json`) applies this upload microbenchmark mode by default.

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

`compare_dawn_vs_doe.py` and `compare_runtimes.py` emit `deltaPercentConvention` in reports and now write `schemaVersion: 4`.

`schemaVersion: 4` percentile summaries include fast-end, median, and tail metrics:

- workload stats include `p10Ms`, `p50Ms`, `p95Ms`, `p99Ms`
- workload deltas include `p10Percent`, `p50Percent`, `p95Percent`, `p99Percent`
- overall delta summary includes `p10Approx`, `p50Approx`, `p95Approx`, `p99Approx`
- workload timing interpretation includes selected-scope metadata and a headline process-wall view (`timingInterpretation.selectedTiming`, `timingInterpretation.headlineProcessWall`)
- reports may also include `overallHeadlineProcessWall` for end-to-end process-wall aggregation across comparable workloads
- HTML visualization emphasizes `p10/p50/p95/p99`
- claimability metadata fields are included:
  `claimabilityPolicy`, workload `claimability`, `claimabilitySummary`, `claimStatus`

Historical note:

- `schemaVersion: 3` used p5-oriented floor fields and is superseded.
- `schemaVersion: 2` uses the same sign convention but does not include the full percentile summary fields above.
- `schemaVersion: 1` used the inverse sign convention.

## Local Metal strict lanes

Additive local-metal presets:

- `bench/compare_dawn_vs_doe.config.local.metal.extended.comparable.json`

Host preflight:

```bash
python3 bench/preflight_metal_host.py
```

Single-workload strict sweep (repeat one workload and emit median/tail deltas):

```bash
python3 bench/run_single_workload_sweep.py \
  --config bench/compare_dawn_vs_doe.config.local.metal.extended.comparable.json \
  --workload upload_write_buffer_64kb \
  --repeats 5
```

Blocking gate sequence for strict local-metal comparable/release lanes:

```bash
python3 bench/run_blocking_gates.py \
  --report bench/out/dawn-vs-doe.local.metal.extended.comparable.json \
  --with-backend-selection-gate \
  --with-shader-artifact-gate \
  --with-metal-sync-conformance-gate \
  --with-metal-timing-policy-gate \
  --backend-runtime-policy config/backend-runtime-policy.json \
  --backend-timing-policy config/backend-timing-policy.json
```

For release claims, enforce backend telemetry in claim gate:

```bash
python3 bench/compare_dawn_vs_doe.py \
  --config bench/compare_dawn_vs_doe.config.local.metal.extended.comparable.json \
  --claimability release \
  --out bench/out/dawn-vs-doe.local.metal.extended.release.json

python3 bench/claim_gate.py \
  --report bench/out/dawn-vs-doe.local.metal.extended.release.json \
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
python3 bench/run_market_readiness_bundle.py \
  --config bench/compare_dawn_vs_doe.config.local.metal.extended.comparable.json \
  --report bench/out/metal.npm.compare.json \
  --cts-config bench/cts_subset.webgpu-node.json
```

Outputs (prefix defaults to `<report>.market-readiness.*`):

- claim scope: `*.claim-scope.json`, `*.claim-scope.md`
- footprint: `*.footprint.json`, `*.footprint.md`
- CTS subset: `*.cts.json`, `*.cts.md`
- manifest: `*.manifest.json`

Optional model ceiling matrix artifact:

```bash
python3 bench/run_market_readiness_bundle.py \
  --config bench/compare_dawn_vs_doe.config.local.metal.extended.comparable.json \
  --report bench/out/metal.npm.compare.json \
  --cts-config bench/cts_subset.webgpu-node.json \
  --model-capacity-config bench/model_capacity_matrix.template.json
```

Model matrix source contract (example template):
- `bench/model_capacity_matrix.template.json`
