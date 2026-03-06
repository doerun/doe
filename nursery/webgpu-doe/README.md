# @simulatte/webgpu-doe

Headless WebGPU for Node.js on the Doe runtime.

**[Fawn](https://github.com/clocksmith/fawn/tree/main/nursery/webgpu-doe)** · **[npm](https://www.npmjs.com/package/@simulatte/webgpu-doe)** · **[simulatte.world](https://simulatte.world)**

## Install

```sh
npm install @simulatte/webgpu-doe
```

The published package currently targets `darwin-arm64`. The N-API addon builds
from C source during install via `node-gyp`, so a local C toolchain is
required (`xcode-select --install` on macOS).

## Quick start

```js
import { create, globals } from '@simulatte/webgpu-doe';

const gpu = create();
const adapter = await gpu.requestAdapter();
const device = await adapter.requestDevice();

console.log(device.limits.maxComputeWorkgroupSizeX); // 1024
console.log(device.features.has('shader-f16'));       // true

// Standard WebGPU compute workflow
const buffer = device.createBuffer({
  size: 64,
  usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_SRC,
});

const shader = device.createShaderModule({
  code: `
    @group(0) @binding(0) var<storage, read_write> data: array<f32>;
    @compute @workgroup_size(64)
    fn main(@builtin(global_invocation_id) id: vec3u) {
      data[id.x] = data[id.x] * 2.0;
    }
  `,
});

// ... create pipeline, bind group, encode, dispatch, readback
```

The package loads `libdoe_webgpu` and exposes a WebGPU-shaped API for
headless compute and basic render work. See [more examples](#more-examples)
below for `navigator.gpu` setup and provider inspection.

## Why Doe

- Native path: JavaScript calls into an N-API addon, which loads
  `libdoe_webgpu` and submits work through Doe's Metal backend.
- Runtime ownership: WGSL is compiled to MSL inside Doe's AST-based compiler
  instead of going through Dawn.
- Small package payload: the shared library is about 2 MB on `darwin-arm64`.
- WebGPU-shaped surface: `requestAdapter`, `requestDevice`, buffer mapping,
  bind groups, compute pipelines, command encoders, and basic render passes are
  exposed directly from the package.

## Status

Current package target:
- macOS arm64: prebuilt library and tested package path

Backend readiness:

| Backend | Compute | Render | WGSL compiler | Status |
|---------|---------|--------|---------------|--------|
| **Metal** (macOS) | Production | Basic (no vertex/index) | WGSL -> MSL (AST-based) | Ready for package use |
| **Vulkan** (Linux) | WIP | Not started | WGSL -> SPIR-V needed | Experimental |
| **D3D12** (Windows) | WIP | Not started | WGSL -> HLSL/DXIL needed | Experimental |

Metal currently covers the package's intended use: bind groups 0-3, buffer
map/unmap, indirect dispatch, `shader-f16`, subgroups, override constants,
workgroup shared memory, multiple entry points, textures, samplers, and basic
render-pass execution.

Vulkan and D3D12 already have native runtime paths for instance creation,
compute dispatch, and buffer upload, but they still need shader translation,
bind group management, buffer map/unmap, textures, and render pipelines.

Performance snapshot from the Fawn Dawn-vs-Doe harness on Apple Silicon with
strict comparability checks:

- Compute e2e: 1.5x faster (0.23ms vs 0.35ms, 4096 threads)
- Buffer upload: faster across 1 KB to 4 GB (8 sizes claimable)
- Atomics: workgroup atomic and non-atomic both claimable
- Matrix-vector multiply: 3 variants claimable
- Concurrent execution: claimable
- Zero-init workgroup memory: claimable
- Draw throughput: 200k draws claimable
- Binary size: about 2 MB vs Dawn's about 11 MB

19 of 30 workloads are currently claimable. The remaining 11 are limited by
per-command Metal command buffer creation overhead (~350us vs Dawn's ~30us).
See `fawn/bench/` and [`status.md`](../../status.md) for methodology and the
broader backend matrix.

## API surface

Compute:

- `create()` / `setupGlobals()` / `requestAdapter()` / `requestDevice()`
- `device.createBuffer()` / `device.createShaderModule()` (WGSL)
- `device.createComputePipeline()` / `device.createComputePipelineAsync()`
- `device.createBindGroupLayout()` / `device.createBindGroup()`
- `device.createPipelineLayout()` / `pipeline.getBindGroupLayout()`
- `device.createCommandEncoder()` / `encoder.beginComputePass()`
- `pass.setPipeline()` / `pass.setBindGroup()` / `pass.dispatchWorkgroups()`
- `pass.dispatchWorkgroupsIndirect()`
- `encoder.copyBufferToBuffer()` / `queue.submit()` / `queue.writeBuffer()`
- `buffer.mapAsync()` / `buffer.getMappedRange()` / `buffer.unmap()`
- `queue.onSubmittedWorkDone()`

Render:

- `device.createTexture()` / `texture.createView()` / `device.createSampler()`
- `device.createRenderPipeline()` / `encoder.beginRenderPass()`
- `renderPass.setPipeline()` / `renderPass.draw()` / `renderPass.end()`

Device capabilities:

- `device.limits` / `adapter.limits`
- `device.features` / `adapter.features` with `shader-f16`

Current gaps:
- Canvas and surface presentation
- Vertex and index buffer binding in render passes
- Full render pipeline descriptor parsing

## More examples

```js
import { setupGlobals } from '@simulatte/webgpu-doe';

setupGlobals(globalThis);
const adapter = await navigator.gpu.requestAdapter();
```

### Provider info

```js
import { providerInfo } from '@simulatte/webgpu-doe';
console.log(providerInfo());
// { module: '@simulatte/webgpu-doe', loaded: true, doeNative: true, ... }
```

## Configuration

The library search order:

1. `DOE_WEBGPU_LIB` environment variable (full path)
2. `<package>/prebuilds/<platform>-<arch>/libdoe_webgpu.{ext}`
3. `<workspace>/zig/zig-out/lib/libdoe_webgpu.{ext}` (monorepo layout)
4. `<cwd>/zig/zig-out/lib/libdoe_webgpu.{ext}`

## Building from source

Requires [Zig](https://ziglang.org/download/) (0.15+).

```sh
git clone https://github.com/clocksmith/fawn
cd fawn/zig
zig build dropin
# Output: zig-out/lib/libdoe_webgpu.{dylib,so}
```

## License

ISC
