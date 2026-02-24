# Chromium WebGPU Lane Plan

## Purpose

This plan defines a detailed, contract-first rollout for:

1. Track A:
   - Fawn as an optional Dawn replacement for Chromium `navigator.gpu`.
2. Track B:
   - Optional internal Chromium GPU modules executed through WebGPU via Fawn.

This is a planning artifact only. No production behavior is changed by this file.

## Guiding Constraints

1. Keep this lane isolated in `fawn/nursery/chromium_webgpu_lane/`.
2. Do not modify core runtime behavior implicitly.
3. Preserve Fawn stage discipline and gate precedence.
4. Require deterministic artifacts for all quality decisions.
5. Keep Dawn fallback available at every rollout stage.

## Program Phases

## M0: Planning and Contract Freeze

### Goal

Establish unambiguous integration contracts and acceptance criteria before implementation.

### Deliverables

1. Runtime seam contract:
   - interface assumptions,
   - symbol/export expectations,
   - fallback behavior.
2. Gate mapping:
   - blocking/advisory expectations aligned with `process.md`.
3. Risk register:
   - failure modes, mitigation, rollback.
4. Experiment inventory:
   - target adapters and workload classes.

### Exit Criteria

1. Contract docs are complete and reviewed.
2. Success/failure metrics are measurable and reproducible.
3. Promotion policy from nursery to core directories is agreed.

## M1: Track A Prototype (Flagged, Fallback First)

### Goal

Run Chromium with Fawn on the WebGPU runtime seam behind an explicit opt-in switch.

### Scope

1. No process model changes.
2. No behavior change when flag is disabled.
3. Dawn fallback remains default and immediate.

### Required Contracts

1. Feature flag contract:
   - explicit enable/disable controls.
2. Kill switch contract:
   - global disable without rebuild.
3. Adapter denylist contract:
   - deterministic auto-fallback behavior.

### Exit Criteria

1. Prototype launches and executes basic WebGPU workloads.
2. Fallback to Dawn succeeds for unsupported/denied configurations.
3. Runtime selection and failure reasons are observable in logs/artifacts.

## M2: Track A Compatibility Hardening

### Goal

Establish compatibility confidence with deterministic evidence.

### Required Evidence

1. Symbol completeness results.
2. Behavior suite results.
3. Browser-level WebGPU tests and CTS subset results.
4. Trace/replay integrity artifacts.

### Blocking Conditions

1. Any schema violation in generated artifacts.
2. Any deterministic correctness regression in required suites.
3. Any trace hash-chain or replay contract regression.
4. Any unresolved fallback path that results in hidden mode switches.

### Exit Criteria

1. ABI and behavior gates are green in defined target matrix.
2. Unsupported capabilities fail explicitly with actionable taxonomy.
3. Replay validation is stable for promoted workload set.

## M3: Track A Performance Qualification

### Goal

Demonstrate claimable or diagnostic-labeled performance behavior without methodology debt.

### Requirements

1. Strict comparability for claim lanes.
2. Operation-scope timing consistency.
3. Sample-floor requirements.
4. Tail positivity requirements per claim mode.

### Artifacts

1. Comparison report JSON.
2. Per-run trace/meta for both sides.
3. Workload contract snapshot and method knobs.
4. Gate outputs and claimability status.

### Exit Criteria

1. Performance reports correctly classify `claimable` vs `diagnostic`.
2. No unsupported/mixed timing claims are published.
3. Release claim gate passes for intended claim lanes.

## M4: Track B Module 1 (`fawn_2d_sdf_renderer`) Incubation

### Goal

Prototype the highest-ROI optional module while preserving CPU-owned semantics.

### Scope

1. GPU path for draw/raster of provided primitives.
2. CPU retains layout, bidi, shaping, accessibility semantics.
3. Explicit fallback for quality edge cases.

### Input Contract (Candidate)

1. `text_runs`:
   - shaped glyph IDs, positions, style refs.
2. `path_ops`:
   - fill/stroke commands with winding rules.
3. `paint_state`:
   - color, blend, clip, transform stack.
4. `target`:
   - render size, format, sample count.

### Output Contract (Candidate)

