@group(0) @binding(0) var<storage, read> input_values: array<u32>;
@group(0) @binding(1) var<storage, read_write> output_values: array<u32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  let index = gid.x;
  if (index == 0u) {
    output_values[index] = input_values[index];
    return;
  }
  output_values[index] = input_values[index - 1u] + input_values[index];
}
