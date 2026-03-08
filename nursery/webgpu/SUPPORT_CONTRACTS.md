# Proposed support contracts for core and full

Contract status: `draft`

Scope:

- proposed future layering for Doe's JS-facing package surfaces
- headless WebGPU support contracts only
- no runtime behavior changes are enabled by this document

This document defines a target support split for two future Doe package
surfaces:

1. `core`
   - minimal headless WebGPU surface
   - compute-first
   - explicit unsupported for render/browser-parity gaps
2. `full`
   - full headless WebGPU surface
   - strict superset of `core`
   - still not a browser-process integration contract

This is intentionally separate from Chromium Track A. Chromium integration
depends on the full runtime artifact plus browser-specific drop-in gates; it
must not depend on npm packaging shape.

Boundary-enforcement and refactor-order details are defined in
`LAYERING_PLAN.md`.

## Dependency contract

The layering rule is one-way:

1. `full` may import and extend `core`.
2. `core` must not import `full`.
3. `full` may reuse `core` Zig modules, Lean theorems, tests, and JS helpers.
4. `core` must remain releaseable and testable without `full`.
5. Chromium Track A depends on the full runtime artifact and browser gates, not
   on the `@simulatte/webgpu` package surface.

Implementation intent:

1. Zig:
   - `zig/src/core/**` contains shared runtime, compute, buffer/resource,
     trace/replay, and backend-common code
   - `zig/src/full/**` contains render, surface, and broader lifecycle/parity
     layers built on `core`
2. Lean:
   - `lean/Fawn/Core/**` contains shared invariants
   - `lean/Fawn/Full/**` may import `Core` and add render/lifecycle proofs
3. Build outputs:
   - `core` and `full` can be emitted as separate artifacts
   - if separate binaries are used, `full` is built from `core` sources; `core`
     must not dynamically depend on a `full` artifact

## Support level definitions

Each capability in the tables below uses one of these support levels:

1. `required`
   - surface must expose it and gate it as part of release acceptance
2. `limited`
   - surface may expose only a constrained subset documented by contract
   - unsupported portions must fail explicitly
3. `out_of_scope`
   - surface does not promise it
   - if present experimentally, it must be labeled diagnostic and must not be a
     release requirement

## Product boundary

Three surfaces are implied by this split:

1. `core`
   - headless compute-first package/runtime
2. `full`
   - headless full WebGPU package/runtime
3. Chromium Track A
   - browser integration seam, wire/proc/drop-in parity, fallback policy,
     process topology, and browser-specific gates

`full` is the top of the headless stack, not the browser stack.
Browser-owned semantics remain outside both `core` and `full`.

## Core support contract

### Target user

- ML inference
- simulation
- data processing
- CI and benchmark orchestration
- deterministic headless command execution

### Promise

`core` promises a stable compute-first headless WebGPU surface with explicit
unsupported behavior for render-heavy and browser-owned semantics.

### Capability contract

| Capability area | `core` support | Notes |
| --- | --- | --- |
| `GPU` / adapter / device discovery | `required` | `requestAdapter`, `requestDevice`, limits/features reporting |
| `GPUQueue` submit and `writeBuffer` | `required` | deterministic timing/trace contracts required |
| Buffer create / destroy / map / unmap | `required` | mapping semantics may be synchronous or async by contract, but must be explicit |
| Copy / clear / barrier command encoding | `required` | explicit unsupported on unsupported backend paths |
| Shader module creation for compute | `required` | WGSL compute path required |
| Compute pipeline create / async create | `required` | async behavior may be wrapper-backed but must be contract-defined |
| Bind group layout / bind group / pipeline layout | `required` | core resource binding model |
| Compute passes and dispatch | `required` | direct and indirect dispatch where contract-required |
| Compute-visible textures / texture views / samplers | `limited` | only non-presentable compute/storage/sampled usage required |
| Render pipeline / render pass / render bundles | `out_of_scope` | must fail explicitly or be absent |
| Vertex / index input state | `out_of_scope` | belongs to `full` |
| Blend / depth-stencil / multisample | `out_of_scope` | belongs to `full` |
| Query sets / render timestamps / occlusion | `limited` | only compute-claimability queries required where benchmark contracts demand them |
| Error scopes / compilation info / device lost | `limited` | explicit subset contract only; broad parity is not required |
| Surface / presentation / `GPUCanvasContext` | `out_of_scope` | browser-owned or full/browser-specific |
| Browser object-model parity | `out_of_scope` | no claim of npm `webgpu` drop-in compatibility |

