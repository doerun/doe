# doe-gpu

<p align="center">
  <img src="https://raw.githubusercontent.com/doe-gpu/doe/main/assets/doe-logo.svg" alt="Doe logo" width="96" />
</p>

`doe-gpu` is the npm package for Doe, a Zig-first WebGPU runtime for Node.js,
Bun, and Deno.

It gives you a small JavaScript layer over the native Doe runtime, plus focused
subpaths for compute, browser, and hybrid use cases. The package is built for
people who want a leaner, explicit WebGPU runtime outside the browser.

## Install

```bash
npm install doe-gpu
```

## Why use it

- Small JS layer over the native Doe runtime
- Explicit failure instead of silent fallback
- One package surface across Node.js, Bun, and Deno
- Browser shim available when you want API compatibility rather than runtime
  replacement

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

## Subpaths

- `doe-gpu`: default native-runtime surface
- `doe-gpu/compute`: narrower compute-focused surface
- `doe-gpu/browser`: browser wrapper over the browser's built-in WebGPU runtime
- `doe-gpu/hybrid`: hybrid/local fallback surface

## Runtime requirements

- Node.js 18+ for the default package surface
- a built or preinstalled Doe native library for native runtime use
- Bun and Deno are supported through the package entrypoints in `exports`

If the native addon or shared library is missing, the package fails explicitly
instead of silently falling back to another runtime.

## Important distinction

The default package, `/compute`, and `/hybrid` subpaths are Doe native-runtime
surfaces.

`doe-gpu/browser` is different. It wraps the browser's incumbent WebGPU
implementation so code written against `doe-gpu` can run in a browser, but it
does not mean Doe has replaced the browser runtime.

## Repo-adjacent surfaces

`createDoeRuntime()` and `runDawnVsDoeCompare()` remain available for
repo-adjacent environments that already have Doe runtime or compare assets.

Deeper runtime internals, benchmark workflows, and status live in the repo:

- repo overview:
  [`README.md`](https://github.com/doe-gpu/doe/blob/main/README.md)
- runtime internals:
  [`runtime/zig/README.md`](https://github.com/doe-gpu/doe/blob/main/runtime/zig/README.md)
- benchmarks and evidence:
  [`bench/README.md`](https://github.com/doe-gpu/doe/blob/main/bench/README.md)
- current status:
  [`docs/status.md`](https://github.com/doe-gpu/doe/blob/main/docs/status.md)
- browser integration:
  [`browser/chromium/README.md`](https://github.com/doe-gpu/doe/blob/main/browser/chromium/README.md)

## Legacy package names

These legacy package names are deprecated in favor of `doe-gpu`:

- `@simulatte/webgpu`
- `@simulatte/webgpu-doe`

## License

Apache-2.0. See
[`docs/licensing.md`](https://github.com/doe-gpu/doe/blob/main/docs/licensing.md).
