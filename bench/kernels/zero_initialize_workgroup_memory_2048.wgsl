const K_WORKGROUP_SIZE: u32 = 256u;
const K_WORKGROUP_ARRAY_SIZE: u32 = 2048u;
const K_LOOP_LENGTH: u32 = K_WORKGROUP_ARRAY_SIZE / K_WORKGROUP_SIZE;

@group(0) @binding(0) var<storage, read_write> dst: array<f32>;
var<workgroup> wg: array<f32, K_WORKGROUP_ARRAY_SIZE>;

@compute @workgroup_size(K_WORKGROUP_SIZE, 1, 1)
fn main(@builtin(local_invocation_id) local_id: vec3u) {
  for (var k: u32 = 0u; k < K_LOOP_LENGTH; k = k + 1u) {
    let index: u32 = K_LOOP_LENGTH * local_id.x + k;
    dst[index] = wg[index];
  }
}