1. `render_pass_stats`:
   - draw count, atlas misses, fallback count.
2. `timing_spans`:
   - setup/encode/submit-wait totals.
3. `quality_flags`:
   - fallback reason codes when SDF path not selected.
4. `trace_link`:
   - module name and hash chain anchors.

### Exit Criteria

1. Deterministic output and replayability for fixed inputs.
2. Explicit fallback behavior for unsupported/low-quality cases.
3. No hidden semantic ownership creep into layout/accessibility logic.

## M5: Track B Additional Modules (One-by-One)

### Goal

Add optional modules incrementally with independent kill switches and gates.

### Modules

1. `fawn_path_engine`
2. `fawn_effects_pipeline`
3. `fawn_compute_services`
4. `fawn_resource_scheduler`

### Rules

1. No bundle promotion; each module ships independently.
2. Each module requires:
   - schema-backed I/O,
   - explicit unsupported taxonomy,
   - replay/gate coverage,
   - rollback plan.

### Exit Criteria (Per Module)

1. Correctness and trace gates pass.
2. Fallback behavior is deterministic and tested.
3. Performance classification is explicit (`claimable` or `diagnostic`).

## M6: Promotion and Maintenance

### Goal

Promote selected pieces from nursery to core directories with full governance.

### Promotion Requirements

1. Schema updates land with migration notes.
2. Process and status docs are updated in the same change.
3. Gate automation includes promoted behaviors.
4. Owners and maintenance responsibilities are explicit.

### Exit Criteria

1. Promoted module no longer depends on nursery-only assumptions.
2. CI has required blocking coverage for promoted scope.
3. Rollback path is validated and documented.

## Track A Detailed Workstreams

## A1. Integration Seam and Runtime Selection

Deliver:

1. Runtime selector contract.
2. Kill switch and denylist policy.
3. Fallback reason taxonomy.

KPIs:

1. Zero hidden mode switches.
2. Deterministic selection logs across repeated runs.

## A2. Compatibility and Correctness

Deliver:

1. Symbol and behavior suite automation for Chromium lane artifacts.
2. API parity checks for selected workload categories.

KPIs:

1. Pass rate against required compatibility matrix.
2. Zero unresolved blocking correctness regressions.

## A3. Trace and Replay Assurance

Deliver:

1. Required trace/meta emission paths.
2. Replay validation integration in gating chain.

KPIs:

1. Replay pass rate for target workload set.
2. Zero hash chain integrity failures.

## A4. Performance and Claimability

Deliver:

1. Claimability mode policy for Chromium lane workloads.
2. Comparability checks and timing-source guardrails.

KPIs:

1. Zero claim reports with methodology violations.
2. Clear classification for all performance reports.

## Track B Detailed Workstreams

## B1. `fawn_2d_sdf_renderer`

Open questions to resolve before implementation:

1. Atlas lifecycle policy and eviction determinism.
2. Quality thresholds for SDF/MSDF fallback.
3. Small-text hinting exceptions.
4. Clip/mask interaction contract.

Initial acceptance:

1. Deterministic atlas state for fixed input stream.
2. Quality/fallback counters in trace artifacts.

## B2. `fawn_path_engine`

Open questions:

1. Tessellation precision policy.
2. Path complexity thresholds.
3. Fill-rule parity expectations.

Initial acceptance:

1. Deterministic stroke/fill output on contract workload set.
2. Explicit fallback for unsupported geometry classes.

## B3. `fawn_effects_pipeline`

Open questions:

1. Effect graph contract and pass scheduling policy.
2. Intermediate texture lifetime and pooling rules.
3. Blend/color-space semantics for claim lanes.

Initial acceptance:

1. Deterministic effect ordering.
2. Replay parity for selected canonical effect chains.

## B4. `fawn_compute_services`

Open questions:

1. Which internal workloads are stable enough for contract hardening.
2. Synchronization boundaries with existing browser subsystems.
3. Resource isolation and error taxonomy requirements.

Initial acceptance:

1. Deterministic command contracts for selected kernels.
2. Explicit unsupported errors for unavailable features.

## B5. `fawn_resource_scheduler`

Open questions:

