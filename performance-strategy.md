# Fawn Performance Strategy

## Purpose

This document defines how to pursue and communicate Dawn-vs-Doe performance work without creating comparability debt.

Use this for:

- benchmark methodology changes
- upload/copy/dispatch performance optimization
- performance claims against Dawn

## Core Rule

Do not optimize or claim from intuition.  
Optimize only from comparable measurements with explicit workload contracts.

## Claimability Order (Always)

1. Check `comparisonStatus`, `nonComparableCount`, and failure reasons.
2. Verify timing class is `operation` on both sides for per-op claims.
3. Verify workload normalization fields:
- repeat
- timing divisor
- ignore-first count
- upload buffer usage
- submit cadence
4. Inspect per-run traces for first-op spikes/outliers.
5. Interpret deltas only after all invariants hold.

If any invariant fails, label the run diagnostic, not claimable.

When reporting outcomes, include tails and floor, not only median:

- `p10` (fast-end floor view; less noisy than `p5` at low sample counts)
- `p50` (median)
- `p95` and `p99` (tail stability)

Recommended distribution-comparison stack for claim support:

1. ECDF overlays
2. bootstrap CI for delta `p50`/`p95`/`p99`
3. superiority probability `P(left<right)`
4. KS statistic + p-value
5. Wasserstein distance
6. workload×percentile delta heatmap

## Reliable Faster Contract

Use two labels only:

- `claimable`: can be used for "Doe is faster" statements.
- `diagnostic`: useful for engineering direction, not for claims.

`claimable` faster requires all of the following:

1. comparability passes (`comparisonStatus=comparable`, zero non-comparable workloads).
2. sample floor: at least 7 timed samples per side (`iterations - warmup >= 7`) for local claims; target 15+ for release/CI claims.
3. percentile sign consistency for speed claims:
- local: `delta p50 > 0` and `delta p95 > 0`
- release/CI: `delta p50 > 0`, `delta p95 > 0`, `delta p99 > 0`
4. timing-scope consistency:
- do not treat mixed-source derived timings as claimable (example: `doe-execution-dispatch-window-ns+ignore-first-ops` where base and adjustment measure different scopes)
- for upload claims, use a single operation-scope timing method consistently and document it in workload/report artifacts
5. operation-vs-wall sanity:
- selected operation timing must not cover an implausibly tiny share of process wall on one side while the peer side shows materially higher operation-to-wall coverage
- treat large left/right operation-to-wall coverage asymmetry as diagnostic until the timing scope is audited
6. no execution errors and no filter/adapter validity failures.

If any condition fails, classify the run as `diagnostic`.

Harness support:

- `compare_dawn_vs_doe.py --claimability local|release` enforces this contract and emits `claimStatus`.

## Delta Sign Convention

Performance delta percent is reported from left-runtime perspective with right baseline:

- formula: `((rightMs - leftMs) / rightMs) * 100`
- positive: left runtime faster
- negative: left runtime slower
- zero: parity

For default Dawn-vs-Doe runs (`left=doe`, `right=dawn`):

- positive: Doe faster than Dawn
- negative: Doe slower than Dawn

## Near-Term Optimization Priorities

1. Align upload timing-source semantics so claim runs are methodologically stable.
2. Eliminate `upload_write_buffer_64kb` bimodality (submit-wait spikes + setup variance).
3. Isolate remaining steady-state hotspots (next focus after 64KB reliability: `upload_write_buffer_1mb`).
4. Remove steady-state allocator churn from upload paths.
5. Keep upload path allocation-light and reuse resources/encoders aggressively.
6. Tune submit cadence by size/profile with explicit config fields.
7. Optimize tails (`p95`/`p99`) in addition to `p50`.

## Investigation Loop (No Shortcut)

1. Reproduce with strict comparability and workload filter.
2. Increase samples (`iterations`) and keep warmup explicit.
3. Split measured cost into setup/encode/submit-wait/dispatch where available.
4. Classify each delta component:
- artifact (cold start / methodology mismatch)
- signal (steady-state per-op overhead)
5. Apply one change at a time and rerun strict comparison.
6. Record methodology and remaining caveats in docs/status.

## 64KB Upload Finding (2026-02-21)

Investigation outcome for AMD Vulkan `upload_write_buffer_64kb`:

1. `leftCommandRepeat=50`, `leftUploadSubmitEvery=50`, `leftIgnoreFirstOps=1` showed strong bimodality and negative tails in repeated runs.
2. Switching `leftIgnoreFirstOps` changed deltas dramatically, confirming high measurement-policy sensitivity.
3. Increasing `leftCommandRepeat` to 500 with explicit per-op normalization produced strong positive diagnostics, indicating heavy batching/setup sensitivity.
4. Local follow-up on operation-scope upload submit-wait metric showed `leftUploadSubmitEvery=100` outperformed `50` for the 64KB contract (`repeat=500`) in `bench/out/upload_64kb_submit_wait_100_vs_50.local.json` (`executionSubmitWaitTotalNs`, `n=30` per side): `p50 +19.52%`, `p95 +14.21%`; AMD Vulkan claim-mode recheck is still required on adapter-backed host.

Interpretation:

- the 64KB issue is primarily a reliability/methodology + submit behavior problem, not a simple one-dimensional throughput limit.
- claim-mode now enforces timing-scope consistency; legacy runs before this enforcement should be treated as diagnostic.
- queue wait implementation strategy can affect host behavior; keep wait-path changes explicit and benchmark-backed before promoting them into claim workloads.

## Architecture Guidance: Zig vs C++

Language alone does not guarantee wins. C++/Dawn can close gaps with enough focused engineering.

Fawn's durable advantage should come from:

- explicit hot-path control in Zig
- config-driven methodology with fail-fast comparability
- deterministic trace/replay for rapid root-cause loops
- proof-driven branch elimination (Lean) after Zig behavior is measured

Target advantage is not "Zig magic"; it is lower hot-path complexity plus faster safe iteration.

## Anti-Patterns (Do Not Do)

- accepting startup-only timings as comparable performance
- allowing implicit filter autodiscovery fallback in strict claim runs
- mixing timing classes (`process-wall` vs `operation`) for per-op claims
- hiding methodology knobs in code instead of workload/config
- reporting deltas when execution/adapter/filter validity failed

## Required Artifacts for Performance Claims

For each claimable result, keep:

- comparison report JSON
- per-run trace meta/jsonl artifacts
- workload config showing normalization/methodology knobs
- comparability status and failure-free summary
- date and command/config used
