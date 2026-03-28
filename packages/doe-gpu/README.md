# doe-gpu

<p align="center">
  <img src="https://raw.githubusercontent.com/doe-gpu/doe/main/assets/doe-logo.svg" alt="Doe logo" width="88" />
</p>

Zig-first WebGPU runtime for Node.js, Bun, and Deno.

`doe-gpu` is the npm package surface for Doe. It ships a JavaScript layer over
the Doe native runtime, plus narrower subpath exports for compute-focused and
browser-facing use cases.

## Install

```bash
npm install doe-gpu
```

## Runtime requirements

- Node.js 18+ for the default package surface
- a built or preinstalled Doe native library for native runtime use
- Bun and Deno are supported through the package entrypoints in `exports`

If the native addon or shared library is missing, the package will fail
explicitly rather than silently falling back to another runtime.

## JavaScript layer

The package gives you a small JavaScript layer on top of the native Doe
runtime. It includes:

- WebGPU-style entrypoints such as `requestAdapter()`, `requestDevice()`, and `setupGlobals()`
- the higher-level `gpu` namespace for one-shot compute and helper-oriented workflows
- runtime helpers such as `providerInfo()` and `createDoeRuntime()`

## Usage

```js
import { gpu } from 'doe-gpu';

const device = await gpu.requestDevice();
const result = await device.compute({
  code: `@group(0) @binding(0) var<storage, read_write> data: array<f32>;
         @compute @workgroup_size(64) fn main(@builtin(global_invocation_id) id: vec3u) {
           data[id.x] = data[id.x] * 2.0;
         }`,
  inputs: [new Float32Array([1, 2, 3, 4])],
  output: { type: Float32Array, size: 16 },
  workgroups: 1,
});
```

You can also use the lower-level JS surface directly:

```js
import { requestDevice, providerInfo } from 'doe-gpu';

const info = providerInfo();
const device = await requestDevice();
```

Use `gpu` when you want the higher-level Doe helper namespace. Use
`requestAdapter()` / `requestDevice()` when you want the lower-level
WebGPU-facing surface directly.

## Deterministic greedy selection

The Doe helper namespace now exposes an explicit deterministic greedy-token
selector:

```js
import { gpu } from 'doe-gpu';

const bound = await gpu.requestDevice();
const { token, receipt } = await bound.determinism.stableToken({
  logits: new Float32Array([0, 7, 7, 3]),
});
```

- `stableToken()` applies scalar CPU argmax over `f32` logits.
- the tie-break rule is explicit: `lowest-index-among-max`
- the helper accepts either host logits bytes or a GPU buffer
- every call returns a receipt with the selected token, the max-tie set, the
  top candidates, the logits SHA-256 digest, and proof links for the
  policy-layer tie-break contract

## Deterministic ambiguity resolution

Doe also exposes a separate bounded-choice helper for ambiguous answer sets:

```js
import { gpu } from 'doe-gpu';

const bound = await gpu.requestDevice();
const { token, receipt } = await bound.determinism.stableChoice({
  logits: new Float32Array([0, 9.0, 8.97, 3.0]),
  candidates: [
    { token: 2, label: 'unsafe' },
    { token: 1, label: 'safe' },
  ],
  ambiguityTrigger: { mode: 'candidate-margin-band', epsilon: 0.05 },
  policyId: 'demo/fixed-priority-unsafe-first',
  triggerPolicyId: 'candidate-margin-band-v1',
  candidateSetId: 'safety.safe_unsafe',
  candidateSetSource: 'fixture-declared',
});
```

- `stableChoice()` is not the same claim as `stableToken()`
- it starts from the same scalar `stable-token` boundary, then evaluates a
  bounded candidate set for ambiguity
- current trigger modes:
  - `exact-max-tie`
  - `candidate-margin-band`
- current evaluator:
  - `fixed-priority` using the candidate array order
- if the ambiguity trigger does not fire, the helper falls back to the scalar
  `stable-token` result
