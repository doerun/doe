# Proposed layering plan for core and full

Plan status: `draft`

Scope:

- future Doe runtime/package sharding for headless WebGPU
- architecture and refactor sequencing only
- no current runtime behavior changes

This plan exists to keep the future `core` and `full` split honest before any
Zig source moves begin.

It answers four questions:

1. what boundary is being enforced
2. how that boundary is enforced in code review and CI
3. how capability coverage and gates split once the boundary exists
4. what order the refactor should happen in

Use this together with:

- `SUPPORT_CONTRACTS.md` for product/support scope
- `API_CONTRACT.md` for the current single-surface package contract
- `COMPAT_SCOPE.md` for current package non-goals
- `ZIG_SOURCE_INVENTORY.md` for the current `zig/src` file map

## Current state

The repo is not physically split into `core` and `full` today.

Current reality:

1. `zig/src/` is still mostly a shared runtime tree
2. an initial `zig/src/core/` namespace exists for extracted compute/copy/sync shards, with compatibility shims left at the old root paths
3. render and surface-related code still largely lives in the shared runtime layer
4. the JS package already exposes some render-facing APIs
5. capability tracking is still represented by one shared coverage ledger

That means this plan is a prerequisite for refactoring, not a description of an
already-landed layout.

## Boundary definition

The target architecture is:

```text
Doe core
  ^
  |
Doe full
  ^
  |
Chromium Track A runtime artifact lane
```

Rules:

1. `full` composes `core`; it does not toggle `core`.
2. `core` must never import `full`.
3. `full` may depend on `core` Zig modules, Lean modules, build outputs, and JS
   helpers.
4. Chromium Track A depends on the full runtime artifact and browser-specific
   gates, not on npm package layout.

The anti-bleed rule is the core of the design:

- no `if full_enabled` branches inside `core`
- no `full` fields added to `core` structs
- no browser-policy logic added to `full`

## Import fence rule

This is the primary long-term enforcement rule.

### Contract

1. `zig/src/core/**` may not import any file under `zig/src/full/**`
2. `lean/Fawn/Core/**` may not import any file under `lean/Fawn/Full/**`
3. package-level `core` entrypoints may not import `full` entrypoints
4. any exception requires redesign, not a one-off waiver

### CI enforcement

Add a dedicated import-fence check that fails if:

1. a Zig file under `core` references `full/`
2. a Lean file under `Core` references `Full`
3. a package `core` entrypoint reaches into a `full`-only module

The check should be a simple, explicit path-dependency audit. This is not a
lint preference; it is a release-blocking architectural boundary.

## Struct wrapping rule

`full` must extend `core` by composition, never by mutating `core` types in
place.

### Contract

1. if `full` needs shared state, it holds a `core` value or handle
2. if `full` needs extra state, that state lives in a `full` wrapper type
3. `core` structs may not gain render/surface/full-only fields just because
   `full` needs them
4. `core` APIs may expose stable extension points, but not latent `full`
   payload slots

### Example direction

Good shape:

```text
full.RenderPipeline
  - core_pipeline_layout: core.PipelineLayout
  - full_render_state: ...
```

Bad shape:

```text
core.PipelineLayout
  - maybe_render_state_if_full_enabled: ...
```

The intent is to keep `core` independently understandable, buildable, and
benchmarked.

## Coverage split rule

The current shared capability ledger is not enough once `core` and `full`
become separate release surfaces.

### Target split

1. `config/webgpu-core-coverage.json`
   - only `core` contractual capabilities
2. `config/webgpu-full-coverage.json`
   - `core` plus `full` contractual capabilities
3. Chromium Track A keeps its own browser/drop-in evidence and must not be
   represented as mere package coverage

### Gate split

`core` gates should validate:

1. core package contract
2. core CTS subset
3. core package-surface benchmark cells
4. explicit unsupported taxonomy outside core scope

`full` gates should validate:

1. all core gates
2. full package contract
3. expanded CTS subset for render/lifecycle/query coverage
4. full package-surface benchmark cells
5. explicit unsupported taxonomy outside full scope

Track A gates remain separate:

1. drop-in symbol completeness
2. drop-in behavior suite
3. browser replay and trace parity
4. browser performance claimability

## Proposed source layout

Target layout:

```text
zig/src/core/
  mod.zig
  trace/
  replay/
  abi/
  resource/
  queue/
  compute/
  backend/common/
  backend/{metal,vulkan,d3d12}/core/

zig/src/full/
  mod.zig
  render/
  surface/
  lifecycle/
  backend/{metal,vulkan,d3d12}/full/
```

Matching Lean layout:

```text
lean/Fawn/Core/
lean/Fawn/Full/
```

Matching package layout can be one of:

1. one package with scoped exports
2. separate packages with separate contracts

Packaging choice is secondary. The source boundary must come first.

## Refactor order

Do not start by renaming packages.

Recommended order:

1. freeze support contracts
   - define what `core` and `full` promise
2. add import-fence CI checks
   - enforce the one-way dependency before extraction starts
3. add split coverage ledgers and split gate entrypoints
   - even if both initially point at the current shared runtime
4. identify shared runtime modules that are genuinely `core`
   - trace, replay, buffers, queue, compute, shared resource model
5. identify `full`-only modules
   - render, surface, broader lifecycle/parity layers
6. extract `full` wrappers around `core` types
   - composition only
7. move render/surface code out of the shared tree
   - no behavior change intended during extraction
8. split package/API contracts
   - only after the runtime boundary is real
9. retarget Chromium Track A to the full runtime artifact contract
   - no npm package dependency in architecture docs

## Review checklist for future changes

Any future patch touching this split should answer:

1. does `core` now depend on `full` anywhere
2. did a `core` struct gain a `full`-only field
3. did a coverage or gate responsibility move without contract updates
4. did a browser-owned behavior get assigned to `core` or `full`
5. did packaging get ahead of the runtime boundary

If any answer is yes, the patch should be treated as architecture drift until
the contract is updated or the design is corrected.

## Immediate next artifacts

Before touching runtime code, add:

1. import-fence enforcement script/check
2. split coverage contracts for `core` and `full`
3. source inventory:
   - `ZIG_SOURCE_INVENTORY.md`

The inventory and initial import-fence check now exist. The next technical step
after this document is extracting the mixed top-level command/type/runtime
boundary.
