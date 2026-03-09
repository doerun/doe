# Chromium browser integration layer (nursery)

## Purpose

`fawn/nursery/fawn-browser` is the repo-local browser integration layer for
Chromium work. It contains the docs, contracts, helper scripts, and diagnostic
harnesses that drive a Chromium checkout/build lane.

It is not the Chromium checkout/build workspace itself. In this repo, that
workspace is `fawn/nursery/chromium_webgpu_lane/` when kept in-tree, or the
path selected by `FAWN_CHROMIUM_LANE_DIR` for external-volume setups.

This integration layer is used for:

1. A Dawn replacement path for `navigator.gpu` in Chromium.
2. An optional execution substrate for selected Chromium-internal GPU modules.

This layer is intentionally process-heavy and contract-first. It exists to
prevent architectural drift and comparability debt before implementation.

## Scope

In scope:

1. Integration architecture, contracts, and rollout policy.
2. Test/gate/benchmark plans for Chromium-facing work.
3. Optional internal module designs (`2D SDF`, `path`, `effects`, `compute services`, `resource scheduler`).

Out of scope:

1. Direct edits to core runtime execution in `fawn/zig/src`.
2. Redefining Fawn stage order or existing gate precedence.
3. Claims of browser-wide replacement semantics.

## Isolation contract

This directory is isolated from core runtime development by policy:

1. No production runtime behavior is enabled from files under `nursery/`.
2. No hidden feature toggles are introduced in core runtime through this layer.
3. Any future implementation promoted from this layer must:
   - move to core module directories (`zig/`, `bench/`, `config/`, etc.),
   - land with schema and migration updates,
   - pass blocking gates defined in `fawn/process.md`.
4. Nothing in this layer bypasses stage discipline:
   - Mine -> Normalize -> Verify -> Bind -> Gate -> Benchmark -> Release.

Milestone status source of truth:

1. `bench/workflows/browser-milestones.json`
2. checked by `scripts/check-browser-milestones.py`
3. plan/notes describe intent and evidence, but milestone state changes should be recorded in the manifest

## Context summary

Fawn already has an ABI-focused drop-in lane and compatibility gates that make Chromium experimentation realistic:

1. Drop-in artifact:
   - `zig/zig-out/lib/libwebgpu_doe.{so,dylib}`
2. Symbol contract and gate support:
   - `config/dropin_abi.symbols.txt`
   - `bench/dropin_symbol_gate.py`
   - `bench/dropin_behavior_suite.py`
   - `bench/dropin_benchmark_suite.py`
   - `bench/dropin_gate.py`
3. Existing trace/replay and claimability policy:
   - `trace/replay.py`, `bench/trace_gate.py`, `bench/claim_gate.py`

This layer extends those capabilities to Chromium integration planning without
coupling directly to core runtime code yet.

Terminology used in this directory:

1. "browser integration layer"
   - `nursery/fawn-browser/`
2. "Chromium checkout/build lane"
   - `nursery/chromium_webgpu_lane/` or an externally mounted lane selected by
     `FAWN_CHROMIUM_LANE_DIR`

## Program shape

Use a two-track model to control risk:

1. Track A (browser):
   - Dawn replacement path for `navigator.gpu` via Fawn.
2. Track B (modules):
   - Optional Chromium-internal modules using WebGPU through Fawn.

Track B (modules) is additive and cannot block Track A (browser) readiness.

## Track A (browser): Dawn replacement lane

### Objective

Swap the runtime implementation seam while keeping browser behavior and process topology stable.

### Design constraints

1. Keep Chromium process model unchanged:
   - renderer behavior unchanged,
   - GPU process boundaries unchanged,
   - sandbox model unchanged.
2. Keep Dawn available as first-class fallback at every stage.
3. Use explicit runtime selection flagging and kill switches.
4. Preserve deterministic artifacts for all quality decisions.

### Integration principle

Only replace the WebGPU runtime seam. Do not fuse this work with unrelated compositor/layout/media refactors.

### Promotion gates

Before moving beyond experiment flags:

1. ABI/symbol completeness gate passes.
2. API behavior parity gate passes.
3. Replay and deterministic trace parity checks pass.
4. Crash/hang rate parity with fallback lane is established.
5. Performance claimability gates pass for any "faster" statement.

## Track B (modules): optional Chromium-internal modules

Track B (modules) are explicitly optional and must preserve CPU ownership for engine semantics.

### Candidate modules

1. `fawn_2d_sdf_renderer`
   - GPU paint/raster path for vector/text primitives via SDF/MSDF.
   - Inputs: shaped runs, path commands, paint state.
   - Outputs: render targets or composited textures.
2. `fawn_path_engine`
   - Hybrid tessellation + SDF path for fills/strokes/clip masks.
   - Includes explicit fallback for pathological geometry.
3. `fawn_effects_pipeline`
   - Compute/render effects (blur, color transforms, mask composition, filter chains).
4. `fawn_compute_services`
   - Shared compute kernels for selected internal tasks.
5. `fawn_resource_scheduler`
   - Shared resource pooling and submission cadence controls.

### Non-goals for Track B (modules)

1. Replacing Blink layout/style/DOM semantics.
2. Replacing V8 execution.
3. Replacing OS compositor/scanout responsibilities.
4. Replacing hardware codec control paths.

## What WebGPU/Fawn can and cannot replace

Can replace or absorb:

