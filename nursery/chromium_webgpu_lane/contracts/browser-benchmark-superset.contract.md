# Browser Benchmark Superset Contract (Draft)

Status: `draft`

## Objective

Define a low-maintenance browser benchmark superset that:

1. depends on core engine workload contracts in `fawn/bench/workloads.amd.vulkan.extended.json`,
2. projects browser-relevant workloads automatically into browser API tests,
3. adds browser workflow scenarios on top,
4. keeps core/runtime and nursery logic de-duplicated.

## Layer Model

1. `L0 engine`
   - canonical Dawn-vs-Fawn runtime benchmark layer (`full39` strict comparable).
2. `L1 browser-api`
   - browser-executed WebGPU API scenarios projected from `L0` workload contracts.
3. `L2 browser-workflow`
   - browser component and lifecycle workflows that involve WebGPU but include browser overhead.

## Source-of-Truth Rule

1. `bench/workloads.amd.vulkan.extended.json` remains the only source for engine workload identity and ownership.
2. nursery projection manifests are generated from this source and must not hand-copy workload lists.
3. if a workload is added/removed in `L0`, the projection generator and gate must reflect this automatically.

## Projection Classes

Each `L0` workload maps to one of:

1. `high`
   - near-direct browser API projection expected.
2. `medium`
   - browser projection possible with declared semantic/timing drift.
3. `non_projectable`
   - runtime-internal semantics; keep in `L0` only.

## Required Projection Fields

Each projected workload row must include:

1. `sourceWorkloadId`
2. `domain`
3. `projectionClass`
4. `layerTarget` (`l1_browser_api` or `l0_only`)
5. `scenarioTemplate`
6. `comparabilityExpectation` (`strict`, `component`, `none`)
7. `requiredStatus` (`ok`, `not_applicable`)
8. `claimScope` (`l1_strict_candidate`, `l1_component_only`, `l0_only_no_claim`)
9. `claimLanguage`
10. `projectionNote`

Projection manifests must also carry:

1. `sourceWorkloadsSha256`
2. `rulesSha256`
3. `projectionContractHash`

These hashes are blocking for contract synchronization.

## Browser Workflow Contract

`L2` workflow entries must define:

1. `id`
2. `scenarioTemplate`
3. `description`
4. `metrics`
5. `comparabilityExpectation`
6. `required` (bool)
7. `requiredStatus` (`ok`, `optional`)
8. `claimScope` (`l2_component_only`, `l2_diagnostic_only`)
9. `claimLanguage`

## Gate Requirements

Nursery superset gate must fail when:

1. generated projection rows are not 1:1 with `L0` workload IDs,
2. any `high` or `medium` row lacks an `L1` scenario template,
3. any `non_projectable` row is incorrectly marked as `L1`,
4. projection hashes drift from active workloads/rules,
5. a provided layered browser report misses any required projected `L1` row,
6. required `L1/L2` rows are present without explicit `status` + `statusCode`,
7. report claim-scope fields drift from projection/workflow contracts.

## Failure Taxonomy (Browser Lane)

Required stable status codes:

1. `ok`
2. `l0_only`
3. unsupported class:
   - `adapter_null`
   - `webgpu_unavailable`
   - `api_unsupported`
   - `sandbox_constraint`
   - `launch_surface_unavailable`
   - `scenario_template_unknown`
4. failure class:
   - `browser_launch_failed`
   - `mode_setup_failed`
   - `scenario_runtime_error`

## Claim Semantics

1. `L0` claim language remains strict and release-policy gated.
2. `L1` can use strict claim language only when timing scope and semantics align.
3. `L2` must use workflow/component claim language; no direct substitution for `L0`.
4. reports must explicitly label layer and comparability expectation.

## Promotion Out of Nursery

Promote only after:

1. projection and workflow schemas are stable,
2. generator + gate run green over repeated windows,
3. browser layer artifacts are reproducible and traceable,
4. ownership for maintenance is explicit.

## Cadence and Approvals

Execution cadence:

1. daily browser smoke runs,
2. twice-weekly layered browser benchmark runs,
3. weekly promotion review.

Promotion gate approvals (required):

1. `track_b_contracts_owner`
2. `coordinator`

## Artifact Discipline

1. Diagnostic browser artifacts remain nursery-local or under `bench/out/scratch`.
2. Writing diagnostics to canonical `bench/out` claim paths is prohibited by default.
3. Promotion to canonical `bench/out` requires formal promotion review + approvals.

## Rollback Triggers

1. hand-maintained scenario drift from workload source-of-truth,
2. hidden toggles affecting comparability semantics,
3. missing runtime-mode evidence in reports,
4. claim wording that exceeds scenario class.

## Ownership Split

1. Chromium lane lead: Playwright harness and workflow scenarios.
2. Contracts liaison: projection rules and schema/hash checks.
3. Coordinator: promotion boundary control from diagnostics to claim-adjacent artifacts.
