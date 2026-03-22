# doe-gpu

WebGPU runtime you embed when you can't ship Dawn.

`doe-gpu` is the npm package for Doe, a Zig-first WebGPU runtime with formal
verification support, compute-first design, and drop-in `webgpu.h` compatibility.

## Install

```bash
npm install doe-gpu
```

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

## Subpath exports

```js
import { gpu } from 'doe-gpu';           // full (default)
import { gpu } from 'doe-gpu/compute';   // compute-only surface
import { gpu } from 'doe-gpu/browser';   // browser shim
```

## What Doe is

- ~2 MB native binary (vs ~11 MB for Dawn)
- Drop-in `webgpu.h` compatibility
- Compute-first design
- Formal verification via Lean proofs
- Vulkan, Metal, and D3D12 backends
- Runs on Node.js, Bun, and Deno

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

## License

Apache-2.0. See [`docs/licensing.md`](../../docs/licensing.md).
