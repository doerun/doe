# Fawn Bench Module

Purpose:
- run correctness and performance measurements against specialization outputs
- enforce blocking/advisory gate modes from `fawn/config/gates.json`

This module is self-contained and does not depend on external runtime code.

## Performance Strategy (Read First)

Before running or interpreting Dawn-vs-Fawn performance results, read:

- `fawn/performance-strategy.md`

That document defines:

- claimability order and comparability invariants
- delta sign convention (`+` faster, `-` slower from Fawn/left perspective)
- optimization priorities and anti-patterns

## Scripts

- `run_bench.py`
  - executes a configured workload command template, captures runtime timing samples, and emits measured metrics
  - computes timing statistics from wall time and trace-window timings when trace artifacts are present
  - emits reproducible run metadata with workload/artifact hashes and toolchain fields
  - compares against incumbent baseline ids from `fawn/config/benchmarks.json`
- `check_correctness.py`
  - runs deterministic contract-level correctness checks
- `compare_runtimes.py`
  - runs two runtime commands repeatedly (left/right), captures wall-time quantiles, and writes a comparison artifact.
- `compare_dawn_vs_fawn.py`
  - executes shared workload files against two explicit command templates (default Fawn runtime + configurable Dawn/competitor runtime).
  - outputs per-run trace artifacts (`--trace-jsonl` and `--trace-meta` when templates provide these placeholders) plus workload-level and overall quantile summaries.
- `visualize_dawn_vs_fawn.py`
  - reads a `compare_dawn_vs_fawn.py` report and writes a self-contained HTML visualization plus optional analysis JSON.
  - includes ECDF overlays, workload×percentile delta heatmap, KS statistic/p-value, Wasserstein distance, probability of superiority `P(left<right)`, and bootstrap CIs for delta `p50`/`p95`/`p99`.
- `claim_gate.py`
  - validates a comparison report against required claim contract fields (`claimabilityPolicy.mode`, `comparisonStatus`, `claimStatus`, and per-workload claimability) for blocking release CI gates.

Template placeholders:
`{commands}`, `{quirks}`, `{vendor}`, `{api}`, `{family}`, `{driver}`, `{workload}`, `{dawn_filter}`, `{trace_jsonl}`, `{trace_meta}`, `{extra_args}`.

## Workload presets

- `fawn/bench/workloads.json` defines replay workloads, default profiles, and command seed artifacts.
- each workload includes `comparable` to declare whether mapping quality is apples-to-apples (`true`) or directional (`false`).
- each workload can include `default: false`; these extended workloads are skipped unless `--include-extended-workloads` or explicit `--workload-filter` is provided.
- workloads are tagged with `domain` and `comparabilityNotes` for report transparency.
- current comparable default matrix is upload scaling: `buffer_upload_{1kb,64kb,1mb,4mb,16mb}`.
- extended domains include render/draw, shader/pipeline, texture-raster, and compute suites.

## Dawn-vs-FAWN example

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
python3 fawn/bench/compare_dawn_vs_fawn.py \
  --left-command-template "env LD_LIBRARY_PATH=fawn/bench/vendor/dawn/out/Release:$LD_LIBRARY_PATH fawn/zig/zig-out/bin/fawn-zig-runtime --commands {commands} --quirks {quirks} --vendor {vendor} --api {api} --family {family} --driver {driver} --backend native --execute --trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta} {extra_args}" \
  --right-command-template "python3 fawn/bench/dawn_benchmark_adapter.py --dawn-state fawn/bench/dawn_runtime_state.json --dawn-filter {dawn_filter} --dawn-filter-map fawn/bench/dawn_workload_map.json --workload {workload} --dawn-extra-args --backend=vulkan --dawn-extra-args --adapter-vendor-id=0x1002 --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}" \
  --comparability strict \
  --require-timing-class operation \
  --resource-probe rocm-smi \
  --resource-sample-ms 100 \
  --resource-sample-target-count 104 \
  --iterations 3 \
  --warmup 1 \
  --out fawn/bench/out/dawn-vs-fawn.json
