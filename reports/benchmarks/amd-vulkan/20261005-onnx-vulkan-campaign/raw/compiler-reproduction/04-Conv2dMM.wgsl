enable subgroups;
const workgroup_size_x: u32 = 8;
const workgroup_size_y: u32 = 8;
const workgroup_size_z: u32 = 1;
@group(0) @binding(0) var<storage, read> x: array<f32>;
@group(0) @binding(1) var<storage, read> w: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read> bias: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read_write> result: array<vec4<f32>>;
struct Uniforms {
  x_shape: vec4<u32>,
  x_stride: vec3<u32>,
  w_shape: vec4<u32>,
  w_stride: vec3<u32>,
  result_shape: vec4<u32>,
  result_stride: vec3<u32>,
  dim_a_outer: u32,
  dim_b_outer: u32,
  dim_inner: u32,
  pads: vec4<u32>,
  strides: vec2<u32>,
  dilations: vec2<u32>,
  logical_dispatch_x: u32,
  logical_dispatch_y: u32,
  logical_dispatch_z: u32
};
@group(0) @binding(4) var<uniform> uniforms: Uniforms;

alias x_value_t = f32;
alias x_indices_t = vec4<u32>;
alias x_element_t = f32;
alias w_value_t = vec4<f32>;
alias w_indices_t = vec4<u32>;
alias bias_value_t = vec4<f32>;
alias bias_indices_t = u32;
alias bias_element_t = f32;
alias result_indices_t = vec4<u32>;

fn getIndexFromCoords3D(coords : vec3<i32>, shape : vec3<i32>) -> i32 {
  return dot(coords, vec3<i32>(shape.y * shape.z, shape.z, 1));
}
fn getIndexFromCoords4D(coords : vec4<i32>, shape : vec4<i32>) -> i32 {
  return dot(coords, vec4<i32>(shape.y * shape.z * shape.w, shape.z * shape.w, shape.w, 1));
}
fn getOutputIndexFromCoords(coords : vec4<i32>) -> i32 {
  return dot(coords, vec4<i32>(i32(uniforms.result_stride.x), i32(uniforms.result_stride.y), i32(uniforms.result_stride.z), 1));
}
fn setOutputAtIndex(flatIndex : i32, value : vec4<x_element_t>) {
  result[flatIndex] = vec4<x_element_t>(value);
}
fn setOutputAtCoords(d0 : i32, d1 : i32, d2 : i32, d3 : i32, value : vec4<x_element_t>){
  let flatIndex = getOutputIndexFromCoords(vec4<i32>(d0, d1, d2, d3));
  setOutputAtIndex(flatIndex, value);
}
fn getBiasByOutputCoords(coords : vec4<i32>) -> bias_value_t {
  return bias[coords.w];
}fn mm_readA(batch : i32, row : i32, colIn : i32) -> vec3<x_element_t> {
let col = colIn * 3;
if(row < i32(uniforms.dim_a_outer) && col < i32(uniforms.dim_inner)) {
  let inChannels = i32(uniforms.w_shape[2]);
let outWidth = i32(uniforms.result_shape[2]);
let outRow = row / outWidth;
 let outCol = row % outWidth;
let WRow = col / (i32(uniforms.w_shape[1]) * inChannels);
let WCol = col / inChannels % i32(uniforms.w_shape[1]);
let xRow = outRow * i32(uniforms.strides[0]) + i32(uniforms.dilations[0]) * WRow - i32(uniforms.pads[0]);
let xCol = outCol * i32(uniforms.strides[1]) + i32(uniforms.dilations[1]) * WCol - i32(uniforms.pads[1]);
let xCh = col % inChannels;
var resData = vec3<x_element_t>(0.0);
 // The bounds checking is always needed since we use it to pad zero for
// the " same " padding type.
if (xRow >= 0 && xRow < i32(uniforms.x_shape[1]) && xCol >= 0 && xCol < i32(uniforms.x_shape[2])) {
  let coord = vec4<i32>(batch, xRow, xCol, xCh / 4);
  let xIndex = getIndexFromCoords4D(coord, vec4<i32>(uniforms.x_shape));
  resData = vec3<x_element_t>(x[xIndex], x[xIndex + 1], x[xIndex + 2]);}
return resData;
}
return vec3<x_element_t>(0.0);
}

fn mm_readB(batch : i32, row : i32, colIn : i32) -> vec4<x_element_t> {
let col = colIn * 4;
if(row < i32(uniforms.dim_inner) && col < i32(uniforms.dim_b_outer)) {
  return w[row * i32(uniforms.w_shape[3])  + colIn];

}
return vec4<x_element_t>(0.0);
}

