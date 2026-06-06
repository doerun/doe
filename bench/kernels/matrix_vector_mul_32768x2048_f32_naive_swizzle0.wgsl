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

  let row0Base = (4u * rowBy4 + 0u) * kPackedCols;
  let row1Base = (4u * rowBy4 + 1u) * kPackedCols;
  let row2Base = (4u * rowBy4 + 2u) * kPackedCols;
  let row3Base = (4u * rowBy4 + 3u) * kPackedCols;
  var sum : vec4<f32> = vec4<f32>(0.0);
  var col : u32 = 0u;
  loop {
    if (col >= kPackedCols) {
      break;
    }

    let v0 = vectorData[col + 0u];
    let v1 = vectorData[col + 1u];
    let v2 = vectorData[col + 2u];
    let v3 = vectorData[col + 3u];
    sum = sum + vec4<f32>(
      dot(matrixData[row0Base + col + 0u], v0),
      dot(matrixData[row1Base + col + 0u], v0),
      dot(matrixData[row2Base + col + 0u], v0),
      dot(matrixData[row3Base + col + 0u], v0)
    ) + vec4<f32>(
      dot(matrixData[row0Base + col + 1u], v1),
      dot(matrixData[row1Base + col + 1u], v1),
      dot(matrixData[row2Base + col + 1u], v1),
      dot(matrixData[row3Base + col + 1u], v1)
    ) + vec4<f32>(
      dot(matrixData[row0Base + col + 2u], v2),
      dot(matrixData[row1Base + col + 2u], v2),
      dot(matrixData[row2Base + col + 2u], v2),
      dot(matrixData[row3Base + col + 2u], v2)
    ) + vec4<f32>(
      dot(matrixData[row0Base + col + 3u], v3),
      dot(matrixData[row1Base + col + 3u], v3),
      dot(matrixData[row2Base + col + 3u], v3),
      dot(matrixData[row3Base + col + 3u], v3)
    );
    col = col + 4u;
  }

  outData[rowBy4] = sum;
}
