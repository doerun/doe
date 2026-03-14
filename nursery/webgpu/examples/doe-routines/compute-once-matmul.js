import { doe } from "@simulatte/webgpu/compute";

const gpu = await doe.requestDevice();
const M = 256;
const K = 512;
const N = 256;

const lhs = Float32Array.from({ length: M * K }, (_, i) => (i % 17) / 17);
const rhs = Float32Array.from({ length: K * N }, (_, i) => (i % 13) / 13);
const dims = new Uint32Array([M, K, N, 0]);

const result = await gpu.compute.once({
  code: `
    struct Dims {
      m: u32,
      k: u32,
      n: u32,
      _pad: u32,
    };

    @group(0) @binding(0) var<uniform> dims: Dims;
    @group(0) @binding(1) var<storage, read> lhs: array<f32>;
    @group(0) @binding(2) var<storage, read> rhs: array<f32>;
    @group(0) @binding(3) var<storage, read_write> out: array<f32>;

    @compute @workgroup_size(8, 8)
    fn main(@builtin(global_invocation_id) gid: vec3u) {
      let row = gid.y;
      let col = gid.x;
      if (row >= dims.m || col >= dims.n) {
        return;
      }

      var acc = 0.0;
      for (var i = 0u; i < dims.k; i = i + 1u) {
        acc += lhs[row * dims.k + i] * rhs[i * dims.n + col];
      }
      out[row * dims.n + col] = acc;
    }
  `,
  inputs: [
    { data: dims, usage: "uniform", access: "uniform" },
    lhs,
    rhs,
  ],
  output: {
    type: Float32Array,
    size: M * N * Float32Array.BYTES_PER_ELEMENT,
  },
  workgroups: [Math.ceil(N / 8), Math.ceil(M / 8)],
});

console.log(JSON.stringify(Array.from(result.subarray(0, 8), (value) => Number(value.toFixed(4)))));
