# API design and JSDoc style guide

This guide defines the public JavaScript API design rules and the required
JSDoc format for `nursery/webgpu`.

It is the source of truth for:

- public package API shape
- API style naming
- public runtime object boundaries
- JSDoc structure and tone

This guide is intentionally opinionated. Public API docs should read more like
Flutter SDK API docs than like internal code comments: lead with the concrete
behavior, explain how the API fits the surface, show a small real example, and
call out the important boundaries.

Primary references:

- [AnimatedContainer class - Flutter API](https://api.flutter.dev/flutter/widgets/AnimatedContainer-class.html)
- [FutureBuilder class - Flutter API](https://api.flutter.dev/flutter/widgets/FutureBuilder-class.html)
- [Effective Dart: Documentation](https://dart.dev/effective-dart/documentation)

Related design references:

- [doe-api-design.md](./doe-api-design.md)
- [api-contract.md](./api-contract.md)

## Scope

This guide applies to:

- exported functions and constants in `src/*.js`
- exported namespaces such as `doe`
- public classes and public methods returned by package entrypoints
- public methods exposed through exported objects and facades

This guide does not apply to:

- private helper functions
- internal implementation-only transforms
- internal wrapper utilities that are not part of the public surface

## API design rules

### 1. Follow the package and API style model

The package split, export surfaces, API styles (`Direct WebGPU` vs `Doe API`),
and helper taxonomy (`gpu.buffer.*`, `gpu.kernel.*`, `gpu.compute(...)`) are
defined in:

- [`./api-contract.md`](./api-contract.md) — current implemented contract
- [`./doe-api-design.md`](./doe-api-design.md) — target naming and design
  principles
- [`./architecture.md`](./architecture.md) — full layer stack

Do not add new public helper namespaces unless they represent a stable,
user-visible abstraction layer. One-shot helpers like `gpu.compute(...)` should
stay narrower than the explicit primitive parts of `Doe API`.

### 2. Prefer explicit resource ownership


`Doe API` may reduce boilerplate, but it should still make resource ownership
and execution shape understandable.

Good:

- `gpu.buffer.create({ size: src.size, usage: "storageReadWrite" })`
- `gpu.kernel.run({ code, bindings, workgroups })`

Risky:

- giant option bags that hide allocations, binding rules, and reuse behavior
- convenience APIs that make it hard to tell when buffers are created or destroyed

### 3. Keep JS naming coherent

For JavaScript APIs:

- functions and methods use `camelCase`
- public token strings use JS-friendly casing
- avoid snake_case names on the public surface

For example:

- `storageRead`
- `storageReadWrite`
- `createBufferLike`
- `requestDevice`

### 4. Prefer singular helper namespaces

When a namespace represents one object domain, prefer the singular form:

- `gpu.buffer.*`
- `gpu.kernel.*`

Treat plural namespaces in the current API as compatibility debt rather than
the naming target for future design work.

### 5. Fail clearly on unsupported states

Unsupported or out-of-scope behavior should fail explicitly with actionable
messages. Public docs should state those boundaries when they are easy to miss.

Examples:

- compute facade intentionally omits render and surface APIs
- `compute(...)` rejects raw numeric usage flags
- bare buffers without Doe metadata require `{ buffer, access }`

## Public documentation rules

### 1. Put public docs on the `.js` implementation

The `.js` file is the source of truth for public behavior. The `.d.ts` files
carry type shape, but the primary API docs live on the implementation.

### 2. Document every public function, class, method, and namespace

That includes:

- exported functions and constants
- exported namespaces
- public runtime classes returned by package entrypoints
- public methods on returned objects and facades

If users can call it directly, it needs JSDoc.

### 3. Do not document private helpers

Do not add JSDoc to:

- private helper functions
- internal normalization helpers
- private wrapper utilities that are not part of the public contract

Public API comments should not be diluted by internal commentary.

### 4. Do not use `//` doc comments in public API files

Public API explanation belongs in JSDoc. Do not add one-line `//` comments
above public functions, classes, or methods when the JSDoc should carry that
meaning instead.

## Required JSDoc structure

Use this order for public APIs:

```js
/**
 * One-sentence summary in plain English.
 *
 * Surface: package layer or namespace.
 * Input: short plain-English summary of the main inputs.
 * Returns: short plain-English summary of the main result.
 *
 * Short prose paragraph explaining what the API does, how it behaves, and
 * why a caller would use it.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * // minimal real usage
 * ```
 *
 * - important defaults
 * - failure modes
 * - scope boundaries
 */
```

Do not add narrative section labels like:

- `What this does:`
- `Example:`
- `Edge cases:`

For future Doe helper docs, the following short contract lines are required:

- `Surface:`
- `Input:`
- `Returns:`

These are machine-scannable anchors, not prose section headings.

## JSDoc content rules

### Summary line

The first line must be a single sentence that states the concrete action.

Prefer verbs:

- `Create`
- `Request`
- `Read`
- `Run`
- `Compile`
- `Report`
- `Install`
- `Release`
- `Return`

Good:

- `Request a Doe-backed adapter from the full package surface.`
- `Create a compute-only GPU facade backed by the Doe runtime.`
- `Read a buffer back into a typed array.`

Bad:

- `Helper for compute.`
- `Convenience method.`
- `Used for device workflows.`

### Contract lines

Immediately after the summary line, add:

- `Surface:`
- `Input:`
- `Returns:`

Keep them short and concrete.

Good:

- `Surface: Doe API (\`gpu.kernel.*\`).`
- `Input: WGSL source, entry point, and representative bindings.`
- `Returns: A reusable kernel object with \`.dispatch(...)\`.`

Bad:

- `Surface: API`
- `Input: options`
- repeating full type declarations from `.d.ts`

### Prose paragraph before the example

After the summary line, include a short prose paragraph explaining:

- what happens
- what is returned, allocated, installed, wrapped, or destroyed
- how it fits the package surface or layer model when relevant

This paragraph should usually be 1-3 short sentences.

Good:

- explain whether the API allocates buffers, submits work, waits, or reads back
- explain whether an object is full-surface or compute-only
- explain whether the API belongs to `Direct WebGPU` or `Doe API`, and whether it is an explicit primitive or a more opinionated one-shot helper when that matters

Do not:

- restate the function name in slightly different words
- narrate private helper calls
- paste type information as prose

### Example lead-in sentence

Immediately above every example block, add one short sentence explaining what
the example demonstrates.

Current default pattern:

- `This example shows the API in its basic form.`

If a more specific sentence is better, use it.

Good alternatives:

- `This example shows the common upload-then-dispatch flow.`
- `This example shows how to reuse a compiled kernel.`
- `This example shows the unbound helper form with an explicit device.`

### Example block

Every public API needs a real usage example.

Requirements:

- use runnable or near-runnable code
- keep it minimal
- use actual package exports and actual method names
- show the most likely usage first

Do:

- use `await doe.requestDevice()` for the direct Doe API entry path
- use `gpu.buffer.create({ size: src.size, ... })` when showing size-copy allocation
- use `gpu.compute(...)` only for true one-shot Doe API examples

Do not:

- use pseudocode
- use fake imports
- add unrelated setup unless the API requires it

### Bullet notes after the example

After the example, use short bullets for the important constraints:

- defaults
- accepted shorthand forms
- throws or explicit failure behavior
- package-surface differences
- cases where the caller should drop to a lower API style

These bullets are where edge cases live, even though the doc does not label
them as an `Edge cases:` section.

## What to document by surface

### Package entrypoints

For `create`, `setupGlobals`, `requestAdapter`, `requestDevice`,
`providerInfo`, `createDoeRuntime`, and `runDawnVsDoeCompare`:

- explain what object they return
- explain whether they create, install, request, or report
- explain whether they are in-process runtime APIs or tooling APIs
- call out failure behavior when relevant

### Runtime classes and facade objects

For objects like `GPU`, adapter, device, queue, buffer, command encoder,
render pass encoder, compute pass encoder, and the compute-only wrapper
objects:

- explain what the object represents
- explain where callers obtain it
- explain what subset of the full surface it owns

For their public methods:

- explain what operation happens
- explain whether it records, allocates, submits, waits, maps, or destroys
- explain wrapper behavior when a compute facade forwards into the full surface

### Doe namespaces

For `doe` and nested namespaces:

- explain the API style split
- explain when to use `requestDevice()` versus `bind(device)`
- explain bound versus unbound Doe forms
- explain where a more opinionated one-shot Doe API helper is intentionally narrower than the rest of `Doe API`

## Style rules

1. Write in present tense.
2. Prefer short paragraphs and flat bullets.
3. Use concrete nouns: `GPU`, adapter, device, buffer, pipeline, typed array.
4. Explain observable behavior, not internal implementation trivia.
5. Keep examples in ASCII.
6. Keep examples aligned with the actual shipped API.
7. Keep docs package-accurate:
   `@simulatte/webgpu` is headless full surface;
   `@simulatte/webgpu/compute` is compute-only;
   browser ownership belongs to `nursery/fawn-browser`.

## Anti-patterns

Do not write docs like this:

```js
/**
 * Helper for compute.
 */
```

```js
/**
 * Binds a device.
 */
```

```js
/**
 * Run compute.
 *
 * ```js
 * // omitted
 * ```
 */
```

These fail because they omit behavior, layering, concrete usage, or the
important constraints.

## Good pattern

```js
/**
 * Run a narrow typed-array routine.
 *
 * This accepts typed-array or Doe input specs, allocates temporary buffers,
 * dispatches the compute job once, reads the output back, and returns the
 * requested typed array result.
 *
 * This example shows a basic one-shot Doe API path with a typed-array input.
 *
 * ```js
 * const out = await gpu.compute({
 *   code: WGSL,
 *   inputs: [new Float32Array([1, 2, 3, 4])],
 *   output: { type: Float32Array },
 *   workgroups: [4, 1],
 * });
 * ```
 *
 * - This is intentionally opinionated: it rejects raw numeric WebGPU usage
 *   flags and expects Doe usage tokens when usage is specified.
 * - Output size defaults from `likeInput` or the first input when possible;
 *   if no size can be derived, it throws instead of guessing.
 * - Temporary buffers created internally are destroyed before the call returns.
 */
```

## Review checklist

Before merging a public API doc change, verify:

- the summary line states the concrete action
- the prose paragraph explains what happens and what is returned or changed
- there is a one-sentence example lead-in immediately above the example
- the example uses the real package API
- the bullets cover defaults, throws, and boundary conditions
- the docs reflect the current full-vs-compute split
- the docs reflect the current `Direct WebGPU` / `Doe API` model
- no private helpers were documented
- no `//` doc comments were added
