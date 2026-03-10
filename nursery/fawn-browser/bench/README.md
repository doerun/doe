# Browser Benchmark Superset (Nursery)

This module implements a layered browser benchmark superset for Chromium Track A (browser).

## Layers

1. `L0 engine`
   - core strict runtime benchmark (`bench/workloads.amd.vulkan.extended.json`).
2. `L1 browser-api`
   - Playwright-driven browser WebGPU projections derived from `L0`.
3. `L2 browser-workflow`
   - browser end-to-end workflows that include WebGPU and browser lifecycle overhead.

## No-Maintenance Rule

1. Do not hand-maintain workload lists in nursery.
2. Generate projection manifest from core workloads using:
   - `scripts/generate-browser-projection-manifest.py`
3. Use `bench/projection-rules.json` for classification and scenario-template mapping.

## Files

1. `projection-rules.json`
   - domain -> projection-class/scenario-template mapping plus required-status and claim-scope.
2. `projection-manifest.schema.json`
   - schema for generated projection manifest.
3. `generated/browser_projection_manifest.json`
   - generated `L1/L0` projection rows with contract hashes.
4. `workflows/browser-workflow-manifest.json`
   - `L2` workflow definitions with required status, claim scope, and promotion approver roles.
5. `workflows/browser-workflow-manifest.schema.json`
   - schema for `L2` workflow manifest.
6. `workflows/browser-promotion-approvals.json`
   - explicit promotion approvals (`module_contracts_owner`, `coordinator`).
7. `workflows/browser-promotion-approvals.schema.json`
   - schema for promotion approval artifact.
8. `workflows/browser-milestones.json`
   - source-of-truth milestone state for M0-M6.
9. `workflows/browser-milestones.schema.json`
   - schema for milestone tracking.

## Scripts

1. `scripts/generate-browser-projection-manifest.py`
   - emits generated manifest from core workload source.
2. `scripts/webgpu-playwright-layered-bench.mjs`
   - runs `L1` and `L2` browser benchmark layers for dawn/doe.
3. `scripts/check-browser-benchmark-superset.py`
   - validates projection completeness/hash sync, optional report coverage, and optional promotion approvals.
4. `scripts/run-browser-benchmark-superset.py`
   - one-command orchestration (generate -> run -> check -> summary + checker artifact).
5. `scripts/check-browser-milestones.py`
   - validates milestone state and required local evidence for M0-M6.

## Quick Start

From `` root:

```bash
npm install --prefix nursery/fawn-browser playwright-core
./nursery/fawn-browser/scripts/run-bench.sh
```

To run dawn/doe against different browser executables in one benchmark run:

```bash
./nursery/fawn-browser/scripts/run-bench.sh \
  --mode both \
  --dawn-chrome /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --doe-chrome nursery/fawn-browser/out/fawn_release_local/Fawn.app/Contents/MacOS/Chromium
```

Default outputs are lane-local diagnostic artifacts under:

- `nursery/fawn-browser/artifacts/<timestamp>/dawn-vs-doe.browser-layered.superset.diagnostic.json`
- `nursery/fawn-browser/artifacts/<timestamp>/dawn-vs-doe.browser-layered.superset.check.json`
- `nursery/fawn-browser/artifacts/<timestamp>/dawn-vs-doe.browser-layered.superset.summary.json`

If you intentionally need `bench/out`, pass `--allow-bench-out` explicitly.
Diagnostic outputs under `bench/out` are restricted to `bench/out/scratch`.

## Cadence

1. Daily browser smoke runs.
2. Twice-weekly layered benchmark runs.
3. Weekly promotion review.

## Promotion Gate

Promotion candidates must pass:

1. hash-synchronized projection contract checks,
2. explicit status/statusCode evidence for required `L1/L2` rows,
3. promotion approvals from `module_contracts_owner` and `coordinator`.
