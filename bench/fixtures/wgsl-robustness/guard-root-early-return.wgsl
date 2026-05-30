@group(0) @binding(0) var<storage, read_write> data: array<u32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  let length = arrayLength(&data);
  if (gid.x >= length) {
    return;
  }
  data[gid.x] = data[gid.x] + 1u;
}
