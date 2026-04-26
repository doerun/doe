# Doe Node WebGPU runtime scope

This note scopes the Doe-side Node WebGPU bootstrap used by Cerebras evidence
tooling. It is a narrow package surface for repo-adjacent receipts, not a
Doppler runtime port.

## Goal

Doe should provide its own Node WebGPU bootstrap surface for evidence tools that
need to compile or dispatch WGSL locally. The surface exists to make Doe receipts
self-contained:

- `bench/tools/run_doe_webgpu_kernel_dispatch.mjs` should not import the bare
  `webgpu` package directly.
- `bench/tools/run_doe_webgpu_program_bundle_inference.mjs` should not import
  `../doppler/src/tooling/node-webgpu.js`.
- `capture_doppler_gemma4_webgpu_graph.mjs` may keep using Doppler as the
  source runner, but the provider it installs should come from Doe once the Doe
  bootstrap exists.

The claim boundary stays narrow: this is a Node WebGPU provider bootstrap for
Doe-side local parity receipts. It is not a Doppler inference runtime.

## Current state

Doppler owns the production inference product: model loading, Program Bundle
export, tokenizer behavior, generation loop, KV cache policy, sampling, and
reference transcripts. Doe owns the runtime/compiler/evidence side: provider
surfaces, capture graphs, TSIR lowering, HostPlan/CSL, and receipt validation.

The Doe-owned bootstrap now lives at `doe-gpu/node-webgpu`. It resolves a
provider module, installs `globalThis.navigator.gpu`, installs WebGPU enum
globals, probes adapter creation, and returns a structured bootstrap result
under Doe naming and Doe failure taxonomy.

## Doe API surface

Preferred first surface, kept repo-adjacent until the contract hardens:

```js
import {
  bootstrapNodeWebGPU,
  bootstrapNodeWebGPUProvider,
} from "doe-gpu/node-webgpu";
```

Minimum contract:

- `bootstrapNodeWebGPU()` installs a usable `globalThis.navigator.gpu` if one is
  not already present, then probes adapter creation.
- `bootstrapNodeWebGPUProvider(specifier, options)` installs a specific provider
  and fails with an actionable error if import, global installation, or adapter
  probing fails.
- Both return `{ ok, provider, detail }` style data rather than silently falling
  back.
- The module installs WebGPU enum globals needed by WGSL dispatch helpers:
  `GPUBufferUsage`, `GPUShaderStage`, `GPUMapMode`, and `GPUTextureUsage`.
- Environment override should use a Doe-owned name, e.g.
  `DOE_NODE_WEBGPU_MODULE`; Doppler's `DOPPLER_NODE_WEBGPU_MODULE` remains
  Doppler-side compatibility only.

Implementation location:

- `packages/doe-gpu/src/node-webgpu.js`
- `packages/doe-gpu/src/node-webgpu.d.ts`
- package export: `"./node-webgpu": "./src/node-webgpu.js"`

## Provider resolution

The Doe bootstrap should accept the same provider shapes Doppler already has to
handle:

- module exports `gpu` or `webgpu`
- default export with `gpu` or `webgpu`
- factory exports such as `create()` or `createInstance()`
- preinstalled `globalThis.navigator.gpu`

Provider resolution must be explicit and auditable:

- no silent browser fallback
- no hidden network fetches
- no DOM dependency
- no mutation beyond WebGPU globals and `navigator.gpu`
- no provider success unless adapter probing succeeds

## Program Bundle host boundary

Porting Node WebGPU bootstrap does not mean porting Doppler's Program Bundle
host evaluator.

The Program Bundle host contract remains Doppler-authored:

- raw WGSL kernels
- constrained host JavaScript
- model/tokenizer/weight identity
- reference transcript generation

If Doe later evaluates `host_entrypoint` directly, that evaluator needs a
separate contract:

- file-backed Program Bundle inputs only
- no DOM
- no dynamic import from bundle code
- no network access
- no ambient model discovery
- explicit failure for unsupported host operations

Until that evaluator exists, Doe's WebGPU evidence can honestly claim provider
bootstrap, shader compile/pipeline status, capture-graph identity, and
per-kernel dispatch receipts. Token-loop parity remains Doppler-runner evidence
or a future Doe evaluator receipt.

## What stays Doppler-side

Do not move these into Doe for this scope:

- model catalog and model loading policy
- tokenizer behavior and chat templates
- generation loop and stopping policy
- sampling semantics
- KV cache ownership in the product runtime
- Program Bundle export
- per-kernel Doppler transcript materialization
- OpenAI-compatible API or command surface

The Doe-side consumer is the transcript, not the product runtime.

## What changes in Doe tools

- `bench/tools/run_doe_webgpu_kernel_dispatch.mjs` imports
  `doe-gpu/node-webgpu` instead of `webgpu`.
- `bench/tools/run_doe_webgpu_program_bundle_inference.mjs` imports
  `doe-gpu/node-webgpu` instead of Doppler's `src/tooling/node-webgpu.js`.
- `bench/tools/capture_doppler_gemma4_webgpu_graph.mjs` installs Doe's capture
  provider through `doe-gpu/node-webgpu`.
- `bench/tools/doe_parity.py` can treat "Node WebGPU module unavailable" as a
  Doe dependency/configuration blocker rather than a Doppler dependency.

## Validation

The scope is complete when Doe can produce these artifacts without importing
Doppler's Node WebGPU helper:

- WebGPU kernel dispatch receipt for a TSIR bootstrap kernel.
- Doe-WebGPU Program Bundle compile/pipeline transcript with a provider source
  field naming Doe.
- Capture-graph receipt whose provider source is Doe and whose Program Bundle
  identity still comes from Doppler.

Token sequence, logits digest, and KV digest parity are deliberately outside
this scope until a Doe Program Bundle host evaluator exists.
