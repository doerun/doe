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
- Faster on modern consumer hardware
- Explicit failure instead of silent fallback
- One package surface across Node.js, Bun, and Deno
- Browser shim available when you want API compatibility rather than runtime
  replacement

## Current evidence

End to end Gemma 3 inference. Positive percentages mean Doe is faster vs Dawn via Node `webgpu` and Bun `bun-webgpu` packages.

![doe-gpu benchmark claims](https://raw.githubusercontent.com/doe-gpu/doe/main/assets/readme/package-claims.svg)

Outputs:
- Node package, AMD Vulkan: [benchmark output](https://github.com/doe-gpu/doe/blob/main/bench/out/amd-vulkan/20260410T235522Z/gemma270m.node-package.ir.compare.json)
- Bun package, AMD Vulkan: [benchmark output](https://github.com/doe-gpu/doe/blob/main/bench/out/amd-vulkan/20260410T235541Z/gemma270m.bun-package.ir.compare.json)
- Node package, Apple Metal: [benchmark output](https://github.com/doe-gpu/doe/blob/main/bench/out/apple-metal/20260414T010826Z/gemma64.node-package.warm.ir.compare.json)
- Bun package, Apple Metal: [benchmark output](https://github.com/doe-gpu/doe/blob/main/bench/out/apple-metal/20260414T010736Z/gemma64.bun-package.warm.ir.compare.json)

## Additional benchmark outputs

ORT lanes and broader follow-up work live in the repo status page. Read
[`docs/status.md`](https://github.com/doe-gpu/doe/blob/main/docs/status.md)
for the current scope and artifacts.

## Usage

```js
import { gpu } from "doe-gpu";

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
- a matching optional platform package or a built/preinstalled Doe native library
- Bun and Deno are supported through the package entrypoints in `exports`

The `doe-gpu` package is the JS front door. Native artifacts are expected to
arrive through one of these paths:

- npm-installed optional platform packages such as `doe-gpu-darwin-arm64`
- a local workspace build under `runtime/zig/zig-out/`
- explicit `DOE_WEBGPU_LIB` / `DOE_LIB` overrides
- local debug prebuilds under `packages/doe-gpu/prebuilds/<platform-arch>/`

If the native addon or shared library is missing, the package fails explicitly
instead of silently falling back to another runtime.

## Publish packaging

Cross-platform npm install support is package-based, not host-magic:

- `doe-gpu` publishes the JS wrapper and declares optional platform packages
- `doe-gpu-<platform>-<arch>` publishes the native `bin/` payload for that host

The platform package bin payload includes:

- `doe_napi.node`
- `libwebgpu_doe.<dylib|so>` or `webgpu_doe.dll`
- `doe-build-metadata.json`
- `metadata.json`

Before publishing a platform package, stage its `bin/` directory from a built
workspace:

```bash
cd packages/doe-gpu-darwin-arm64
npm run stage
```

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