fn mm_write(batch : i32, row : i32, colIn : i32, valueIn : vec4<x_element_t>) {
  let col = colIn * 4;
  if(row < i32(uniforms.dim_a_outer) && col < i32(uniforms.dim_b_outer)) {
    var value = valueIn;
    let outWidth =  i32(uniforms.result_shape[2]) ;
    let coords = vec4<i32>(batch, row / outWidth, row % outWidth, col / 4);
    value = value + getBiasByOutputCoords(coords);
    value = max(value, vec4<x_element_t>(x_element_t(0.000000)));
    setOutputAtCoords(coords[0], coords[1], coords[2], coords[3], value);
  }
}
var<workgroup> mm_Asub: array<array<vec3<x_element_t>, 8>, 32>;
var<workgroup> mm_Bsub: array<array<vec4<x_element_t>, 8>, 24>;
const rowPerThread = 4;
const colPerThread = 4;
const innerElementSize = 3;
const tileInner = 24;
@compute @workgroup_size(workgroup_size_x, workgroup_size_y, workgroup_size_z)
fn main(@builtin(global_invocation_id) global_id : vec3<u32>,
        @builtin(workgroup_id) workgroup_id : vec3<u32>,
        @builtin(local_invocation_index) local_idx : u32,
        @builtin(local_invocation_id) local_id : vec3<u32>,
        @builtin(subgroup_invocation_id) sg_id : u32,
        @builtin(subgroup_size) sg_size : u32,
        @builtin(num_workgroups) num_workgroups : vec3<u32>) {
  let workgroup_idx = workgroup_id.z * num_workgroups[0] * num_workgroups[1] + workgroup_id.y * num_workgroups[0] + workgroup_id.x;
  let global_idx = workgroup_idx * (workgroup_size_x * workgroup_size_y * workgroup_size_z) + local_idx;
  let logical_workgroup_id_z = workgroup_idx / (uniforms.logical_dispatch_x * uniforms.logical_dispatch_y);
  let logical_workgroup_id_y = (workgroup_idx % (uniforms.logical_dispatch_x * uniforms.logical_dispatch_y)) / uniforms.logical_dispatch_x;
  let logical_workgroup_id_x = (workgroup_idx % (uniforms.logical_dispatch_x * uniforms.logical_dispatch_y)) % uniforms.logical_dispatch_x;
  let logical_workgroup_id = vec3u(logical_workgroup_id_x, logical_workgroup_id_y, logical_workgroup_id_z);
  const workgroupSize = vec3u(workgroup_size_x, workgroup_size_y, workgroup_size_z);
  let logical_global_id = logical_workgroup_id * workgroupSize + local_id;
  let localRow = i32(local_id.y);
  let tileRow = localRow * rowPerThread;
  let tileCol = i32(local_id.x);
  let globalRow = i32(logical_global_id.y) * rowPerThread;
  let globalCol = i32(logical_global_id.x);
  let globalRowStart = i32(logical_workgroup_id.y) * 32;
  let globalColStart = i32(logical_workgroup_id.x) * 32;
  var acc: array<vec4<x_element_t>, rowPerThread>;
  let num_tiles = (uniforms.dim_inner - 1) / tileInner + 1;
  var kStart = 0;
  let batch = i32(logical_global_id.z);
  let tileRowB = localRow * 3;
  for (var t = 0; t < i32(num_tiles); t = t + 1) {
    for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
      let inputRow = tileRow + innerRow;
      let inputCol = tileCol;
      mm_Asub[inputRow][inputCol] = mm_readA(batch, globalRow + innerRow, kStart / innerElementSize + inputCol);
    }
    for (var innerRow = 0; innerRow < 3; innerRow = innerRow + 1) {
      let inputRow = tileRowB + innerRow;
      let inputCol = tileCol;
     mm_Bsub[inputRow][inputCol] = mm_readB(batch, kStart + inputRow, globalCol);
    }
    kStart = kStart + tileInner;
    workgroupBarrier();
    for (var k = 0; k < tileInner / innerElementSize; k = k + 1) {
      let BCached0 = mm_Bsub[k * innerElementSize][tileCol];
      let BCached1 = mm_Bsub[k * innerElementSize + 1][tileCol];
      let BCached2 = mm_Bsub[k * innerElementSize + 2][tileCol];
      for (var i = 0; i < rowPerThread; i = i + 1) {
        let ACached = mm_Asub[tileRow + i][k];
        acc[i] = BCached0 * ACached.x + acc[i];
        acc[i] = BCached1 * ACached.y + acc[i];
        acc[i] = BCached2 * ACached.z + acc[i];
        
      }
    }
    workgroupBarrier();
  }
  for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
    mm_write(batch, globalRow + innerRow, globalCol, acc[innerRow]);
  }

}