### Release gates for `core`

`core` acceptance requires:

1. schema, correctness, and trace gates green
2. package contract tests green for Node and declared Bun surface
3. CTS subset coverage for:
   - adapter/device acquisition
   - buffers
   - copy/upload
   - compute pipeline
   - compute dispatch
4. benchmark cube evidence limited to:
   - upload
   - compute e2e
   - dispatch-only
5. explicit unsupported taxonomy for any render, surface, or browser-parity API
   request outside the `core` contract

### Non-goals for `core`

1. full WebGPU JS object-model parity
2. render pipeline completeness
3. browser presentation parity
4. Chromium drop-in readiness by itself

## Full support contract

### Target user

- headless rendering
- offscreen graphics testing
- broader WebGPU package compatibility
- future Chromium runtime-artifact dependency

### Promise

`full` promises a full headless WebGPU surface. It is a strict superset of
`core`, but it still does not claim browser-process ownership, DOM integration,
or Chromium wire/drop-in readiness by itself.

### Capability contract

| Capability area | `full` support | Notes |
| --- | --- | --- |
| All `core` capabilities | `required` | `full` is a strict superset of `core` |
| Render pipeline creation | `required` | vertex + fragment pipeline support |
| Render pass encoding | `required` | begin/end, attachments, load/store ops |
| Render bundles | `required` | where supported by backend contract |
| Vertex / index buffers and draw variants | `required` | direct + indirect forms per contract |
| Textures / views / samplers across render + compute | `required` | includes render-attachment usage classes |
| Blend state / depth-stencil / multisample | `required` | full render-state contract |
| Query sets / timestamps / occlusion | `required` | explicit backend support and unsupported taxonomy where unavailable |
| Async pipeline creation / compilation info | `required` | no silent downgrade to hidden sync path |
| Error scopes / lifecycle semantics / device lost reporting | `required` | headless full object-model contract |
| Texture format table | `required` | supported set must be explicit and schema-tracked |
| Surface / present APIs for headless or native presentation paths | `limited` | native/headless surface contract may exist, but browser canvas ownership is still out of scope |
| `GPUCanvasContext`, DOM, HTML canvas wiring | `out_of_scope` | belongs to Chromium/browser integration |
| Chromium wire/proc/drop-in parity | `out_of_scope` | belongs to Track A |

### Release gates for `full`

`full` acceptance requires:

1. every `core` gate remains green
2. full contract tests green for Node and declared Bun surface
3. broader CTS subset coverage for:
   - render pipeline creation
   - render pass execution
   - texture formats and sampling
   - bind-group and pipeline-layout behavior
   - query/lifecycle/error-scope paths
4. benchmark cube evidence may include:
   - upload
   - compute e2e
   - render
   - texture/raster
5. explicit unsupported taxonomy for any capability not yet in the full release
   contract
6. no marketing or docs claim browser parity unless Track A browser gates also
   pass

### Non-goals for `full`

1. replacing Chromium's process model
2. owning browser fallback policy
3. claiming `navigator.gpu` parity in the browser
4. bypassing Track A symbol/behavior/replay/drop-in gates

## Browser boundary contract

The following capabilities are not owned by `core` or `full` package contracts:

1. `navigator.gpu` behavior inside Chromium
2. Dawn-wire or proc-surface completeness requirements
3. browser fallback policy, denylist policy, kill switch policy
4. renderer/GPU-process topology
5. browser presentation semantics tied to DOM/canvas ownership

These belong to Chromium Track A and must be governed by:

- `nursery/fawn-browser/README.md`
- `nursery/fawn-browser/plan.md`
- drop-in symbol/behavior/benchmark gates
- browser replay and claimability artifacts

## Current repo reality

This split is not yet how the repo is physically organized today.

Current state:

1. the canonical package is still a single `@simulatte/webgpu` surface
2. current package code already exposes some render objects and methods
3. current Zig/runtime docs track a single Doe runtime capability ledger

This document is therefore a target contract for future sharding, not a claim
that the split already exists.

## Adoption rules

Before naming or shipping separate `core` and `full` products:

1. create separate support ledgers and gates for each surface
2. enforce one-way import boundaries in Zig and Lean
3. move render/surface/lifecycle code out of the shared core path
4. define separate package API contracts and compatibility scopes
5. keep Chromium depending on the full runtime artifact, not on npm packaging