- every call returns a receipt with:
  - logits digest
  - candidate-set logits
  - ambiguity trigger config and whether it fired
  - the policy ID / evaluator kind
  - the trigger policy ID, candidate-set ID, and candidate-set provenance
  - the final chosen token and whether it came from policy or fallback
  - proof links for the stable-token base rule, trigger contract, and
    fixed-priority evaluator semantics

## Reviewed ambiguity resolution

Doe also exposes a separate reviewed-choice helper when you want the ambiguity
resolution path to be explicit and auditable instead of purely programmatic:

```js
import { gpu } from 'doe-gpu';

const bound = await gpu.requestDevice();
const { token, receipt } = await bound.determinism.reviewedChoice({
  logits: new Float32Array([0, 7, 7, 3]),
  candidates: [
    { token: 2, label: 'unsafe' },
    { token: 1, label: 'safe' },
  ],
  ambiguityTrigger: { mode: 'exact-max-tie' },
  reviewPolicyId: 'demo/reviewer-v1',
  triggerPolicyId: 'exact-max-tie-v1',
  candidateSetId: 'safety.safe_unsafe',
  candidateSetSource: 'fixture-declared',
  decision: {
    token: 1,
    label: 'safe',
    reviewerId: 'demo/reviewer-v1',
    decisionId: 'demo-review-001',
  },
});
```

- `reviewedChoice()` is a sibling of `stableToken()` and `stableChoice()`, not
  an alias for either one
- it uses the same bounded candidate-set and ambiguity-trigger contract as
  `stableChoice()`
- the evaluator is an explicit reviewed decision receipt, not the built-in
  fixed-priority program
- if the ambiguity trigger does not fire, or the reviewed token is outside the
  ambiguous bounded set, the helper falls back to the scalar `stable-token`
  result
- every call returns a receipt with:
  - logits digest
  - bounded candidate-set logits
  - ambiguity trigger config and whether it fired
  - reviewed decision provenance (`reviewerId`, optional decision IDs/refs)
  - whether the reviewed decision was accepted or why it fell back
  - proof links for the stable-token base rule, trigger contract, and
    reviewed-decision evaluator semantics

## Subpath exports

```js
import { gpu } from 'doe-gpu';           // full (default)
import { gpu } from 'doe-gpu/compute';   // compute-only surface
import { gpu } from 'doe-gpu/browser';   // browser shim
```

- `doe-gpu`: full default surface for Node.js, Bun, and Deno
- `doe-gpu/compute`: narrower compute-focused surface with runtime utilities
- `doe-gpu/browser`: browser-facing shim around native browser WebGPU objects

The browser subpath is a browser-oriented JS shim. The default package and
`/compute` subpath are the native-runtime package surfaces.

## Advanced helpers

`createDoeRuntime()` and `runDawnVsDoeCompare()` remain available for
repo-adjacent environments that already have Doe runtime or compare assets
available.

They are not npm CLI tools. Canonical compare, release, and gate workflows live
in the repo under `bench/`.

## Migration from @simulatte/webgpu

```diff
- import { doe } from '@simulatte/webgpu';
+ import { gpu } from 'doe-gpu';

- const device = await doe.requestDevice();
+ const device = await gpu.requestDevice();
```

`createDoeNamespace` is still available; `createGpuNamespace` is the new alias:

```js
import { createGpuNamespace } from 'doe-gpu';
```

The same alias is available from the subpath exports:

```js
import { createGpuNamespace } from 'doe-gpu/compute';
import { createGpuNamespace as createBrowserGpuNamespace } from 'doe-gpu/browser';
```

## Read more

- Repo overview: [`README.md`](../../README.md)
- Runtime internals: [`runtime/zig/README.md`](../../runtime/zig/README.md)
- Internal operator tooling: [`docs/internal-tooling.md`](../../docs/internal-tooling.md)
- Browser integration: [`browser/chromium/README.md`](../../browser/chromium/README.md)
- Licensing: [`docs/licensing.md`](../../docs/licensing.md)

## License

Apache-2.0. See [`docs/licensing.md`](../../docs/licensing.md).
