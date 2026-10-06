enable subgroups;
const workgroup_size_x: u32 = 64;
const workgroup_size_y: u32 = 1;
const workgroup_size_z: u32 = 1;
const tile_size: u32 = 16;
@group(0) @binding(0) var<storage, read> a: array<f32>;
@group(0) @binding(1) var<storage, read_write> output: array<f32>;
struct Uniforms {
  a_shape: vec4<u32>,
  a_stride: vec3<u32>,
  output_shape: vec4<u32>,
  output_stride: vec3<u32>,
  output_size: u32
};
@group(0) @binding(2) var<uniform> uniforms: Uniforms;

alias a_indices_t = vec4<u32>;
fn i2o_a(indices : a_indices_t)->u32 {
  return indices[0] * uniforms.a_stride[0] + indices[1] * uniforms.a_stride[1] + indices[2] * uniforms.a_stride[2] + indices[3];
}
fn get_a_by_indices(indices_fnarg: a_indices_t)->f32 {
  return a[i2o_a(indices_fnarg)];
}
alias output_value_t = f32;
alias output_indices_t = vec4<u32>;
fn o2i_output(offset : u32)->output_indices_t {
  var indices: output_indices_t;
  var current = offset;
  indices[0] = current / uniforms.output_stride[0];
  current = current % uniforms.output_stride[0];
  indices[1] = current / uniforms.output_stride[1];
  current = current % uniforms.output_stride[1];
  indices[2] = current / uniforms.output_stride[2];
  current = current % uniforms.output_stride[2];
  indices[3] = current;
  return indices;
}

fn perm(i: output_indices_t)->a_indices_t {
  var a: a_indices_t;
  a[2] = i[0];
  a[3] = i[1];
  a[1] = i[2];
  a[0] = i[3];
  return a;
}
@compute @workgroup_size(workgroup_size_x, workgroup_size_y, workgroup_size_z)
fn main(@builtin(global_invocation_id) global_id : vec3<u32>,
        @builtin(workgroup_id) workgroup_id : vec3<u32>,
        @builtin(local_invocation_index) local_idx : u32,
        @builtin(local_invocation_id) local_id : vec3<u32>,
        @builtin(subgroup_invocation_id) sg_id : u32,
        @builtin(subgroup_size) sg_size : u32) {
  let global_idx = global_id.x;
  let workgroup_idx = workgroup_id.x;
  if (global_idx >= uniforms.output_size) { return; }
  let indices = o2i_output(global_idx);
  let x_indices = perm(indices);
  output[global_idx]=get_a_by_indices(x_indices);
}
