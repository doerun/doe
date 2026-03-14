# Proposed package plan for `@simulatte/webgpu-doe`

Plan status: `draft`

Scope:

- JS package boundary for the existing Doe API / Doe routines layer
- package/export/refactor sequencing only
- no immediate runtime behavior change required

This plan exists because the current `nursery/webgpu` codebase already has a
real logical split:

1. raw full WebGPU surface
2. raw compute-first WebGPU surface
3. shared Doe API / Doe routines JS layer on top

The missing piece is packaging. We already own the package name
`@simulatte/webgpu-doe`, and the code is already structured close to that
boundary.

This document answers:

1. what `@simulatte/webgpu-doe` should mean
2. what code already belongs to that package today
3. what still couples it to `@simulatte/webgpu`
4. what extraction order keeps the split honest
5. what should not change during the split

Use this together with:

- `README.md` for the current package surface story
- `api-contract.md` for the current `full` + `compute` contract
- `layering-plan.md` for the broader core/full runtime split
- `support-contracts.md` for the current support surface

## Package picture

The intended package family is:

```text
@simulatte/webgpu
  raw full headless surface
  + re-exported Doe API / Doe routines layer

@simulatte/webgpu/compute
  raw compute-first headless surface
  + re-exported Doe API / Doe routines layer

@simulatte/webgpu-doe
  shared JS helper layer only
  no addon
  no native library loading
```

This is not a proposal to create three different runtimes.

It is a proposal to make the already-existing JS layering explicit:

1. raw full surface
2. raw compute surface
3. shared helper surface above both

## How the three packages should work together

### `@simulatte/webgpu`

Role:

- the canonical headless full-surface package
- owns native addon loading
- owns library discovery
- owns full raw device and adapter classes
- re-exports the Doe helper layer for convenience

User story:

- install this when you want the default package
- use it when you need raw WebGPU plus render/textures/samplers
- also use it when you want Doe helpers without losing access to the raw full device

### `@simulatte/webgpu/compute`

Role:

- the compute-first subpath of the same runtime package family
- owns the compute-only raw facade
- narrows the raw device surface
- re-exports the same Doe helper layer

User story:

- install this when you want the constrained compute package contract
- use it when you want a simpler AI/ML/buffer-dispatch-oriented surface
- also use it when you want the same Doe helper layer over a compute-only raw device

### `@simulatte/webgpu-doe`

Role:

- the shared JS helper layer only
- exports the helper namespace and helper factory
- does not own any native runtime bootstrap

User story:

- install this only when you explicitly want the helper layer as its own dependency
- use it when you are composing your own host package or advanced runtime wiring
- use it when you want the Doe API / Doe routines abstraction without tying documentation or ownership to the raw package directly

## What gets installed

### Case 1: default full-surface users

Install:

```bash
npm install @simulatte/webgpu
```

What they get:

- native addon / prebuild handling
- runtime library discovery
- full raw device surface
- re-exported Doe API / Doe routines surface

What they do not need to install separately:

- `@simulatte/webgpu-doe`

Why:

- the default package should continue to be a batteries-included entrypoint

### Case 2: compute-first users

Install:

```bash
npm install @simulatte/webgpu
```

Import:

```js
import { requestDevice, doe } from "@simulatte/webgpu/compute";
```

What they get:

- same runtime package install
- compute-only raw facade
- same Doe API / Doe routines layer

What they do not need to install separately:

- `@simulatte/webgpu-doe`

Why:

- `compute` is a subpath export of the main runtime package, not a separate npm package today

### Case 3: advanced helper-layer users

Install:

```bash
npm install @simulatte/webgpu @simulatte/webgpu-doe
```

or, if a future compute package becomes separately publishable:

```bash
npm install @simulatte/webgpu-compute @simulatte/webgpu-doe
```

What they get:

- one host runtime package
- one helper-only package

What they do with it:

- compose `createDoeNamespace(...)` over a host-provided `requestDevice`
- import the unbound `doe` namespace directly for helper-only composition

### Installation rule

`@simulatte/webgpu-doe` should not try to install or bootstrap the runtime by itself.

It should assume one of the host runtime packages is already present.

That means:

1. normal app users install the host runtime package only
2. advanced/composition users may install the helper package explicitly
3. the helper package must not pretend to be a standalone runtime

## What each package includes

### `@simulatte/webgpu`

Includes:

- native addon loader
- prebuilds
- full raw JS surface
- runtime metadata helpers
- Doe API / Doe routines re-export
- CLI/runtime wrapper helpers

Does not include:

- browser DOM/canvas ownership
- browser-process integration

