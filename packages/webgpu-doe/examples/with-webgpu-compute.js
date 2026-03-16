import { requestDevice } from '@simulatte/webgpu/compute';
import { createDoeNamespace } from '@simulatte/webgpu-doe';

const doe = createDoeNamespace({ requestDevice });
const gpu = await doe.requestDevice();

const src = gpu.buffer.create({ data: Float32Array.of(1, 2, 3, 4) });
const dst = gpu.buffer.create({ size: src.size, usage: 'storageReadWrite' });

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
  workgroups: 1,
});

batch.dispatch(kernel, {
  bindings,
  workgroups: 1,
});

await batch.submit();

console.log(await gpu.buffer.read({ buffer: dst, type: Float32Array }));
