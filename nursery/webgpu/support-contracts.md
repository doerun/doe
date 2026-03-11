# Proposed support contracts for core, full, and browser boundary

Contract status: `draft`

Scope:

- proposed future layering for Doe's JS-facing package surfaces
- headless WebGPU package/runtime contracts only
- browser-owned Chromium semantics are called out explicitly as outside package
  ownership
- no runtime behavior changes are enabled by this document

This document defines three explicit layers:

1. `compute` (`core` runtime boundary)
   - compute-first headless WebGPU for AI workloads and other buffer/dispatch-heavy tasks
   - minimal releaseable package/runtime surface
   - explicit unsupported for sampled/render/browser gaps
2. `full`
   - full headless WebGPU
   - strict superset of `core`
   - still not a browser-process integration contract
3. browser / Track A
   - Chromium-only integration seam
   - not package-owned
   - owns DOM/canvas/process/fallback/proc-surface concerns

This split is intentionally separate from Chromium Track A. Chromium integration
depends on the full runtime artifact plus browser-specific gates; it must not
depend on npm packaging shape.

Boundary-enforcement and refactor-order details are defined in
[`./layering-plan.md`](./layering-plan.md).

## Dependency contract

The layering rule is one-way:

1. `full` may import and extend `core`.
2. `core` must not import `full`.
3. browser / Track A may depend on the full runtime artifact and browser-owned
   contracts.
4. `core` and `full` must not own Track A browser behavior.
5. `core` must remain releaseable and testable without `full`.

Implementation intent:

1. Zig:
   - `zig/src/core/**` contains shared runtime, compute, copy/upload, limited
     compute-visible texture handling, trace/replay, and backend-common code
   - `zig/src/full/**` contains sampled textures, render, surface, and broader
     lifecycle/parity layers built on `core`
2. Lean:
   - `lean/Fawn/Core/**` contains shared invariants
   - `lean/Fawn/Full/**` may import `Core` and add render/lifecycle proofs
3. Build outputs:
   - `core` and `full` can be emitted as separate artifacts
   - if separate binaries are used, `full` is built from `core` sources; `core`
     must not dynamically depend on a `full` artifact

## Product boundary

Three surfaces are implied by this split:

1. `compute`
   - headless compute-first package/runtime
2. `full`
   - headless full WebGPU package/runtime
3. browser / Track A
   - browser integration seam, wire/proc/drop-in parity, fallback policy,
     process topology, and browser-specific gates

`full` is the top of the headless stack, not the browser stack.
Browser-owned semantics remain outside both `core` and `full`.

## Ownership matrix

| Capability area | `core` | `full` | browser / Track A |
| --- | --- | --- | --- |
| `GPU`, `GPUAdapter`, `GPUDevice`, `GPUQueue` | `required` | inherits `core` | not package-owned |
| `GPUBuffer` | `required` | inherits `core` | not package-owned |
| `GPUShaderModule` for compute WGSL | `required` | inherits `core` | not package-owned |
| `GPUBindGroupLayout`, `GPUBindGroup`, `GPUPipelineLayout` | `required` | inherits `core` | not package-owned |
| `GPUComputePipeline` | `required` | inherits `core` | not package-owned |
| `GPUCommandEncoder` for copy/upload/clear/barrier/compute | `required` | inherits `core` | not package-owned |
| `GPUComputePassEncoder` | `required` | inherits `core` | not package-owned |
| `dispatchWorkgroups`, `dispatchWorkgroupsIndirect` | `required` | inherits `core` | not package-owned |
| `GPUTexture` / `GPUTextureView` for compute-visible usages only | `required` | inherits and extends | not package-owned |
| `GPUSampler` | `out_of_scope` | `required` | not package-owned |
| `GPURenderPipeline` | `out_of_scope` | `required` | not package-owned |
| `GPURenderPassEncoder` | `out_of_scope` | `required` | not package-owned |
| `GPURenderBundleEncoder` | `out_of_scope` | `required` | not package-owned |
| Vertex / index buffers and draw variants | `out_of_scope` | `required` | not package-owned |
| Blend / depth-stencil / multisample | `out_of_scope` | `required` | not package-owned |
| Render-attachment textures | `out_of_scope` | `required` | not package-owned |
| Broader texture / view / format coverage | `limited` | `required` | not package-owned |
| `GPUCanvasContext` | `out_of_scope` | `out_of_scope` | `required` |
| DOM / canvas ownership | `out_of_scope` | `out_of_scope` | `required` |
| Proc-surface parity | `out_of_scope` | `out_of_scope` | `required` |
| Fallback policy / denylist / kill switch | `out_of_scope` | `out_of_scope` | `required` |
| Chromium process behavior | `out_of_scope` | `out_of_scope` | `required` |

## Compute support contract (`core` runtime, `@simulatte/webgpu/compute` export)

### Target user

