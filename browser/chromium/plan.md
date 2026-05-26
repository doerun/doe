# Chromium browser integration plan

This file is the browser-lane acceptance plan. The actual Chromium WebGPU task
list lives in
[`../../docs/chromium-webgpu-dominance.md`](../../docs/chromium-webgpu-dominance.md).
Live milestone state lives in
[`bench/workflows/browser-milestones.json`](bench/workflows/browser-milestones.json)
and is checked by [`scripts/check-browser-milestones.py`](scripts/check-browser-milestones.py).

Do not add parallel strategy prose here. Add new work to the canonical task
list, then update this plan only when the acceptance gate or browser-lane
artifact route changes.

## Scope

- Own forced-Doe Chromium WebGPU integration at the `navigator.gpu` seam.
- Preserve Chromium process, sandbox, layout, media, and accessibility policy.
- Keep Dawn available as explicit fallback until replacement gates say
  otherwise.
- Disable hidden fallback in claim mode.
- Emit deterministic artifacts for runtime selection, fallback state, trace
  continuity, and workload evidence.

## Milestone acceptance gates

### M0. Contracts

- Runtime selector contract exists.
- Browser benchmark and claim methodology contracts exist.
- Ownership, rollback, and artifact routes are schema-backed.
- Milestone state is represented in the manifest.

### M1. Forced runtime selection

- Chromium launches in explicit `dawn`, `doe`, and `auto` modes.
- Forced `doe` mode fails closed when Doe cannot initialize.
- `auto` mode falls back with typed reason codes.
- Runtime selection fields appear in browser artifacts.

### M2. Compatibility

- Drop-in ABI and symbol gates pass for required browser-lane artifacts.
- Browser WebGPU smoke and layered rows run under both Dawn and forced Doe.
- CTS subset artifacts are linked when available.
- Trace and replay artifacts pass hash-chain checks.
- Hidden runtime switches are rejected.

### M3. Claim qualification

- Browser reports explicitly classify `diagnostic` vs `claimable`.
- Claimable rows pass strict timing-scope and structural-equivalence checks.
- Repeated browser claim artifacts pass the browser claim policy.
- Browser claim reports stay separate from native/package claims.

## Current task source

Use the canonical task list for all new work:

- compiler tasks against Tint
- runtime tasks against Dawn
- Chromium seam tasks
- browser responsibility map tasks
- browser capability tasks beyond current Chrome behavior
- security and fork-maintenance tasks

See
[`../../docs/chromium-webgpu-dominance.md`](../../docs/chromium-webgpu-dominance.md).

## Archived module references

The old Track B module contracts are archived and inactive:

- `fawn_2d_sdf_renderer`
- `fawn_path_engine`
- `fawn_effects_pipeline`
- `fawn_compute_services`
- `fawn_resource_scheduler`

Use those files only as historical contract references. New browser work must
start from the canonical task list and promote through schema, trace, gate, and
artifact contracts before runtime behavior changes.
