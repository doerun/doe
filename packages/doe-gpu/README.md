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
