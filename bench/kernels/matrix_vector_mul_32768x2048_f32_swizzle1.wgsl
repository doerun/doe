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

    let base = 4u * (rowBy4 * kPackedCols + col);
    let v0 = vectorData[col + 0u];
    let v1 = vectorData[col + 1u];
    let v2 = vectorData[col + 2u];
    let v3 = vectorData[col + 3u];
    sum = sum + vec4<f32>(
      dot(matrixData[base + 0u], v0),
      dot(matrixData[base + 1u], v0),
      dot(matrixData[base + 2u], v0),
      dot(matrixData[base + 3u], v0)
    ) + vec4<f32>(
      dot(matrixData[base + 4u], v1),
      dot(matrixData[base + 5u], v1),
      dot(matrixData[base + 6u], v1),
      dot(matrixData[base + 7u], v1)
    ) + vec4<f32>(
      dot(matrixData[base + 8u], v2),
      dot(matrixData[base + 9u], v2),
      dot(matrixData[base + 10u], v2),
      dot(matrixData[base + 11u], v2)
    ) + vec4<f32>(
      dot(matrixData[base + 12u], v3),
      dot(matrixData[base + 13u], v3),
      dot(matrixData[base + 14u], v3),
      dot(matrixData[base + 15u], v3)
    );
    col = col + 4u;
  }

  outData[rowBy4] = sum;
}
