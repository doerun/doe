@group(0) @binding(0) var<storage, read> lhs: array<f32>;
@group(0) @binding(1) var<storage, read> rhs: array<f32>;
@group(0) @binding(2) var<storage, read_write> out: array<f32>;

override cols: u32 = 16u;

@compute @workgroup_size(8, 8, 1)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  let row = gid.y;
  let col = gid.x;
  var acc = 0.0;
  for (var k = 0u; k < cols; k = k + 1u) {
    acc = acc + lhs[row * cols + k] * rhs[k * cols + col];
  }
  out[row * cols + col] = acc;
}
