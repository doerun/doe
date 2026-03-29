struct Params {
  length: u32,
  _pad0: u32,
  _pad1: u32,
  _pad2: u32,
};

@group(0) @binding(0) var<uniform> params: Params;
@group(0) @binding(1) var<storage, read> lhs: array<f32>;
@group(0) @binding(2) var<storage, read> rhs: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  if (gid.x != 0u) {
    return;
  }
  var sum: f32 = 0.0;
  var remaining: u32 = params.length;
  loop {
    if (remaining == 0u) {
      break;
    }
    remaining = remaining - 1u;
    sum = sum + lhs[remaining] * rhs[remaining];
  }
  output[0] = sum;
}
