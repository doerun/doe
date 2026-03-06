# @simulatte/webgpu-doe

Headless WebGPU for Node.js, powered by the
[Doe](https://github.com/clocksmith/fawn) runtime.

## What this is

Doe is a Zig WebGPU implementation with native Metal and Vulkan backends. It
implements the standard `wgpu*` C ABI so it can serve as a drop-in replacement
for Dawn or wgpu-native in any application that uses the WebGPU C API.

This package ships:

- **`libdoe_webgpu`** — the Doe drop-in library (Zig, ~2 MB)
- **`libwebgpu_dawn`** — Dawn sidecar for GPU execution (~11 MB)
- **`doe_napi.node`** — N-API addon bridging `libdoe_webgpu` to JavaScript
- **`src/index.js`** — JS wrapper providing WebGPU-shaped classes and constants

## Architecture

```
JavaScript (DoeGPUDevice, DoeGPUBuffer, ...)
    |
  N-API addon (doe_napi.c)
    |
  libdoe_webgpu.dylib  ← Doe drop-in, Zig routing layer
    |
  libwebgpu_dawn.dylib ← GPU execution (Metal on macOS, Vulkan on Linux)
```

### Current state (v0.1.x)

The `wgpu*` C ABI calls are routed through Dawn for GPU execution. Doe provides
the routing layer, symbol ownership policy, and diagnostic instrumentation.

### Roadmap: native Zig backends

Doe has real, working native GPU backends:

| Backend | Platform | Capabilities |
|---------|----------|-------------|
| Metal | macOS | buffer upload, compute dispatch (MSL), render, textures, sync |
| Vulkan | Linux | buffer upload, compute dispatch (SPIR-V), barrier sync, timestamps |
| D3D12 | Windows | buffer upload, sync (compute dispatch in progress) |

These backends make real GPU API calls (Metal framework via ObjC bridge, Vulkan
C ABI, D3D12 COM). They are not simulations.

The `wgpu*` C ABI functions are being implemented natively against these
backends, one function at a time. The Doe routing layer supports per-symbol
ownership, so each function can independently flip from Dawn delegation to
native Zig execution. The Dawn sidecar dependency will shrink as coverage grows
and will eventually be eliminated.

## Platform support

| Platform | Architecture | Status |
|----------|-------------|--------|
| macOS | arm64 | Prebuilt, tested |
| macOS | x64 | Not yet built |
| Linux | x64 | Not yet built |
| Linux | arm64 | Not yet built |
| Windows | x64 | Not yet built |

v0.1.0 ships prebuilt binaries for macOS arm64 only. Other platforms require
building from source (see [Building from source](#building-from-source)).

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

## API surface (v0.1.0)

Headless compute:

- `create()` / `setupGlobals()` / `requestAdapter()` / `requestDevice()`
- `device.createBuffer()` / `device.createShaderModule()` (WGSL)
- `device.createComputePipeline()` / `device.createBindGroupLayout()`
- `device.createBindGroup()` / `device.createPipelineLayout()`
- `device.createCommandEncoder()` / `encoder.beginComputePass()`
- `pass.setPipeline()` / `pass.setBindGroup()` / `pass.dispatchWorkgroups()`
- `encoder.copyBufferToBuffer()` / `queue.submit()` / `queue.writeBuffer()`
- `buffer.mapAsync()` / `buffer.getMappedRange()` / `buffer.unmap()`

Not yet supported: render passes, textures, samplers, canvas presentation.

## Configuration

The library search order:

1. `DOE_WEBGPU_LIB` environment variable (full path)
2. `<package>/prebuilds/<platform>-<arch>/libdoe_webgpu.{ext}`
3. `<workspace>/zig/zig-out/lib/libdoe_webgpu.{ext}` (monorepo layout)
4. `<cwd>/zig/zig-out/lib/libdoe_webgpu.{ext}`

The Dawn sidecar is found automatically when co-located with `libdoe_webgpu`.

## Building from source

Requires [Zig](https://ziglang.org/download/) (0.15+) and a Dawn build.

```sh
git clone https://github.com/clocksmith/fawn
cd fawn/zig
zig build dropin
# Output: zig-out/lib/libdoe_webgpu.{dylib,so}
```

Dawn build instructions: see `fawn/bench/vendor/dawn/`.

## License

ISC
