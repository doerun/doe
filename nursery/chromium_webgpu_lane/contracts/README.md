# Contracts Index

This directory contains contract drafts for the Chromium WebGPU lane.

These files define candidate module boundaries and promotion expectations before implementation.

## Files

1. `runtime-selector-and-fallback.contract.md`
   - Track A runtime selection, kill switch, denylist, and fallback contract.
2. `fawn-2d-sdf-renderer.contract.md`
   - Track B 2D SDF/MSDF renderer module contract.
3. `fawn-path-engine.contract.md`
   - Track B path processing and fallback contract.
4. `fawn-effects-pipeline.contract.md`
   - Track B effects graph contract.
5. `fawn-compute-services.contract.md`
   - Track B internal compute services contract.
6. `fawn-resource-scheduler.contract.md`
   - Track B resource and submit-cadence scheduler contract.
7. `module-contract-matrix.md`
   - Cross-module input/output schema fields, required gates, and rollout KPIs.
8. `browser-benchmark-superset.contract.md`
   - Layered browser benchmark superset contract (`L0`/`L1`/`L2`) and projection/gate rules.
   - includes hash-synchronization, status-code taxonomy, cadence, and promotion-approval policy.

## Contract Rules

1. Every contract must define:
   - input shape,
   - output artifacts,
   - failure taxonomy,
   - fallback policy,
   - gate coverage,
   - promotion criteria.
2. Any runtime-visible field promoted from these drafts must gain:
   - schema entries under `fawn/config/*schema*.json`,
   - migration notes under `fawn/config/migration-notes.md`,
   - status/process updates when behavior changes.
3. No draft in this directory may silently alter core runtime behavior.

## Draft Status

All contracts here are `draft` and non-binding until promoted through Fawn stage and gate policy.