1. Many explicit GPU draw/compute operations.
2. Significant portions of raster/effects work where command contracts are stable.
3. Internal GPU utility workloads with deterministic contracts.

Cannot replace by itself:

1. HTML/CSS layout semantics and accessibility logic.
2. Browser orchestration and process/security policy.
3. OS-level presentation and protected path ownership.
4. Hardware decoder control APIs.

## Contract-first policy for this layer

Every proposed feature in this layer must define:

1. Input contract:
   - schema-backed request shape.
2. Output contract:
   - result artifacts and traceability fields.
3. Failure contract:
   - explicit unsupported/error taxonomy.
4. Methodology contract:
   - timing source, normalization divisors, comparability mode.
5. Fallback contract:
   - deterministic fallback path and trigger reasons.

No implicit behavior switching is allowed.

## Config and schema expectations

Future implementation promoted from this layer must use config-as-code:

1. Config files in `fawn/config/*.json`.
2. Schema files in `fawn/config/*schema*.json`.
3. Migration notes in `fawn/config/migration-notes.md` for runtime-visible changes.
4. Status tracking updates in `fawn/status.md` for temporary placeholders or staged methods.

## Gate policy alignment

This layer inherits Fawn v0 gate priorities:

1. Blocking:
   - schema,
   - correctness,
   - trace.
2. Advisory (v0 global policy):
   - verification,
   - performance.
3. Additional blocking when applicable:
   - drop-in compatibility for artifact lanes,
   - release claimability when promotion requires claim statements.

## Reliability and claimability expectations

No performance claim can be promoted without:

1. strict comparability compliance,
2. operation-scope timing consistency,
3. minimum timed sample floors,
4. positive percentile tails (`p50`, `p95`; `p99` for release claims),
5. zero execution errors in selected claim workloads.

Directional runs must be labeled non-claimable.

## Observability contract

All promoted experiments must emit:

1. run metadata (`run-metadata.schema.json`),
2. row-level trace (`trace.schema.json`),
3. run-level trace summary (`trace-meta.schema.json`),
4. reproducible artifact hashes for replay and audit.

Traceability fields must include module identity and hash chain continuity.

## Risk controls

Primary risks:

1. Hidden fallback behavior under incompatible adapters.
2. Timing-scope mismatches generating false win claims.
3. ABI drift from Chromium/Dawn evolution.
4. Excessive platform divergence from driver-specific quirks.

Mitigations:

1. explicit unsupported taxonomy and fail-fast checks,
2. strict comparability mode by default for claim lanes,
3. symbol and behavior drop-in gates in CI,
4. upstream quirk mining and deterministic normalization.

## Directory structure

Current browser integration layer structure:

1. `README.md`
   - scope, policy, and contracts overview.
2. `plan.md`
   - milestone plan, exit criteria, dependencies.
3. `chromium-bringup.md`
   - practical local bring-up path and early integration sequence.
4. `contracts/`
   - runtime selector contract and optional module contract drafts.
   - see `contracts/README.md` for index.
5. `notes/`
  - findings, experiment logs, touchpoint mapping, and promotion decisions.
6. `scripts/`
   - lane-local helpers (`scripts/bootstrap-host-tools.sh`, `scripts/env.sh`,
     `scripts/preflight.sh`, `scripts/bringup-linux.sh`,
     `scripts/run-smoke.sh`, `scripts/run-bench.sh`,
     `scripts/check-browser-milestones.py`).
7. `assets/`
   - brand assets, logo source, and compiled macOS/Linux logo artifacts.

## Logo asset layout

- Source SVG: `assets/logo/source/fawn-icon-main.svg`
- Compiled macOS icon: `assets/logo/compiled/macos/fawn-icon-main.icns`
- Compiled Linux PNGs: `assets/logo/compiled/linux/fawn-icon-main-16.png`,
  `fawn-icon-main-32.png`, `fawn-icon-main-64.png`,
  `fawn-icon-main-128.png`, `fawn-icon-main-256.png`,
  `fawn-icon-main-512.png`.
- Rebuild from source with:

```bash
cd /Users/xyz/deco/fawn/nursery/fawn-browser
./scripts/build-fawn-logo-assets.sh
```

Any script/code added here must be non-production and must not alter core runtime behavior by default.

## Decision rules for promotion out of nursery

A design exits nursery only when all are true:

1. Problem statement and success metric are explicit.
2. Contract schema and migration impact are specified.
3. Gate implications are mapped (blocking/advisory).
4. Rollback and fallback behavior are explicit.
5. Ownership and maintenance burden are assigned.

If one is missing, keep the item in nursery.

## Ownership model

Recommended ownership split:

1. Runtime seam and ABI parity:
   - runtime integration owner(s).
2. Trace/replay and correctness gate policy:
   - quality owner(s).
3. Performance/claimability policy:
   - benchmark methodology owner(s).
4. Optional module incubation:
   - module-specific owners.

Cross-owner signoff is required before any promotion from nursery to core paths.

## How to use this folder

1. Read this file and `plan.md` before proposing Chromium integration changes.
2. Add or update module proposals as contract documents first.
3. Tie every proposal to gates and measurable exit criteria.
4. Promote to core directories only after passing promotion rules.

## Current status

This lane contains planning/contracts docs, lane-local bring-up scripts, and a lane-local Chromium workspace (`src/`) with in-flight Track A (browser) seam integration edits.

No core `fawn/zig` production runtime behavior is introduced by this directory by default.
