import { doe } from "@simulatte/webgpu/compute";

const gpu = await doe.requestDevice();

const result = await gpu.compute({
  code: `
    @group(0) @binding(0) var<storage, read> lhs: array<f32>;
    @group(0) @binding(1) var<storage, read> rhs: array<f32>;
    @group(0) @binding(2) var<storage, read_write> dst: array<f32>;

    @compute @workgroup_size(4)
    fn main(@builtin(global_invocation_id) gid: vec3u) {
      let i = gid.x;
      dst[i] = lhs[i] + rhs[i];
    }
  `,
  inputs: [
    new Float32Array([1, 2, 3, 4]),
    new Float32Array([10, 20, 30, 40]),
  ],
  output: {
    type: Float32Array,
  },
  workgroups: 1,
});

console.log(JSON.stringify(Array.from(result)));
