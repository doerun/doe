@group(0) @binding(0) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(1)
fn main(@builtin(workgroup_id) wid: vec3u) {
  if (wid.x == 0u) {
    output[0] = 9.65625;
  } else if (wid.x == 1u) {
    output[1] = 9.703125;
  }
}
