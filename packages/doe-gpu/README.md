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

ONNX Runtime (ORT) lanes and broader follow-up work live in the repo status page. Read
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
- `doe-gpu/api`: provider-neutral JS API helpers and types
- `doe-gpu/native`: explicit Zig-backed native WebGPU provider
- `doe-gpu/plan`: JSON command-stream, capture-graph, and execution-plan contracts
- `doe-gpu/capture`: alias for the record-only WebGPU capture provider
- `doe-gpu/compute`: narrower compute-focused surface
- `doe-gpu/browser`: browser wrapper over the browser's built-in WebGPU runtime
- `doe-gpu/hybrid`: legacy integration helper for local/cloud fallback

## Runtime requirements

- Node.js 18+ for the default package surface
- a matching optional platform package or a built/preinstalled Doe native library
- Bun and Deno are supported through the package entrypoints in `exports`

The `doe-gpu` package is the JS front door. Native artifacts are expected to
arrive through one of these paths:

- npm-installed optional platform packages such as `doe-gpu-darwin-arm64`
  and `doe-gpu-linux-x64`
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

Release order matters:

1. Build the native artifacts on the target host for each platform package.
2. Bump `doe-gpu-<platform>-<arch>` to the release version it will publish.
3. Run `npm run stage` in that platform package.
4. Verify `packages/doe-gpu` with `npm run test:smoke`,
   `npm run test:integration`, and `npm pack --dry-run`.
5. Publish the platform package versions first. On Apple, publish
   `doe-gpu-darwin-arm64` only after Linux is already published.
6. Publish `doe-gpu` only after every platform package version referenced in
   its `optionalDependencies` is already live on npm.

## Important distinctions

The default package and `/compute` remain batteries-included Doe native-runtime
surfaces. `/native` is the explicit subpath for consumers that want to bind to
the Zig-backed WebGPU provider directly.

`doe-gpu/browser` is different. It wraps the browser's incumbent WebGPU
implementation so code written against `doe-gpu` can run in a browser, but it
does not mean Doe has replaced the browser runtime.

`doe-gpu/api`, `doe-gpu/plan`, and `doe-gpu/capture` do not load native addons
or platform packages. They expose provider-neutral helpers, JSON shape checks,
WebGPU enum globals, and a record-only WebGPU provider that captures supported
compute calls into a Doe execution graph.

The portable capture boundary is WebGPU behavior, not arbitrary JavaScript
source translation. Host code may use normal JavaScript, but the observable GPU
work must flow through the supported provider subset:
`requestAdapter`, `requestDevice`, buffer creation/writes, WGSL shader module
creation, bind group and compute pipeline creation, command encoding,
compute dispatch, buffer copies, queue submission, and selected readback
checkpoints. Unsupported CSL features such as render passes, textures,
samplers, atomics, and generic subgroup behavior fail explicitly in capture
mode.

`doe-gpu/hybrid` is kept for compatibility, but product model loading,
tokenizers, generation, and local/cloud routing should live above Doe. New
Doppler integrations should prefer an explicit Doppler provider over treating
`/hybrid` as a core Doe runtime layer.

There is intentionally no public `doe-gpu/csl` subpath yet. CSL and SdkLayout
lowering stays private until the HostPlan and receipt boundary is stable enough
to publish without overpromising. The public boundary today is the captured
WebGPU graph plus plan/receipt contracts. Public demos should bind the Doppler
runner, capture graph hash, WGSL hashes, lowering stage status, and parity
verdict through `doe_webgpu_capture_evidence` receipts.

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
