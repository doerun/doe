# @simulatte/webgpu

Headless WebGPU for Node.js and Bun, powered by Doe.

<p align="center">
  <img src="assets/fawn-icon-main-256.png" alt="Fawn logo" width="196" />
</p>

Use this package for compute, CI, benchmarking, and offscreen GPU execution.
It is not a DOM/canvas package and it does not target browser-surface parity.

## Install

```bash
npm install @simulatte/webgpu
```

The install ships platform-specific prebuilds for macOS arm64 (Metal) and
Linux x64 (Vulkan). If no prebuild matches your platform, the installer falls
back to building the native addon with `node-gyp` only; it does not build or
bundle `libwebgpu_doe` and the required Dawn sidecar for you. On unsupported
platforms, use a local Fawn workspace build for those runtime libraries.

## Choose a surface

| Import | Surface | Includes |
| --- | --- | --- |
| `@simulatte/webgpu` | Default full surface | Buffers, compute, textures, samplers, render, Doe helpers |
| `@simulatte/webgpu/compute` | Compute-first surface | Buffers, compute, copy/upload/readback, Doe helpers |
| `@simulatte/webgpu/full` | Explicit full surface | Same contract as the default package surface |

Use `@simulatte/webgpu/compute` when you want the constrained package contract
for AI workloads and other buffer/dispatch-heavy headless execution. The
compute surface intentionally omits render and sampler methods from the JS
facade.

## Quick examples

### Inspect the provider

```js
import { providerInfo } from "@simulatte/webgpu";

console.log(providerInfo());
```

### Request a full device

```js
import { requestDevice } from "@simulatte/webgpu";

const device = await requestDevice();
console.log(device.limits.maxBufferSize);
```

### Request a compute-only device

```js
import { requestDevice } from "@simulatte/webgpu/compute";

const device = await requestDevice();
console.log(typeof device.createComputePipeline); // "function"
console.log(typeof device.createRenderPipeline);  // "undefined"
```

### Run a small compute job with `doe`

```js
import { doe, requestDevice } from "@simulatte/webgpu/compute";

const gpu = doe.bind(await requestDevice());

const input = gpu.createBufferFromData(new Float32Array([1, 2, 3, 4]));

const output = gpu.createBuffer({
  size: input.size,
  usage: "storage-readwrite",
});

await gpu.runCompute({
  code: `
    @group(0) @binding(0) var<storage, read> src: array<f32>;
    @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

    @compute @workgroup_size(4)
    fn main(@builtin(global_invocation_id) gid: vec3u) {
      let i = gid.x;
      dst[i] = src[i] * 2.0;
    }
  `,
  bindings: [input, output],
  workgroups: 1,
});

const result = await gpu.readBuffer(output, Float32Array);
console.log(Array.from(result)); // [2, 4, 6, 8]
```

`doe` is available from both `@simulatte/webgpu` and
`@simulatte/webgpu/compute`. It provides a small ergonomic layer for common
headless tasks: `doe.bind(device)` for device-bound workflows, plus static
buffer creation, readback, one-shot compute dispatch, and
reusable compiled compute kernels.
Binding access is inferred from Doe helper-created buffer usage when possible.
For raw WebGPU buffers or non-bindable/ambiguous usage, pass
`{ buffer, access }` explicitly.

## What this package is

`@simulatte/webgpu` is the canonical package surface for Doe. Node uses an
N-API addon and Bun currently routes through the same addon-backed runtime
entry to load `libwebgpu_doe`. Current builds still ship a Dawn sidecar where
proc resolution requires it.

Doe is a Zig-first WebGPU runtime with explicit profile and quirk binding, a
native WGSL pipeline (`lexer -> parser -> semantic analysis -> IR -> backend
emitters`), and explicit Vulkan/Metal/D3D12 execution paths in one system.
Optional `-Dlean-verified=true` builds use Lean 4 where proved invariants can
be hoisted out of runtime branches instead of being re-checked on every
command; package consumers should not assume that path by default.

## Current scope

- `@simulatte/webgpu` is the default full headless package surface.
- `@simulatte/webgpu/compute` is the compute-first subset for AI workloads.
- Node is the primary supported package surface.
- Bun currently shares the addon-backed runtime entry with Node.
- Package-surface comparisons should be read through the published repository
  benchmark artifacts, not as a replacement for strict backend reports.

<p align="center">
  <img src="assets/package-surface-cube-snapshot.svg" alt="Static package-surface benchmark cube snapshot" width="920" />
</p>

## Verify your install

```bash
npm run smoke
npm test
npm run test:bun
```

`npm run smoke` checks native library loading and a GPU round-trip. `npm test`
covers the Node package contract and a packed-tarball export/import check.

## Caveats

- This is a headless package, not a browser DOM/canvas package.
- `@simulatte/webgpu/compute` is intentionally narrower than the default full
  surface.
- Bun currently shares the addon-backed runtime entry with Node. Package-surface
  contract tests are green, and current comparable macOS package cells are
  claimable. Any FFI-specific claims remain scoped to the experimental Bun FFI
  path until separately revalidated.
- Package-surface benchmark rows are positioning data; backend-native claim
  lanes remain the source of truth for strict Doe-vs-Dawn claims.

## Further reading

- [API contract](./api-contract.md)
- [Support contracts](./support-contracts.md)
- [Compatibility scope](./compat-scope.md)
- [Layering plan](./layering-plan.md)
- [Headless WebGPU comparison](./headless-webgpu-comparison.md)
- [Zig source inventory](./zig-source-inventory.md)
