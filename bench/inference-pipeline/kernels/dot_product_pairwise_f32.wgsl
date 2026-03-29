struct Params {
  length: u32,
  _pad0: u32,
  _pad1: u32,
  _pad2: u32,
};

const WORKGROUP_WIDTH: u32 = 8u;

@group(0) @binding(0) var<uniform> params: Params;
@group(0) @binding(1) var<storage, read> lhs: array<f32>;
@group(0) @binding(2) var<storage, read> rhs: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

var<workgroup> partial: array<f32, WORKGROUP_WIDTH>;

@compute @workgroup_size(8)
fn main(@builtin(local_invocation_id) lid: vec3u) {
  let tid = lid.x;
  var term: f32 = 0.0;
  if (tid < params.length) {
    term = lhs[tid] * rhs[tid];
  }
  partial[tid] = term;
  workgroupBarrier();

  var stride: u32 = 1u;
  loop {
    if (stride >= WORKGROUP_WIDTH) {
      break;
    }
    if ((tid % (stride * 2u)) == 0u && (tid + stride) < WORKGROUP_WIDTH) {
      partial[tid] = partial[tid] + partial[tid + stride];
    }
    workgroupBarrier();
    continuing {
      stride = stride * 2u;
    }
  }

  if (tid == 0u) {
    output[0] = partial[0];
  }
}
