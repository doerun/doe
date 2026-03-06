# @simulatte/webgpu-doe

Native WebGPU runtime for Node.js via the Doe drop-in library.

Doe (`libdoe_webgpu`) is a Zig-built WebGPU routing layer that provides the
standard `wgpu*` C ABI. This package wraps it as a Node.js N-API addon, giving
JavaScript code a WebGPU compute surface without depending on browser runtimes.

## Status

**v0.1.0 — bring your own libs.** This release ships the N-API binding source
and JS wrapper. You must build `libdoe_webgpu` yourself and point the package
to it. Prebuilt binaries are planned for a future release.

## Requirements

- Node.js >= 18
- A C compiler (node-gyp builds the N-API addon on `npm install`)
- `libdoe_webgpu` shared library (`.dylib` / `.so` / `.dll`)
- Dawn sidecar library (`libwebgpu_dawn`) — loaded by `libdoe_webgpu` at runtime

## Building libdoe_webgpu

From the [fawn](https://github.com/clocksmith/fawn) repository:

```sh
cd fawn/zig
zig build dropin
# produces zig-out/lib/libdoe_webgpu.{dylib,so}
```

The Dawn sidecar must also be built or obtained separately. See
`fawn/bench/vendor/dawn/` for build instructions.

## Install

```sh
npm install @simulatte/webgpu-doe
```

node-gyp compiles the N-API addon automatically. If the build fails, ensure you
have a working C toolchain (`xcode-select --install` on macOS, `build-essential`
on Debian/Ubuntu).

## Configuration

The package searches for `libdoe_webgpu` in these locations (first match wins):

1. `DOE_WEBGPU_LIB` environment variable (full path to the shared library)
2. `<package>/prebuilds/<platform>-<arch>/libdoe_webgpu.{ext}` (future prebuilds)
3. `<workspace>/zig/zig-out/lib/libdoe_webgpu.{ext}` (monorepo dev layout)
4. `<cwd>/zig/zig-out/lib/libdoe_webgpu.{ext}`

Dawn's sidecar library must be discoverable at runtime. On macOS/Linux, set
`DYLD_LIBRARY_PATH` or `LD_LIBRARY_PATH` to include the directory containing
`libwebgpu_dawn.dylib` / `libwebgpu_dawn.so`.

```sh
export DOE_WEBGPU_LIB=/path/to/libdoe_webgpu.dylib
export DYLD_LIBRARY_PATH=/path/to/dawn/out/Release
node your-app.js
```

## Usage

### Direct API

```js
import { create, globals } from '@simulatte/webgpu-doe';

const gpu = create();
const adapter = await gpu.requestAdapter();
const device = await adapter.requestDevice();

const buffer = device.createBuffer({
  size: 64,
  usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_SRC,
});
```

### Setup globals (navigator.gpu)

```js
import { setupGlobals } from '@simulatte/webgpu-doe';

setupGlobals(globalThis);

const adapter = await navigator.gpu.requestAdapter();
const device = await adapter.requestDevice();
```

### Convenience helpers

```js
import { requestAdapter, requestDevice } from '@simulatte/webgpu-doe';

const adapter = await requestAdapter();
const device = await requestDevice();
```

## Supported surface

v0.1.0 covers the headless compute surface:

- Instance creation, adapter/device request
- Buffer create, map, unmap, destroy
- Shader module creation (WGSL)
- Compute pipeline, bind group layout, bind group, pipeline layout
- Command encoder, compute pass (setPipeline, setBindGroup, dispatch, end)
- Buffer-to-buffer copy
- Queue submit, queue writeBuffer

Render passes, textures, and canvas presentation are not yet supported.

## License

ISC