1. Pool sizing policy and deterministic eviction.
2. Submit cadence adaptation policy from config.
3. Cross-module contention and fairness rules.

Initial acceptance:

1. Config-driven behavior only.
2. No hidden heuristics in scheduling decisions.

## Module Contract Matrix (Initial Draft)

| Module | Inputs | Outputs | Blocking Gates | Advisory Gates | Rollback Trigger |
|---|---|---|---|---|---|
| Track A runtime seam | runtime selector + workload stream | trace/meta + behavior report | schema, correctness, trace, drop-in | performance | fallback instability |
| fawn_2d_sdf_renderer | text_runs, path_ops, paint_state | render stats + quality flags | schema, correctness, trace | performance | visual parity regressions |
| fawn_path_engine | path/stroke command stream | geometry/raster stats | schema, correctness, trace | performance | path correctness failures |
| fawn_effects_pipeline | effect graph + resources | pass stats + output hashes | schema, correctness, trace | performance | effect mismatch or instability |
| fawn_compute_services | kernel request contracts | execution stats + failure taxonomy | schema, correctness, trace | performance | unsupported/failure rate growth |
| fawn_resource_scheduler | resource usage + cadence policy | pool/submit metrics | schema, correctness, trace | performance | nondeterministic scheduling |

## Gate Mapping

Use existing Fawn gate order and tools where applicable:

1. Schema gate:
   - required for all promoted contract surfaces.
2. Correctness gate:
   - required for deterministic behavior checks.
3. Trace gate:
   - required for replay/hash-chain integrity.
4. Drop-in gate:
   - required for drop-in artifact lanes.
5. Claim gate:
   - required when release-level claimability is asserted.

Verification and performance remain advisory by default in v0 except where per-quirk policy makes proof blocking.

## KPI Framework

## Stability KPIs

1. Crash/hang parity vs fallback lane.
2. Replay pass rate stability over rolling windows.
3. Unsupported/fallback rate by adapter profile.

## Correctness KPIs

1. Required suite pass rates.
2. Deterministic output parity on fixed seeds.
3. Trace hash-chain integrity rate.

## Performance KPIs

1. Claimable workload count.
2. Non-comparable workload count.
3. Tail metrics (`p95`, `p99`) trend stability.

## Operational KPIs

1. Time-to-detect methodology drift.
2. Time-to-fallback on runtime health regressions.
3. Share of runs with complete artifact bundles.

## Rollback Policy

Rollback triggers:

1. Blocking gate regressions.
2. Crash/hang regression above agreed threshold.
3. Unbounded unsupported/fallback spike.
4. Artifact integrity failures in release lanes.

Rollback actions:

1. Disable experimental runtime via global switch.
2. Enforce denylist route to fallback.
3. Re-run blocking gates on fallback lane.
4. Publish incident artifact bundle and mitigation notes.

## Dependencies and Assumptions

1. Chromium-side build/runtime selection seam is available for runtime switching.
2. Drop-in ABI lane remains maintained against upstream drift.
3. Target adapter inventory is known and reproducible.
4. CI can run required gate suites with stable artifact capture.

If any assumption fails, keep feature in nursery and do not promote.

## Open Decisions

1. Exact Chromium flag names and user-facing policy.
2. Minimum target adapter matrix for promotion from M2 to M3.
3. SDF quality acceptance thresholds for module promotion.
4. Required CTS/browser suite subsets for each milestone.
5. Long-term ownership split across runtime, quality, and module teams.

## Immediate Next Actions

1. Finalize runtime seam and fallback contract document.
2. Define first adapter/workload matrix for M1 and M2.
3. Draft candidate input/output schemas for `fawn_2d_sdf_renderer`.
4. Draft kill-switch and denylist policy with explicit reasons.
5. Define initial KPI baselines and reporting templates.
6. Start local Chromium bring-up using `chromium-bringup.md` with lane-local, gitignored build directories.

## Promotion Checklist

Before moving any item out of nursery:

1. Contract schema and migration implications are documented.
2. Gate wiring is defined and testable.
3. Rollback path is validated.
4. Ownership and oncall expectations are assigned.
5. Status tracking updates are prepared.

If any checklist item is unmet, the item remains in nursery.
