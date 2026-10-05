enable subgroups;
const workgroup_size_x: u32 = 64;
const workgroup_size_y: u32 = 1;
const workgroup_size_z: u32 = 1;
@group(0) @binding(0) var<storage, read> a: array<vec4<f32>>;
@group(0) @binding(1) var<storage, read> b: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read_write> output: array<vec4<f32>>;
struct Uniforms {
  a_shape: vec2<u32>,
  a_stride: u32,
  b_shape: vec2<u32>,
  b_stride: u32,
  output_shape: vec3<u32>,
  output_stride: vec2<u32>,
  output_size: u32,
  M: u32,
  N: u32,
  K: u32
};
@group(0) @binding(3) var<uniform> uniforms: Uniforms;

alias a_value_t = vec4<f32>;
alias a_indices_t = vec2<u32>;
alias a_element_t = f32;
fn i2o_a(indices : a_indices_t)->u32 {
  return indices[0] * uniforms.a_stride + indices[1];
}
alias b_value_t = vec4<f32>;
alias b_indices_t = vec2<u32>;
alias b_element_t = f32;
fn i2o_b(indices : b_indices_t)->u32 {
  return indices[0] * uniforms.b_stride + indices[1];
}
alias output_value_t = vec4<f32>;
alias output_indices_t = vec3<u32>;
alias output_element_t = f32;
fn i2o_output(indices : output_indices_t)->u32 {
  return indices[0] * uniforms.output_stride[0] + indices[1] * uniforms.output_stride[1] + indices[2];
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
let col = (global_idx % (uniforms.N / 4)) * 4;
var index1 = global_idx / (uniforms.N / 4);
let stride1 = uniforms.M / 4;
let row = (index1 % stride1) * 4;
let batch = index1 / stride1;
var a_indices: a_indices_t;
a_indices[0]=0;
a_indices[1]=0;
let a_offset = i2o_a(a_indices)*4;
var b_indices: b_indices_t;
b_indices[0]=0;
b_indices[1]=0;
let b_offset = i2o_b(b_indices) * 4;
var values: array<output_value_t, 4>;
for (var k: u32 = 0u; k < uniforms.K; k = k + 4) {
var a_data: a_value_t;
let b_data0 = b[(b_offset + (k + 0) * uniforms.N + col) / 4];
let b_data1 = b[(b_offset + (k + 1) * uniforms.N + col) / 4];
let b_data2 = b[(b_offset + (k + 2) * uniforms.N + col) / 4];
let b_data3 = b[(b_offset + (k + 3) * uniforms.N + col) / 4];
a_data = a[(a_offset + (row + 0) * uniforms.K + k) / 4];
values[0] = fma(b_value_t(a_data[0]), b_data0, values[0]);
values[0] = fma(b_value_t(a_data[1]), b_data1, values[0]);
values[0] = fma(b_value_t(a_data[2]), b_data2, values[0]);
values[0] = fma(b_value_t(a_data[3]), b_data3, values[0]);
a_data = a[(a_offset + (row + 1) * uniforms.K + k) / 4];
values[1] = fma(b_value_t(a_data[0]), b_data0, values[1]);
values[1] = fma(b_value_t(a_data[1]), b_data1, values[1]);
values[1] = fma(b_value_t(a_data[2]), b_data2, values[1]);
values[1] = fma(b_value_t(a_data[3]), b_data3, values[1]);
a_data = a[(a_offset + (row + 2) * uniforms.K + k) / 4];
values[2] = fma(b_value_t(a_data[0]), b_data0, values[2]);
values[2] = fma(b_value_t(a_data[1]), b_data1, values[2]);
values[2] = fma(b_value_t(a_data[2]), b_data2, values[2]);
values[2] = fma(b_value_t(a_data[3]), b_data3, values[2]);
a_data = a[(a_offset + (row + 3) * uniforms.K + k) / 4];
values[3] = fma(b_value_t(a_data[0]), b_data0, values[3]);
values[3] = fma(b_value_t(a_data[1]), b_data1, values[3]);
values[3] = fma(b_value_t(a_data[2]), b_data2, values[3]);
values[3] = fma(b_value_t(a_data[3]), b_data3, values[3]);

}
for (var i = 0u; i < 4u; i++) {
  var value = values[i];


  let cur_indices = output_indices_t(batch, row + i, col/ 4);
  let offset = i2o_output(cur_indices);
output[offset]=value;}

}
