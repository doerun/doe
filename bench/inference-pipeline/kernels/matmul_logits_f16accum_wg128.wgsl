enable f16;

struct Params {
  rows: u32,
  cols: u32,
  _pad0: u32,
  _pad1: u32,
};

const WORKGROUP_WIDTH: u32 = 128u;

@group(0) @binding(0) var<uniform> params: Params;
@group(0) @binding(1) var<storage, read> hidden: array<f32>;
@group(0) @binding(2) var<storage, read> weights: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

var<workgroup> partial: array<f32, WORKGROUP_WIDTH>;

@compute @workgroup_size(128)
fn main(
  @builtin(local_invocation_id) lid: vec3u,
  @builtin(workgroup_id) wid: vec3u,
) {
  let row = wid.x;
  let tid = lid.x;
  if (row >= params.rows) {
    return;
  }

  var acc: f16 = 0.0h;
  for (var col: u32 = tid; col < params.cols; col = col + WORKGROUP_WIDTH) {
    acc = acc + f16(hidden[col]) * f16(weights[row * params.cols + col]);
  }
  partial[tid] = f32(acc);
  workgroupBarrier();

  var stride: u32 = WORKGROUP_WIDTH / 2u;
  loop {
    if (stride == 0u) {
      break;
    }
    if (tid < stride) {
      partial[tid] = partial[tid] + partial[tid + stride];
    }
    workgroupBarrier();
    continuing {
      stride = stride / 2u;
    }
  }

  if (tid == 0u) {
    output[row] = partial[0];
  }
}