```

Run extended suites (non-default domains):

```bash
python3 fawn/bench/compare_dawn_vs_fawn.py \
  --include-extended-workloads \
  --include-noncomparable-workloads \
  --comparability warn \
  --workload-filter workgroup_atomic_1024,workgroup_non_atomic_1024,matrix_vector_multiply_32768x2048_f32,matrix_vector_multiply_32768x2048_f32_swizzle1,matrix_vector_multiply_32768x2048_f32_workgroupshared_swizzle1,shader_compile_pipeline_stress,render_draw_throughput_proxy,texture_sampling_raster_proxy \
  --right-command-template "python3 fawn/bench/dawn_benchmark_adapter.py --dawn-state fawn/bench/dawn_runtime_state.json --dawn-filter {dawn_filter} --dawn-filter-map fawn/bench/dawn_workload_map.json --workload {workload} --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}" \
  --out fawn/bench/out/dawn-vs-fawn.extended.json
```

With Fawn's default binary path:

```bash
python3 fawn/bench/compare_dawn_vs_fawn.py \
  --right-name "chromium-dawn" \
  --right-command-template "./path/to/dawn-wrapper.sh {commands} --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}"
```

## Comparability guardrails

`compare_dawn_vs_fawn.py` marks each workload as comparable/non-comparable and can fail hard:

- `--comparability strict` (default): exit non-zero when timing classes are mixed or mismatched.
- strict mode also exits non-zero when a selected workload contract is explicitly marked non-comparable (`comparable=false`).
- `--require-timing-class operation` (default): require operation-level timings on both sides.
- `--allow-left-no-execution`: opt out if left trace-meta has no `executionSuccessCount`/`executionRowCount`.
- strict mode rejects samples with runtime execution failures (`executionErrorCount > 0`) on either side.
- Dawn adapter now fails fast when a gtest filter matches zero tests (`Running 0 tests` / filter no-match warning) so startup-only runs cannot be reported as comparable timings.
- non-comparable workload mappings are excluded by default using `workloads.json` `comparable: false`.
- use `--include-noncomparable-workloads` only for directional investigation runs.
- non-default workload entries are excluded unless `--include-extended-workloads` is set.
- strict upload comparability now preflights the executed `fawn-zig-runtime` binary:
  it must expose `--upload-buffer-usage` and `--upload-submit-every`, reject invalid values for both flags, and not be older than key upload/runtime Zig sources (`zig/src/main.zig`, `zig/src/execution.zig`, `zig/src/wgpu_commands.zig`, `zig/src/webgpu_ffi.zig`).
  when a workload contract sets `--queue-wait-mode`, strict preflight also requires runtime support and validation for `--queue-wait-mode process-events|wait-any`.
- claimability reliability mode is available:
  `--claimability local|release` enforces sample-floor and positive-tail checks for claimable speed reports.
  use `--claim-min-timed-samples N` to override mode defaults (`local=7`, `release=15`).
  claimability failures return non-zero exit status (`3`) and report `claimStatus=diagnostic`.
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
- for upload claims, avoid mixed-scope derived timing sources; if timing selection and ignore-first adjustment measure different scopes, treat result as diagnostic.

Quick reliability recheck pattern:

```bash
python3 fawn/bench/compare_dawn_vs_fawn.py \
  --config fawn/bench/compare_dawn_vs_fawn.config.amd.vulkan.json \
  --workload-filter buffer_upload_64kb \
  --iterations 10 \
  --warmup 1 \
  --out fawn/bench/out/dawn-vs-fawn.64kb.recheck.json
