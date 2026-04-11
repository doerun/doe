struct ReduceConfig {
  element_count: u32,
  _pad0: u32,
  _pad1: u32,
  _pad2: u32,
}

@group(0) @binding(0) var<uniform> config: ReduceConfig;
@group(0) @binding(1) var<storage, read> src: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read_write> dst: array<vec4<f32>>;

var<workgroup> scratch: array<vec4<f32>, 64>;

@compute @workgroup_size(64, 1, 1)
fn main(
  @builtin(local_invocation_id) local_id: vec3<u32>,
  @builtin(workgroup_id) workgroup_id: vec3<u32>,
) {
  let lane = local_id.x;
  let source_index = workgroup_id.x * 64u + lane;

  var accumulator = vec4<f32>(0.0);
  if (source_index < config.element_count) {
    accumulator = src[source_index];
  }

  scratch[lane] = accumulator;
  workgroupBarrier();

  var stride: u32 = 32u;
  loop {
    if (lane < stride) {
      scratch[lane] = scratch[lane] + scratch[lane + stride];
    }
    workgroupBarrier();

    if (stride == 1u) {
      break;
    }
    stride = stride / 2u;
  }

  if (lane == 0u) {
    dst[workgroup_id.x] = scratch[0];
  }
}
