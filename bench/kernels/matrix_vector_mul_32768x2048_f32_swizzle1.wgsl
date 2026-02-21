const kRows : u32 = 32768u;
const kPackedCols : u32 = 512u;

@group(0) @binding(0) var<storage, read> matrixData : array<vec4<f32>>;
@group(0) @binding(1) var<storage, read> vectorData : array<vec4<f32>>;
@group(0) @binding(2) var<storage, read_write> outData : array<vec4<f32>>;

@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) gid : vec3u) {
  let rowBy4 = gid.x;
  if (rowBy4 >= (kRows / 4u)) {
    return;
  }

  var sum : vec4<f32> = vec4<f32>(0.0);
  var col : u32 = 0u;
  loop {
    if (col >= kPackedCols) {
      break;
    }

    let v = vectorData[col];
    let base = 4u * (rowBy4 * kPackedCols + col);
    sum.x = sum.x + dot(matrixData[base + 0u], v);
    sum.y = sum.y + dot(matrixData[base + 1u], v);
    sum.z = sum.z + dot(matrixData[base + 2u], v);
    sum.w = sum.w + dot(matrixData[base + 3u], v);
    col = col + 1u;
  }

  outData[rowBy4] = sum;
}