- AI workloads
- simulation
- data processing
- CI and benchmark orchestration
- deterministic headless command execution

### Promise

`compute` promises a stable compute-first headless WebGPU surface sized for AI
workloads and other buffer/dispatch-heavy headless execution, with explicit
unsupported behavior for sampled-texture, render, and browser-owned semantics.

### Included object model

`compute` includes:

- `GPU`, `GPUAdapter`, `GPUDevice`, `GPUQueue`
- `GPUBuffer`
- `GPUShaderModule` for compute WGSL
- `GPUBindGroupLayout`, `GPUBindGroup`, `GPUPipelineLayout`
- `GPUComputePipeline`
- `createComputePipelineAsync`
- `GPUCommandEncoder` for copy, upload, clear, barrier, and compute encoding
- `GPUComputePassEncoder`
- `dispatchWorkgroups`
- `dispatchWorkgroupsIndirect`
- queue `writeBuffer`
- buffer readback via `MAP_READ` + `copyBufferToBuffer`
- Node/Bun bootstrap globals required for headless execution:
  - `navigator.gpu`
  - `GPUBufferUsage`
  - `GPUShaderStage`
  - `GPUMapMode`
  - `GPUTextureUsage`

### WGSL contract

WGSL required in `compute`:

- storage buffers
- uniform buffers
- workgroup buffers
- atomics
- barriers

WGSL out of scope for `compute`:

- sampler declarations and binding semantics
- `textureSample*`
- vertex stage
- fragment stage
- render-attachment behavior

### Explicit exclusions

`compute` does not own:

- `GPUSampler`
- sampled textures
- `GPURenderPipeline`
- `GPURenderPassEncoder`
- `GPURenderBundleEncoder`
- vertex/index input state
- draw/drawIndexed/drawIndirect
- blend/depth-stencil/multisample
- render-attachment textures
- `GPUCanvasContext`
- DOM/canvas ownership
- proc-surface parity
- Chromium fallback/process policy

### Release gates for `core`

`compute` acceptance requires:

1. schema, correctness, and trace gates green
2. package contract tests green for Node and declared Bun surface
3. CTS subset coverage for:
   - adapter/device acquisition
   - buffers
   - copy/upload
   - readback
   - compute pipeline
   - compute dispatch
4. benchmark cube evidence limited to:
   - upload
   - compute e2e
   - dispatch-only
5. explicit unsupported taxonomy for any sampler, sampled-texture, render,
   surface, or browser API request outside the `core` contract

### Non-goals for `compute`

1. full WebGPU JS object-model parity
2. sampled-texture semantics
3. render pipeline completeness
4. browser presentation parity
5. Chromium drop-in readiness by itself

## Full support contract

### Target user

- headless rendering
- offscreen graphics testing
- broader WebGPU package compatibility
- future Chromium runtime-artifact dependency

### Promise

`full` promises a full headless WebGPU surface. It is a strict superset of
`compute`, but it still does not claim browser-process ownership, DOM
integration, or Chromium wire/drop-in readiness by itself.

### Added object model

`full` adds:

- `GPURenderPipeline`
- `GPURenderPassEncoder`
- `GPURenderBundleEncoder`
- vertex buffers
- index buffers
- `draw`
- `drawIndexed`
- `drawIndirect`
- render-state objects and behavior for blend, depth-stencil, and multisample
- `GPUSampler`

### Texture contract

`full` adds the texture/render surface that `core` deliberately excludes:

- sampled textures
- render-attachment textures
- broader texture/view/format coverage
- texture/view behavior needed by render pipelines and broader headless package
  compatibility

### WGSL additions

WGSL added in `full`:

- sampler declarations and binding semantics
- `textureSample*`
- vertex stage
- fragment stage

`full` therefore owns the shader and object-model pieces needed for sampled
textures and render semantics. It still does not own DOM/canvas behavior.

### Still outside `full`

`full` still does not own:

- `GPUCanvasContext`
- DOM/canvas ownership
- proc-surface parity
- browser fallback policy
- Chromium process behavior

### Release gates for `full`

`full` acceptance requires:

1. every `core` gate remains green
2. full contract tests green for Node and declared Bun surface
3. broader CTS subset coverage for:
   - render pipeline creation
   - render pass execution
   - render bundles where contract-required
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

## Browser / Track A boundary contract

The following capabilities are not owned by `core` or `full` package contracts:

- `GPUCanvasContext`
- DOM/canvas ownership
- `navigator.gpu` behavior inside Chromium
- proc-surface completeness requirements
- browser fallback policy, denylist policy, and kill-switch policy
- renderer/GPU-process topology
- Chromium process behavior

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
3. move render, sampled-texture, and surface/lifecycle code out of the shared
   core path
4. define separate package API contracts and compatibility scopes
5. keep Chromium depending on the full runtime artifact, not on npm packaging
