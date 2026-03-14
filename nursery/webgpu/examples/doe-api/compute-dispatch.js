import { doe } from "@simulatte/webgpu/compute";

const gpu = await doe.requestDevice();
const src = gpu.buffer.fromData(new Float32Array([1, 2, 3, 4]));
const dst = gpu.buffer.like(src, {
  usage: "storageReadWrite",
});

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

const result = await gpu.buffer.read(dst, Float32Array);
console.log(JSON.stringify(Array.from(result)));
