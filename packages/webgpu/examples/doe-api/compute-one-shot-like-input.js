import { doe } from "@simulatte/webgpu/compute";

const gpu = await doe.requestDevice();

const result = await gpu.compute({
  code: `
    struct Scale {
      value: f32,
    };

    @group(0) @binding(0) var<uniform> scale: Scale;
    @group(0) @binding(1) var<storage, read> src: array<f32>;
    @group(0) @binding(2) var<storage, read_write> dst: array<f32>;

    @compute @workgroup_size(4)
    fn main(@builtin(global_invocation_id) gid: vec3u) {
      let i = gid.x;
      dst[i] = src[i] * scale.value;
    }
  `,
  inputs: [
    {
      data: new Float32Array([2]),
      usage: "uniform",
      access: "uniform",
    },
    new Float32Array([1, 2, 3, 4]),
  ],
  output: {
    type: Float32Array,
    likeInput: 1,
  },
  workgroups: [1, 1],
});

console.log(JSON.stringify(Array.from(result)));