### `@simulatte/webgpu/compute`

Includes:

- compute-only raw JS facade
- the same underlying runtime package
- Doe API / Doe routines re-export

Does not include:

- render methods on the public facade
- sampler methods on the public facade
- surface/presentation methods on the public facade

### `@simulatte/webgpu-doe`

Includes:

- `createDoeNamespace(...)`
- unbound `doe`
- `doe.bind(device)`
- `buffers.*`
- `compute.run(...)`
- `compute.compile(...)`
- `compute.once(...)`
- helper-layer validation and normalization

Does not include:

- native addon loading
- raw WebGPU constants as the primary API
- raw `GPUDevice`/`GPUAdapter` implementations
- platform/runtime probing
- runtime binaries or prebuilds

## Recommended dependency model

The first clean model is:

1. `@simulatte/webgpu` depends on `@simulatte/webgpu-doe`
2. `@simulatte/webgpu/compute` is a subpath of `@simulatte/webgpu` and also imports that dependency internally
3. `@simulatte/webgpu-doe` has no dependency back on the runtime package

That gives this direction:

```text
@simulatte/webgpu-doe   -> no native runtime dependency
@simulatte/webgpu       -> depends on @simulatte/webgpu-doe
@simulatte/webgpu/compute
                        -> subpath of @simulatte/webgpu, uses @simulatte/webgpu-doe
```

If we later publish `@simulatte/webgpu-compute` as its own npm package, it
should also depend on `@simulatte/webgpu-doe`.

### Why not peer dependencies first

Peer dependencies are possible, but they are a worse first move here.

Problems:

1. normal users would have to think about the helper package explicitly
2. host/runtime version skew becomes easier
3. the host packages would stop being batteries-included

Better first model:

- runtime packages depend on the helper package internally
- advanced users can still install `@simulatte/webgpu-doe` directly if they want explicit composition

## Proposed exports for each package

### `@simulatte/webgpu`

Should keep exporting:

- `create`
- `setupGlobals`
- `requestAdapter`
- `requestDevice`
- `providerInfo`
- `createDoeRuntime`
- `runDawnVsDoeCompare`
- `doe`

### `@simulatte/webgpu/compute`

Should keep exporting:

- `create`
- `setupGlobals`
- `requestAdapter`
- `requestDevice`
- `providerInfo`
- `createDoeRuntime`
- `runDawnVsDoeCompare`
- `doe`

### `@simulatte/webgpu-doe`

Should initially export:

- `createDoeNamespace`
- `doe`

May export later:

- `preflightShaderSource`
- typed helper interfaces if they move cleanly with the package

## Proposed package.json shape

The first version should be a pure ESM JS package.

Example:

```json
{
  "name": "@simulatte/webgpu-doe",
  "version": "0.1.0",
  "description": "Shared Doe API and Doe routines layer for Simulatte WebGPU packages",
  "type": "module",
  "main": "./src/index.js",
  "types": "./src/index.d.ts",
  "exports": {
    ".": {
      "types": "./src/index.d.ts",
      "default": "./src/index.js"
    }
  },
  "files": [
    "src/",
    "README.md",
    "CHANGELOG.md"
  ]
}
```

It should not include:

- `binding.gyp`
- `native/`
- `prebuilds/`
- runtime binaries

## Proposed file split

### First extraction target

Move:

- `src/doe.js`

Add in the new package:

- `src/index.js`
  - re-export `createDoeNamespace`
  - re-export `doe`

Possibly add:

- `src/index.d.ts`
  - extracted from the current `src/doe.d.ts`

### Files that stay in the host package

- `src/index.js`
- `src/full.js`
- `src/compute.js`
- `src/bun.js`
- `src/bun-ffi.js`
- `src/node-runtime.js`
- `native/`
- `prebuilds/`

### Type split recommendation

`src/doe.d.ts` already reflects the right conceptual boundary.

That means a clean extraction path is:

1. move `src/doe.js`
2. move `src/doe.d.ts`
3. make host `full.d.ts` and `compute.d.ts` import their Doe helper types from the new package

This is another sign the package boundary already exists conceptually.

## Extraction candidates

### First extraction: move with minimal churn

Move as-is:

- `src/doe.js`

Move soon after if the type boundary is extracted cleanly:

- `src/doe.d.ts`

Maybe move in the same change if we want a truly self-contained helper package:

- `src/wgsl_preflight.js`

Do not move yet:

- `src/index.js`
- `src/compute.js`
- `src/full.js`
- `src/bun-ffi.js`
- native addon code

