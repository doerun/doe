# @simulatte/webgpu-doe

<table>
  <tr>
    <td valign="middle">
      <strong>Use the Doe JavaScript helper API with @simulatte/webgpu or another compatible WebGPU runtime.</strong>
    </td>
    <td valign="middle">
      <img src="assets/fawn-icon-main.svg" alt="Fawn logo" width="88" />
    </td>
  </tr>
</table>

`@simulatte/webgpu-doe` is the standalone JavaScript Doe helper package.

It does **not** ship a runtime, native addon, Bun FFI layer, or raw WebGPU
implementation. It ships the Doe API only:

- `createDoeNamespace(...)`
- `doe`
- `default`

Use it when:

- you want the Doe API as a separate JavaScript package
- you already have a compatible WebGPU device
- you want to mount Doe onto `@simulatte/webgpu` or another runtime

## What this package includes

- Doe buffer helpers: `gpu.buffer.create(...)`, `gpu.buffer.read(...)`
- Doe kernel helpers: `gpu.kernel.run(...)`, `gpu.kernel.create(...)`,
  `kernel.dispatch(...)`, `kernel.bindings.create(...)`, `kernel.encode(...)`
- Doe batched compute helpers: `gpu.compute(...)`, `gpu.compute.begin(...)`
- Doe explicit encoder helpers: `gpu.commandEncoder.create(...)`
- Generic TypeScript types for the bound Doe namespace and helper options

## What this package does not include

- no runtime or device discovery on its own
- no Node addon or Bun FFI transport
- no raw WebGPU wrapper classes
- no feature publication, limits, or globals

You either:

1. inject a `requestDevice(...)` function from another package, or
2. bind Doe to an already-created compatible device with `doe.bind(device)`

## Install

Pair it with a compatible runtime package, usually `@simulatte/webgpu`:

```bash
npm install @simulatte/webgpu-doe @simulatte/webgpu
```

## How the packages fit together

- `@simulatte/webgpu`
  - the runtime package
  - headless WebGPU for Node.js and Bun
  - includes the same Doe API
- `@simulatte/webgpu/compute`
  - narrower compute-first runtime entrypoint
- `@simulatte/webgpu-doe`
  - helper-only JavaScript package
  - no runtime transport

If you just want headless WebGPU, use `@simulatte/webgpu`. If you specifically
want the helper API as a separate package, use `@simulatte/webgpu-doe`.

## Start here

The same simple compute pass, shown first as the helper-only package mounted on
the compute runtime and then as a direct bind over an already-created device.

### 1. Bind Doe to `@simulatte/webgpu/compute`

```js
import { requestDevice } from "@simulatte/webgpu/compute";
import { createDoeNamespace } from "@simulatte/webgpu-doe";

const doe = createDoeNamespace({ requestDevice });
const gpu = await doe.requestDevice();

const src = gpu.buffer.create({ data: Float32Array.of(1, 2, 3, 4) });
const dst = gpu.buffer.create({ size: src.size, usage: "storageReadWrite" });

await gpu.kernel.run({
  code: `
    @group(0) @binding(0) var<storage, read> src: array<f32>;
    @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

    @compute @workgroup_size(4)
    fn main(@builtin(global_invocation_id) gid: vec3u) {
      let i = gid.x;
      dst[i] = src[i] * 2.0;
    }
  `,
  bindings: [src, dst],
  workgroups: 1,
});

console.log(await gpu.buffer.read({ buffer: dst, type: Float32Array }));
```

### 2. Bind Doe to an existing device

```js
import { requestDevice } from "@simulatte/webgpu";
import doe from "@simulatte/webgpu-doe";

const device = await requestDevice();
const gpu = doe.bind(device);
```

### 3. Inject your own request path

```js
import { createDoeNamespace } from "@simulatte/webgpu-doe";

const doe = createDoeNamespace({
  async requestDevice(options) {
    return createMyCompatibleDevice(options);
  },
});

const gpu = await doe.requestDevice();
```

The only requirement is that the bound device exposes the WebGPU methods Doe
uses internally:

