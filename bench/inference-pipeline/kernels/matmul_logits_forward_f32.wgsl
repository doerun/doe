struct Params {
  rows: u32,
  cols: u32,
  _pad0: u32,
  _pad1: u32,
};

@group(0) @binding(0) var<uniform> params: Params;
@group(0) @binding(1) var<storage, read> hidden: array<f32>;
@group(0) @binding(2) var<storage, read> weights: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(1)
fn main(
  @builtin(local_invocation_id) lid: vec3u,
  @builtin(workgroup_id) wid: vec3u,
) {
  if (lid.x != 0u || wid.x >= params.rows) {
    return;
  }
  let row = wid.x;
  var acc: f32 = 0.0;
  for (var col: u32 = 0u; col < params.cols; col = col + 1u) {
    acc = acc + hidden[col] * weights[row * params.cols + col];
  }
  output[row] = acc;
}
