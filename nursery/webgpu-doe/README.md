# @simulatte/webgpu-doe

Headless WebGPU for Node.js, powered by the
[Doe](https://github.com/clocksmith/fawn) runtime.

## What this is

A native Metal WebGPU implementation for Node.js — no Dawn, no IPC, no
11 MB sidecar. Doe compiles WGSL to MSL at runtime via an AST-based
shader compiler and dispatches directly to Metal via a Zig + ObjC bridge.

This package ships:

- **`libdoe_webgpu`** — Doe native runtime (~2 MB, Zig + Metal)
- **`doe_napi.node`** — N-API addon bridging `libdoe_webgpu` to JavaScript
- **`src/index.js`** — JS wrapper providing WebGPU-shaped classes and constants

## Architecture

```
JavaScript (DoeGPUDevice, DoeGPUBuffer, ...)
    |
  N-API addon (doe_napi.c)
    |
  libdoe_webgpu.dylib  ← Doe native Metal backend, ~2 MB
    |
  Metal.framework       ← GPU execution (Apple Silicon)
```

No Dawn dependency. All GPU calls go directly from Zig to Metal.

## Performance claims (Metal, Apple Silicon)

Apples-to-apples vs Dawn (Chromium's WebGPU), matched workloads and timing:

- **Compute e2e** — 1.5x faster (0.23ms vs 0.35ms, 4096 threads)
- **Buffer upload** — faster across 1 KB to 4 GB (8 sizes claimable)
- **Atomics** — workgroup atomic and non-atomic both claimable
- **Matrix-vector multiply** — 3 variants claimable (naive, swizzle, workgroup-shared)
- **Concurrent execution** — claimable
- **Zero-init workgroup memory** — claimable
- **Draw throughput** — 200k draws claimable
- **Binary size** — ~2 MB vs Dawn's ~11 MB

19 of 30 workloads are claimable. The remaining 11 are bottlenecked by
per-command Metal command buffer creation overhead (~350us vs Dawn's ~30us).
See `fawn/bench/` for methodology and raw data.

## API surface

Compute:

- `create()` / `setupGlobals()` / `requestAdapter()` / `requestDevice()`
- `device.createBuffer()` / `device.createShaderModule()` (WGSL)
- `device.createComputePipeline()` / `device.createBindGroupLayout()`
- `device.createBindGroup()` / `device.createPipelineLayout()`
- `device.createCommandEncoder()` / `encoder.beginComputePass()`
- `pass.setPipeline()` / `pass.setBindGroup()` / `pass.dispatchWorkgroups()`
- `pass.dispatchWorkgroupsIndirect()`
- `pipeline.getBindGroupLayout()`
- `device.createComputePipelineAsync()`
- `encoder.copyBufferToBuffer()` / `queue.submit()` / `queue.writeBuffer()`
- `buffer.mapAsync()` / `buffer.getMappedRange()` / `buffer.unmap()`
- `queue.onSubmittedWorkDone()`

Render:

- `device.createTexture()` / `texture.createView()` / `device.createSampler()`
- `device.createRenderPipeline()` / `encoder.beginRenderPass()`
- `renderPass.setPipeline()` / `renderPass.draw()` / `renderPass.end()`

Device capabilities:

- `device.limits` / `adapter.limits` — full Metal device limits
- `device.features` / `adapter.features` — reports `shader-f16`

Not yet supported: canvas/surface presentation, vertex/index buffer binding
in render passes, full render pipeline descriptor parsing.

## Backend readiness

| Backend | Compute | Render | WGSL compiler | Status |
|---------|---------|--------|---------------|--------|
| **Metal** (macOS) | Production | Basic (no vertex/index) | WGSL -> MSL (AST-based) | Ready |
| **Vulkan** (Linux) | WIP | Not started | WGSL -> SPIR-V needed | Experimental |
| **D3D12** (Windows) | WIP | Not started | WGSL -> HLSL/DXIL needed | Experimental |

**Metal** is the primary backend. All Doppler compute workloads run on Metal today:
bind groups 0-3, buffer map/unmap, indirect dispatch, shader-f16, subgroups,
override constants, workgroup shared memory, multiple entry points.

**Vulkan** and **D3D12** have real native runtime paths (not stubs) with instance
creation, compute dispatch, and buffer upload — but lack shader translation,
bind group management, buffer map/unmap, textures, and render pipelines.

See [`fawn/status.md`](../../status.md) for the full backend implementation matrix.

## Platform support

| Platform | Architecture | Status |
|----------|-------------|--------|
| macOS | arm64 | Prebuilt, tested |
| macOS | x64 | Not yet built |
| Linux | x64 | Not yet built (Vulkan backend experimental) |
| Windows | x64 | Not yet built (D3D12 backend experimental) |

## Install

```sh
npm install @simulatte/webgpu-doe
```

The N-API addon compiles from C source on install via node-gyp. This requires
a C compiler (`xcode-select --install` on macOS).

## Usage

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

### Setup globals (navigator.gpu)

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