- `createBuffer`
- `createShaderModule`
- `createBindGroupLayout`
- `createPipelineLayout`
- `createComputePipeline`
- `createBindGroup`
- `createCommandEncoder`
- `queue.writeBuffer`
- `queue.submit`
- optionally `queue.onSubmittedWorkDone`

## API shape

The JavaScript Doe API is split by role:

- `gpu.buffer.*`
  - convenience helpers over raw `GPUBuffer`
- `gpu.kernel.*`
  - explicit reusable compute primitives
- `gpu.compute(...)`
  - the narrow one-shot typed-array workflow
- `gpu.compute.begin(...)`
  - batched explicit dispatch under one submit
- `gpu.commandEncoder.create(...)`
  - the lowest-level explicit Doe submission path above raw WebGPU

Most users only need:

- `doe.requestDevice(...)`
- `doe.bind(device)`
- `gpu.buffer.*`
- `gpu.kernel.run(...)`
- `gpu.kernel.create(...)`
- `gpu.compute(...)`

## API surface

### `createDoeNamespace({ requestDevice } = {})`

Creates a Doe namespace object with:

- `requestDevice(options?)`
- `bind(device)`

If `requestDevice` is omitted, `doe.requestDevice()` throws an explicit error
and `doe.bind(device)` remains available.

### `doe`

Default namespace created with no injected `requestDevice(...)`. This is
useful when you want only `doe.bind(device)`.

## Choosing the right entrypoint

Use `gpu.compute(...)` when:

- your inputs already live in JS typed arrays
- you want Doe to allocate temporary buffers and clean them up
- you only need one dispatch and one typed-array output

Use `gpu.kernel.run(...)` when:

- you already own buffers
- you want explicit resource control
- you only need one dispatch

Use `gpu.kernel.create(...)` plus `kernel.dispatch(...)` when:

- the same shader shape will run more than once
- reuse matters, but one submit per dispatch is still fine

Use `gpu.compute.begin(...)` when:

- multiple dispatches should share one encoder and one compute pass
- submission and waiting should happen once per round
- reusable binding sets should amortize bind-group creation

Use `gpu.commandEncoder.create(...)` when:

- you want the lowest-level explicit Doe path above raw WebGPU
- pass lifetime should be explicit
- you still want Doe kernels and binding validation during encoding

Doe validates dispatch counts through `maxComputeWorkgroupsPerDimension` and
positive-integer checks. It does not treat dispatch counts as
`@workgroup_size(...)` limits.

## Lower-overhead batching example

```js
import { requestDevice } from "@simulatte/webgpu/compute";
import { createDoeNamespace } from "@simulatte/webgpu-doe";

const doe = createDoeNamespace({ requestDevice });
const gpu = await doe.requestDevice();

const src = gpu.buffer.create({ data: Float32Array.of(1, 2, 3, 4) });
const dst = gpu.buffer.create({ size: src.size, usage: "storageReadWrite" });

const kernel = gpu.kernel.create({
  code: `
    @group(0) @binding(0) var<storage, read> src: array<f32>;
    @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

    @compute @workgroup_size(4)
    fn main(@builtin(global_invocation_id) gid: vec3u) {
      let i = gid.x;
      dst[i] = src[i] * 2.0;
    }
  `,
  bindings: [src, dst],
});

const bindings = kernel.bindings.create([src, dst]);
const batch = gpu.compute.begin();

batch.dispatch(kernel, {
  bindings,
  workgroups: [1, 1, 1],
});

batch.dispatch(kernel, {
  bindings,
  workgroups: [1, 1, 1],
});

await batch.submit();
console.log(await gpu.buffer.read({ buffer: dst, type: Float32Array }));
```

## Lowest-level Doe encoding example

```js
const encoder = gpu.commandEncoder.create();
const pass = encoder.beginComputePass();

kernel.encode(pass, {
  bindings,
  workgroups: [1, 1, 1],
});

pass.end();
await encoder.submit();
```

## Release contract

This package intentionally owns only the helper contract. It should stay
transport-free. Runtime loading and raw WebGPU surfaces belong in
`@simulatte/webgpu`.

## License

Apache-2.0