```

Timing classes:

- `operation`: `fawn-execution-dispatch-window-ns`, `fawn-execution-total-ns`, `fawn-execution-row-total-ns`, `fawn-trace-window`, `dawn-perf-wall-time`
- `process-wall`: `wall-time`

Process-wall comparability policy:

- when `--require-timing-class process-wall` is set, `compare_dawn_vs_fawn.py` forces both sides to use outer command wall-time for measurement selection (no trace-meta substitution).
- if trace-meta also reports `timingSource=wall-time`, it is treated as auxiliary metadata and not as the primary timing value.
- process/resource sampling avoids fixed sleep quantization for open-ended runs by waiting on process completion with timeout polling.
- per-workload timing normalization divisors (`leftTimingDivisor`/`rightTimingDivisor`) are only applied in non-process-wall timing modes; process-wall runs use a normalization divisor of `1.0`.

Use `process-wall` only for startup/runtime-overhead studies, not per-op claims.

## Resource Bench (1:1)

`compare_dawn_vs_fawn.py` can capture resource metrics for both sides from the same external source:

- `processPeakRssKb`: per-run peak process RSS (`/usr/bin/time` max-RSS when available, with `/proc/<pid>/status` sampling fallback).
- `gpuVramUsed{Before,After,Peak}Bytes` and `gpuVramDeltaPeakFromBeforeBytes`:
  sampled from `rocm-smi --showmeminfo vram --json` when `--resource-probe rocm-smi` is enabled.

Use `--resource-sample-target-count N` to force fixed-count resource probing (`N vs N`) per run.
If a side runs longer than the probe budget, strict comparability fails with a truncation reason.

This is a 1:1 contract because the probe is outside both runtimes and identical for Dawn and Fawn.
Interpret VRAM deltas as device-level signals (global GPU usage), not isolated per-process accounting.

## What Is Being Tested

- default comparable Dawn-vs-Fawn runs currently test upload throughput scaling with
  `buffer_upload_{1kb,64kb,1mb,4mb,16mb}`.
- each workload is timed at operation-level when available:
  Dawn adapter uses benchmark `*RESULT ... wall_time` samples and takes median;
  Fawn timing source is selected by `compare_dawn_vs_fawn.py` policy from trace metadata
  (`executionGpuTimestampTotalNs` -> `executionEncodeTotalNs+executionSubmitWaitTotalNs` -> `executionTotalNs`)
  with fallback to trace-window/wall-time when required fields are unavailable.
  when ignore-first is enabled and applied, source is reported as `fawn-execution-row-total-ns+ignore-first-ops`.
- per-workload timing normalization is config-driven via `leftTimingDivisor` / `rightTimingDivisor`
  in `workloads.json` (matvec uses `leftTimingDivisor=100` and `rightTimingDivisor=100` to report per-dispatch units).
- non-comparable mappings are explicitly flagged in `workloads.json` and excluded by default.

Extended workload domains now include:

- render/draw throughput and state-set variants (`DrawCallPerf` mappings for base, dynamic bind-group, redundant pipeline/bind-group, draw-indexed proxy, and render-bundle dynamic variants).
- shader compile/pipeline stress (`ShaderRobustnessPerf` mapping, comparable, fixed single-test filter + per-step normalization).
- texture/raster and texture API contract workloads (`SubresourceTrackingPerf` mappings) including explicit sampler create/destroy, queue write texture, texture query assertions, and texture destroy lifecycle commands.
- async pipeline diagnostics contract workload (mapped to `ShaderRobustnessPerf` pipeline-compilation baseline) covering `CreateRenderPipelineAsync`, error scopes, and shader compilation-info API paths.
- surface lifecycle contract workload is tracked as directional (`surface_presentation_contract`) because Dawn perf suites do not expose a direct surface lifecycle benchmark contract across adapters.
- compute kernels matched to Dawn compute suites: `WorkgroupAtomicPerf` (atomic/non-atomic) and `MatrixVectorMultiplyPerf` (Rows=32768, Cols=2048, F32/F32 Naive).
  Matvec variants in config:
  `matrix_vector_multiply_32768x2048_f32` (Naive Swizzle=0),
  `matrix_vector_multiply_32768x2048_f32_swizzle1` (Naive Swizzle=1),
  `matrix_vector_multiply_32768x2048_f32_workgroupshared_swizzle1` (WorkgroupShared Swizzle=1).
  Fawn matvec command files set `kernel_dispatch.repeat=100` to match Dawn's `kNumDisptaches=100` step structure.

Use report `domain`, `workloadComparable`, and `comparabilityNotes` fields to separate
strict claims from directional investigation.

## Release hard gate (mandatory)

Release CI should treat replay validation as a blocking gate.
After each `compare_dawn_vs_fawn.py` run, fail CI if any successful sample lacks
or fails replay validation. For claimable release statements, also fail CI unless
the report is explicitly `claimability.mode=release`, `comparisonStatus=comparable`,
and `claimStatus=claimable`. Then generate an HTML visualization artifact:

```bash
python3 fawn/bench/compare_dawn_vs_fawn.py ... --out fawn/bench/out/dawn-vs-fawn.json
python3 fawn/bench/trace_gate.py --report fawn/bench/out/dawn-vs-fawn.json
python3 fawn/bench/claim_gate.py --report fawn/bench/out/dawn-vs-fawn.json --require-claimability-mode release --require-claim-status claimable --require-comparison-status comparable --require-min-timed-samples 15
python3 fawn/bench/visualize_dawn_vs_fawn.py --report fawn/bench/out/dawn-vs-fawn.json --out fawn/bench/out/dawn-vs-fawn.html
# optional machine-readable distribution analysis:
python3 fawn/bench/visualize_dawn_vs_fawn.py --report fawn/bench/out/dawn-vs-fawn.json --analysis-out fawn/bench/out/dawn-vs-fawn.distribution.json
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
- Otherwise the adapter reads `--dawn-filter-map` (`filters.<workload>` then `filters.default`).
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
    "buffer_upload_1kb": "@autodiscover",
    "default": "@autodiscover"
  }
}
```

### Explicit mapping (no autodiscovery)

```json
{
  "schemaVersion": 1,
  "filters": {
    "buffer_upload_1kb": "BufferUploadPerf.Run/Vulkan_AMD_Radeon_Graphics__RADV_GFX1151__WriteBuffer_BufferSize_1KB"
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

`compare_dawn_vs_fawn.py` supports a JSON config so you do not need to pass long placeholder-heavy templates inline.

Use:

```bash
python3 fawn/bench/compare_dawn_vs_fawn.py --config fawn/bench/compare_dawn_vs_fawn.config.json
```

Config fields (CLI-compatible, config-first):

```json
{
  "workloads": "fawn/bench/workloads.json",
  "left": {
    "name": "fawn",
    "commandTemplate": "env LD_LIBRARY_PATH=fawn/bench/vendor/dawn/out/Release:$LD_LIBRARY_PATH fawn/zig/zig-out/bin/fawn-zig-runtime --commands {commands} --quirks {quirks} --vendor {vendor} --api {api} --family {family} --driver {driver} --backend native --execute --trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta} {extra_args}"
  },
  "right": {
    "name": "dawn",
    "commandTemplate": "python3 fawn/bench/dawn_benchmark_adapter.py --dawn-state fawn/bench/dawn_runtime_state.json --dawn-filter-map fawn/bench/dawn_workload_map.json --workload {workload} --dawn-extra-args=--backend=vulkan --dawn-extra-args=--adapter-vendor-id=0x1002 --trace-jsonl {trace_jsonl} --trace-meta {trace_meta}"
  },
  "run": {
    "iterations": 3,
    "warmup": 1,
    "out": "fawn/bench/out/dawn-vs-fawn.ryzen.json",
    "workspace": "fawn/bench/out/runtime-comparisons.ryzen"
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

- config: `bench/compare_dawn_vs_fawn.config.amd.vulkan.json`
- workloads: `bench/workloads.amd.vulkan.json`
- Dawn filter map: `bench/dawn_workload_map.amd.autodiscover.json`
- AMD quirks list (empty/no-op baseline): `examples/quirks/amd_radv_noop_list.json`

Additional AMD Vulkan presets:

- release claim mode: `bench/compare_dawn_vs_fawn.config.amd.vulkan.release.json`
- extended comparable matrix (upload + compute + render + texture + render-bundle + async pipeline diagnostics): `bench/compare_dawn_vs_fawn.config.amd.vulkan.extended.comparable.json`
- directional diagnostics (surface lifecycle contract): `bench/compare_dawn_vs_fawn.config.amd.vulkan.directional.json`
- adapter-agnostic local comparable matrix (no fixed AMD vendor-id requirement): `bench/compare_dawn_vs_fawn.config.local.vulkan.extended.comparable.json`

Preset behavior:

- Fawn side is AMD-profiled in workload fields (`vendor=amd`, `api=vulkan`, `family=gfx11`, `driver=24.0.0`). The Fawn runtime currently expects `driver` to be a semver string.
- Dawn side is constrained to Vulkan + AMD vendor id (`--backend=vulkan`, `--adapter-vendor-id=0x1002`).
- Dawn filter selection is config-controlled and explicit via `@autodiscover` in the map.
- Autodiscovery is opt-in only (from map token `@autodiscover`); otherwise adapter fails fast.
- Comparability policy is strict operation-level timing (`mode=strict`, `requireTimingClass=operation`).
- strict mode will fail fast if the configured Fawn runtime binary does not support upload knobs or appears stale relative to upload/runtime Zig sources.
- Upload workloads are configured for strict apples-to-apples matching against Dawn `BufferUploadPerf WriteBuffer`:
  `leftUploadBufferUsage=copy-dst`, `leftIgnoreFirstOps=1`, and explicit per-size
  `leftCommandRepeat`/`leftTimingDivisor`/`leftUploadSubmitEvery` values in
  `bench/workloads.amd.vulkan.json`.

Run from `fawn/` directory:

```bash
python3 bench/compare_dawn_vs_fawn.py --config bench/compare_dawn_vs_fawn.config.amd.vulkan.json
```

Extended AMD Vulkan runs:

```bash
# comparable extended matrix (upload + compute + render + texture + render-bundle + async)
python3 bench/compare_dawn_vs_fawn.py --config bench/compare_dawn_vs_fawn.config.amd.vulkan.extended.comparable.json

# release-style claimability floor (15 timed samples)
python3 bench/compare_dawn_vs_fawn.py --config bench/compare_dawn_vs_fawn.config.amd.vulkan.release.json

# directional diagnostics only (surface lifecycle contract, non-claim)
python3 bench/compare_dawn_vs_fawn.py --config bench/compare_dawn_vs_fawn.config.amd.vulkan.directional.json

# local adapter-agnostic comparable matrix (strict, no vendor-id pin)
python3 bench/compare_dawn_vs_fawn.py --config bench/compare_dawn_vs_fawn.config.local.vulkan.extended.comparable.json
```

If Dawn cannot access an AMD Vulkan adapter on the host (for example, missing `/dev/dri` access),
run fails by design and is reported as non-comparable.

Quick host preflight (recommended before strict runs):

```bash
python3 bench/preflight_bench_host.py --strict-amd-vulkan
```

## Apples-to-apples timing configuration

Workloads can now control per-run command stream expansion:

- `leftCommandRepeat` (default `1`)
- `rightCommandRepeat` (default `1`)
- `leftIgnoreFirstOps` / `rightIgnoreFirstOps` (default `0`)
- `leftUploadBufferUsage` / `rightUploadBufferUsage` (default `copy-dst-copy-src`, valid: `copy-dst-copy-src`, `copy-dst`)
- `leftUploadSubmitEvery` / `rightUploadSubmitEvery` (default `1`)

When repeat is greater than `1`, `compare_dawn_vs_fawn.py` expands the workload command JSON array for that side before execution and runs the larger stream in a single sample. Use this with timing divisors to compare on the same unit:

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

## Dawn-vs-Fawn apples-to-apples contract

Claimable Dawn-vs-Fawn performance results must satisfy this contract.

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

Directional investigation runs are allowed, but they must be explicitly marked non-comparable (`workloadComparable=false` or `--include-noncomparable-workloads`) and must not be presented as apples-to-apples claims.

## Delta sign convention

Performance deltas are now reported from the left-runtime perspective with the right side as baseline:

- formula: `((rightMs - leftMs) / rightMs) * 100`
- positive percent: left runtime is faster
- negative percent: left runtime is slower
- zero: parity

For default Dawn-vs-Fawn runs (`left=fawn`, `right=dawn`), this means:

- positive percent: Fawn is faster than Dawn
- negative percent: Fawn is slower than Dawn

`compare_dawn_vs_fawn.py` and `compare_runtimes.py` emit `deltaPercentConvention` in reports and now write `schemaVersion: 3`.

`schemaVersion: 3` adds percentile summaries centered on p5/p50/p95/p99:

- workload stats now include `p5Ms`
- workload deltas now include `p5Percent`
- overall delta summary now includes `p5Approx`, `p50Approx`, `p95Approx`, `p99Approx`
- claimability metadata fields are included:
  `claimabilityPolicy`, workload `claimability`, `claimabilitySummary`, `claimStatus`

Historical note:

- `schemaVersion: 2` uses the same sign convention but does not include the full p5-based summary fields above.
- `schemaVersion: 1` used the inverse sign convention.
