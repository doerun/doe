const kRows : u32 = 32768u;
const kCols : u32 = 2048u;

@group(0) @binding(0) var<storage, read> matrixData : array<f32>;
@group(0) @binding(1) var<storage, read> vectorData : array<f32>;
@group(0) @binding(2) var<storage, read_write> outData : array<f32>;

@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) gid : vec3u) {
  let row = gid.x;
  if (row >= kRows) {
    return;
  }

  let base = row * kCols;
  var accum : f32 = 0.0;
  var col : u32 = 0u;
  loop {
    if (col >= kCols) {
      break;
    }
    accum = accum + matrixData[base + col] * vectorData[col];
    col = col + 1u;
  }

  outData[row] = accum;
}
