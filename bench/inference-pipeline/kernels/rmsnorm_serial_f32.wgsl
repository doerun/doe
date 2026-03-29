struct Uniforms {
  size: u32,
  eps: f32,
  _pad0: u32,
  _pad1: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> input: array<f32>;
@group(0) @binding(2) var<storage, read> weight: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(1)
fn main(@builtin(workgroup_id) wid: vec3u) {
  let row_offset = wid.x * u.size;

  var sum_sq: f32 = 0.0;
  for (var i: u32 = 0u; i < u.size; i = i + 1u) {
    let v = input[row_offset + i];
    sum_sq = sum_sq + v * v;
  }

  let rms = 1.0 / sqrt(sum_sq / f32(u.size) + u.eps);

  for (var j: u32 = 0u; j < u.size; j = j + 1u) {
    output[row_offset + j] = input[row_offset + j] * rms * weight[j];
  }
}
