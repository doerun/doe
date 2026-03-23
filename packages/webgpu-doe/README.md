# @simulatte/webgpu-doe

> **Deprecated:** This package is deprecated and has been merged into [`doe-gpu`](https://github.com/doe-gpu/doe).

The standalone Doe JavaScript helper layer for WebGPU-compatible runtimes.

This package does not ship a runtime, native addon, or raw WebGPU
implementation. It gives you the Doe helper API so you can mount it onto
`@simulatte/webgpu` or another compatible device/runtime.

If you want the runtime included, use
[`@simulatte/webgpu`](../webgpu/README.md).

## Quick start

```bash
npm install @simulatte/webgpu-doe @simulatte/webgpu
```

Mount Doe onto the compute runtime:

```js
import { requestDevice } from "@simulatte/webgpu/compute";
import { createDoeNamespace } from "@simulatte/webgpu-doe";

const doe = createDoeNamespace({ requestDevice });
const gpu = await doe.requestDevice();

const result = await gpu.compute({
  code: `
    @group(0) @binding(0) var<storage, read> src: array<f32>;
    @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

    @compute @workgroup_size(4)
    fn main(@builtin(global_invocation_id) gid: vec3u) {
      let i = gid.x;
      dst[i] = src[i] * 2.0;
    }
  `,
  inputs: [new Float32Array([1, 2, 3, 4])],
  output: { type: Float32Array },
  workgroups: 1,
});

console.log(JSON.stringify(Array.from(result)));
```

Bind Doe to an existing device:

```js
import { requestDevice } from "@simulatte/webgpu";
import doe from "@simulatte/webgpu-doe";

const device = await requestDevice();
const gpu = doe.bind(device);
```

The same one-shot flow is available in
[`examples/with-webgpu-one-shot.js`](examples/with-webgpu-one-shot.js).

## What it gives you

- `createDoeNamespace({ requestDevice })`
- the default `doe` namespace
- `doe.bind(device)` when you already own a compatible device
- `gpu.buffer.*`, `gpu.kernel.*`, `gpu.compute(...)`, and
  `gpu.commandEncoder.create(...)`

If you create a namespace without `requestDevice`, `doe.requestDevice()` throws
and `doe.bind(device)` remains available.

## When to use it

- you want the Doe helper API as a separate package boundary
- you already have device creation handled elsewhere
- you want Doe helpers without taking a dependency on the full runtime package
  surface

## What it does not do

- discover or load a runtime on its own
- provide raw WebGPU globals or wrapper classes
- ship a native transport layer

## Documentation

- [`examples/README.md`](examples/README.md)
- [`examples/with-webgpu-one-shot.js`](examples/with-webgpu-one-shot.js)
- [`examples/with-webgpu-compute.js`](examples/with-webgpu-compute.js)
- [`examples/with-webgpu-command-encoder.js`](examples/with-webgpu-command-encoder.js)
- [`../webgpu/README.md`](../webgpu/README.md)
- [`../../README.md`](../../README.md)

## License

Apache-2.0