### Why `wgsl_preflight.js` is optional

It is helper-layer behavior in spirit, but today it still reflects package
surface/compiler limitations and may be easier to keep with the host package
until the package contract stabilizes.

Reasonable staging:

1. first package split: move only `doe.js`
2. second pass: decide whether `wgsl_preflight.js` belongs in Doe or in the
   host runtime package

## What still couples the helper layer today

The split is already clean conceptually, but not fully hardened.

Current coupling points:

1. helper code assumes a particular raw device shape
2. helper code uses package-local validation and runtime conventions
3. helper code is tested today only through the host package
4. helper docs currently live inside the main package docs
5. some capability messaging still assumes the main package surface

These are not blockers, but they are the places where the extraction can go
sloppy if done carelessly.

## Refactor order

Do not start by renaming the current package.

Recommended order:

1. freeze the intended `@simulatte/webgpu-doe` contract
   - `createDoeNamespace`
   - `doe`
   - helper API only
2. add one package-local compatibility test that exercises `doe.js` against:
   - the full surface
   - the compute surface
3. split out `src/doe.d.ts` if needed so type ownership matches runtime ownership
4. move `src/doe.js` into the new package with no behavior change
5. update `@simulatte/webgpu` and `@simulatte/webgpu/compute` to import it
6. keep tests running in the host package first
7. add standalone smoke/docs for the Doe package itself
8. move optional helper modules later (`wgsl_preflight.js`) if still warranted

The rule is:

> extract the already-real boundary, do not invent a new abstraction mid-move

## Concrete extraction checklist

The first real implementation checklist should be:

1. create a new repo/package workspace for `@simulatte/webgpu-doe`
2. copy `src/doe.js`
3. copy or extract `src/doe.d.ts`
4. add package README explaining:
   - this is the helper layer only
   - it does not bootstrap the runtime
   - it expects a host raw surface
5. update `@simulatte/webgpu` to import `createDoeNamespace` from the new package
6. update `@simulatte/webgpu/compute` to import `createDoeNamespace` from the new package
7. keep existing host package tests green
8. add one explicit helper-layer composition test:
   - full raw device + Doe layer
   - compute raw device + Doe layer
9. only then decide whether `wgsl_preflight.js` should move too
10. only after that consider publishing docs that encourage direct installation of the Doe package

## Packaging recommendation

The first version of `@simulatte/webgpu-doe` should be a pure JS package.

That means:

1. no native addon
2. no prebuilds
3. no runtime shared library loading
4. no direct ownership of Node/Bun provider bootstrapping

Why:

- this package is not the runtime
- it is the helper layer above the runtime
- keeping it pure JS makes versioning and reuse much simpler

## Versioning model

Recommended model:

1. `@simulatte/webgpu`
2. `@simulatte/webgpu/compute`
3. `@simulatte/webgpu-doe`

should advance in lockstep initially.

Do not optimize for independent version skew yet.

Why:

- the helper layer still evolves with the package surface
- independent versioning too early increases support complexity
- the goal of the first split is architectural clarity, not marketplace
  fragmentation

## Documentation recommendation

After extraction, documentation should say this clearly:

1. `@simulatte/webgpu`
   gives you the raw full surface and also re-exports the Doe helper layer
2. `@simulatte/webgpu/compute`
   gives you the raw compute surface and also re-exports the same Doe helper layer
3. `@simulatte/webgpu-doe`
   is the helper layer itself for advanced users and explicit composition

That is already what the code wants. The packaging should stop hiding it.

## Non-goals

This package split should not:

1. change runtime behavior
2. change the raw full-vs-compute boundary
3. create a second native runtime identity
4. move browser ownership into the Doe helper package
5. turn helper APIs into a separate product promise beyond the current support contract

## Review checklist

Any patch implementing this package split should answer:

1. did `@simulatte/webgpu-doe` gain native/runtime ownership it should not have?
2. does the helper package still work unchanged over both full and compute surfaces?
3. did the extraction preserve `doe.bind(device)` and `doe.requestDevice()` behavior?
4. did the host packages stay small adapters rather than re-forking helper logic?
5. are docs explicit that the Doe package is a JS API layer, not a second runtime?

## Bottom line

`@simulatte/webgpu-doe` is not a speculative package idea.

It is already present in the codebase as a logical layer:

- one shared helper factory
- mounted over two raw surfaces
- documented as a distinct API style

So the real work is not invention.

It is:

1. make the package boundary explicit
2. keep the helper package pure JS
3. preserve the raw full-vs-compute split underneath
4. avoid letting packaging get ahead of the actual architecture
