enable subgroups;
const workgroup_size_x: u32 = 64;
const workgroup_size_y: u32 = 1;
const workgroup_size_z: u32 = 1;
@group(0) @binding(0) var<storage, read> input_a: array<vec4<f32>>;
@group(0) @binding(1) var<storage, read> input_b: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read_write> output: array<vec4<f32>>;
struct Uniforms {
  vec_size: u32
};
@group(0) @binding(3) var<uniform> uniforms: Uniforms;

alias input_a_value_t = vec4<f32>;
alias input_a_element_t = f32;
alias input_b_value_t = vec4<f32>;
alias input_b_element_t = f32;
alias output_value_t = vec4<f32>;

@compute @workgroup_size(workgroup_size_x, workgroup_size_y, workgroup_size_z)
fn main(@builtin(global_invocation_id) global_id : vec3<u32>,
        @builtin(workgroup_id) workgroup_id : vec3<u32>,
        @builtin(local_invocation_index) local_idx : u32,
        @builtin(local_invocation_id) local_id : vec3<u32>,
        @builtin(subgroup_invocation_id) sg_id : u32,
        @builtin(subgroup_size) sg_size : u32) {
  let global_idx = global_id.x;
  let workgroup_idx = workgroup_id.x;
  if (global_idx >= uniforms.vec_size) { return; }
let a = input_a[global_idx];
let b = input_b[global_idx];
output[global_idx]=a + b;
}
