@group(0) @binding(0) var<storage, read> input: array<f32>;
@group(0) @binding(1) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(1)
fn main(@builtin(workgroup_id) wid: vec3u) {
  output[wid.x] = input[wid.x];
}
