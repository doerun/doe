enable subgroups;
const workgroup_size_x: u32 = 16;
const workgroup_size_y: u32 = 16;
const workgroup_size_z: u32 = 1;
const tile_size: u32 = 16;
@group(0) @binding(0) var<storage, read> a: array<f32>;
@group(0) @binding(1) var<storage, read_write> output: array<f32>;
struct Uniforms {
  a_shape: vec2<u32>,
  a_stride: u32,
  output_shape: vec2<u32>,
  output_stride: u32,
  output_size: u32
};
@group(0) @binding(2) var<uniform> uniforms: Uniforms;

alias a_indices_t = vec2<u32>;
fn i2o_a(indices : a_indices_t)->u32 {
  return indices[0] * uniforms.a_stride + indices[1];
}
fn get_a_by_indices(indices_fnarg: a_indices_t)->f32 {
  return a[i2o_a(indices_fnarg)];
}
alias output_value_t = f32;
alias output_indices_t = vec2<u32>;
fn i2o_output(indices : output_indices_t)->u32 {
  return indices[0] * uniforms.output_stride + indices[1];
}
fn set_output_by_indices(indices: output_indices_t, value: output_value_t) {
  output[i2o_output(indices)]=value;
}

var<workgroup> tile : array<array<output_value_t, tile_size + 1>, tile_size>;
@compute @workgroup_size(workgroup_size_x, workgroup_size_y, workgroup_size_z)
fn main(@builtin(global_invocation_id) global_id : vec3<u32>,
        @builtin(workgroup_id) workgroup_id : vec3<u32>,
        @builtin(local_invocation_index) local_idx : u32,
        @builtin(local_invocation_id) local_id : vec3<u32>,
        @builtin(subgroup_invocation_id) sg_id : u32,
        @builtin(subgroup_size) sg_size : u32) {
  let global_idx = global_id.x;
  let workgroup_idx = workgroup_id.x;
  let stride = (uniforms.output_shape[1] - 1) / tile_size + 1;
  let workgroup_id_x = workgroup_idx % stride;
  let workgroup_id_y = workgroup_idx / stride;
  let input_col = workgroup_id_y * tile_size + local_id.x;
  let input_row = workgroup_id_x * tile_size + local_id.y;
  if (input_row < uniforms.a_shape[0] && input_col < uniforms.a_shape[1]) {
    tile[local_id.y][local_id.x] = get_a_by_indices(a_indices_t(input_row, input_col));
  }
  workgroupBarrier();
  let output_col = workgroup_id_x * tile_size + local_id.x;
  let output_row = workgroup_id_y * tile_size + local_id.y;
  if (output_row < uniforms.output_shape[0] && output_col < uniforms.output_shape[1]) {
    set_output_by_indices(output_indices_t(output_row, output_col), tile[local_id.x][local_id.y]);
  }
}
