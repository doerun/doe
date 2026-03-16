# Doe API design

Status: `active`

Scope:

- Doe helper naming and layering above direct WebGPU
- public JSDoc structure for package-surface helper APIs
- future expansion direction for routine families beyond the current helper surface

Use this together with:

- [api-contract.md](./api-contract.md) for current implemented method signatures
- [architecture.md](./architecture.md) for the full runtime layer stack
- [jsdoc-style-guide.md](./jsdoc-style-guide.md) for public API documentation rules

## Why this exists

This document captures the naming cleanup that moved the Doe helper surface to
a more coherent hierarchy:

- `gpu.buffer.*` for resource helpers
- `gpu.kernel.*` for explicit compute primitives
- `gpu.compute.*` for higher-level routines

The remaining job is to keep future additions aligned with that model instead
of drifting back into mixed abstraction buckets.

The design goal is:

1. keep direct WebGPU separate
2. give Doe one explicit primitive layer
3. give Doe one routine layer
4. avoid domain namespaces until they are clearly justified

## Design principles

### 1. Bind once, then stay on the bound object

`doe` itself should only do two things:

- `await doe.requestDevice()`
- `doe.bind(device)`

All helper methods should live on the returned `gpu` object.

This keeps the public model simple:

- `doe` binds
- `gpu` does work

### 2. Namespace by unit of thought, not by implementation accident

Namespaces should represent stable user concepts:

- `buffer`
  resource ownership and readback
- `kernel`
  explicit compiled/dispatchable compute units
- `compute`
  higher-level workflows that allocate, dispatch, and read back for the caller

Avoid namespaces that only reflect where code currently happens to live.

### 3. Do not mix primitives and routines in one namespace

The main current naming problem is that `compute` does two jobs:

- explicit kernel operations
- opinionated one-shot workflows

Those should be separate.

### 4. Delay domain packs until the domain is real

Names like `linalg` or `math` should not exist just because one operation such
as matmul exists.

Introduce a domain namespace only when it has a real family of routines with a
shared mental model and clear boundaries.

Until then, keep those workflows under `gpu.compute.*`.

## Current implemented surface

For exact method signatures and behavior, see
[`api-contract.md`](./api-contract.md) (section `doe`).

The three namespaces are:

- `gpu.buffer.*` — resource helpers (create, read)
- `gpu.kernel.*` — explicit compute primitives (create, run, dispatch)
- `gpu.compute(...)` — one-shot workflow helper

## Proposed routine family (not yet implemented)

- `gpu.compute.map(options) -> Promise<TypedArray>`
- `gpu.compute.zip(options) -> Promise<TypedArray>`
- `gpu.compute.reduce(options) -> Promise<number | TypedArray>`
- `gpu.compute.scan(options) -> Promise<TypedArray>`
- `gpu.compute.matmul(options) -> Promise<TypedArray>`

Domain namespaces like `gpu.linalg` or `gpu.math` should not exist until the
domain has a real family of routines. Keep workflow routines under
`gpu.compute.*` until then.

## Naming rules

### 1. Prefer singular namespaces for domains

Use:

- `gpu.buffer.*`
- `gpu.kernel.*`

Do not use plural buckets like `gpu.buffers.*` unless the package already has a
hard compatibility constraint.

### 2. Keep verbs concrete

Use:

- `create`
- `read`
- `run`
- `dispatch`
- `map`
- `zip`
- `reduce`

Avoid generic names like:

- `execute`
- `process`
- `handle`
- `apply`

unless the contract is genuinely broader than the specific verbs above.

### 3. Keep one namespace, one abstraction level

Examples:

- `gpu.buffer.*`
  resource helpers
- `gpu.kernel.*`
  explicit compute primitives
- `gpu.compute.*`
  routines

Do not mix:

- reusable kernel compilation
- buffer lifecycle
- high-level task workflows

inside one namespace.

## Migration history (completed)

The following renames were applied to reach the current implemented surface:

- `gpu.buffers.create(...)` → `gpu.buffer.create(...)`
- `gpu.buffers.fromData(...)` → merged into `gpu.buffer.create({ data: ... })`
- `gpu.buffers.like(...)` → removed (use `gpu.buffer.create({ size: src.size, ... })`)
- `gpu.buffers.read(...)` → `gpu.buffer.read({ buffer, type, ... })`
- `gpu.compute.run(...)` → `gpu.kernel.run(...)`
- `gpu.compute.compile(...)` → `gpu.kernel.create(...)`
- `kernel.dispatch(...)` → stayed `kernel.dispatch(...)`
- `gpu.compute(...)` → stayed `gpu.compute(...)`

## JSDoc contract for the future helper surface

Public JSDoc should document the API the user actually sees, not the private
helper graph underneath it.

For the Doe helper surface, the preferred structure is:

```js
/**
 * Create a reusable compute kernel from WGSL and binding metadata.
 *
 * Surface: Doe API (`gpu.kernel.*`).
 * Input: WGSL source, entry point, and representative bindings.
 * Returns: A reusable kernel object with `.dispatch(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const kernel = gpu.kernel.create({
 *   code,
 *   bindings: [src, dst],
 * });
 * ```
 *
 * - Reuse this when dispatching the same WGSL shape repeatedly.
 * - Drop to direct WebGPU if you need manual pipeline-layout ownership.
 */
```

Required fields for future Doe helper docs:

1. one-sentence summary
2. `Surface:` line
3. `Input:` line
4. `Returns:` line
5. one small example
6. flat bullets for defaults, failure modes, and escalation path

This is stricter than the current narrative style on purpose. The Doe helper
surface benefits from explicit API contracts more than from prose-heavy
commentary.

## Decision rule for future additions

When adding a new helper:

1. If it is about resource ownership, put it under `gpu.buffer.*`.
2. If it is about explicit WGSL/pipeline reuse and dispatch, put it under
   `gpu.kernel.*`.
3. If it is a workflow that owns temporary allocations and returns typed
   results, put it under `gpu.compute.*`.
4. If it requires model semantics, tensor semantics, KV cache handling,
   attention, routing, or pipeline planning, it does not belong in Doe at all;
   it belongs in a higher-level consumer such as Doppler.

## Non-goals

This design does not propose:

- moving model runtime or pipeline semantics into Doe
- replacing direct WebGPU
- creating a broad domain-pack taxonomy today
- documenting the proposed naming as if it were already the implemented package contract

The live contract remains in [api-contract.md](./api-contract.md) until the
implementation catches up.
