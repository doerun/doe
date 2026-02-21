const kRows : u32 = 32768u;
const kPackedCols : u32 = 512u;
const kWorkgroupSize : u32 = 64u;
const kColsPerInvocation : u32 = (kPackedCols + kWorkgroupSize - 1u) / kWorkgroupSize;

@group(0) @binding(0) var<storage, read> matrixData : array<vec4<f32>>;
@group(0) @binding(1) var<storage, read> vectorData : array<vec4<f32>>;
@group(0) @binding(2) var<storage, read_write> outData : array<vec4<f32>>;

var<workgroup> partialSums : array<vec4<f32>, 64>;

@compute @workgroup_size(64, 1, 1)
fn main(
  @builtin(workgroup_id) workgroupId : vec3u,
  @builtin(local_invocation_id) localId : vec3u
) {
  let rowBy4 = workgroupId.x;
  if (rowBy4 >= (kRows / 4u)) {
    return;
  }

  let lane = localId.x;
  let colStart = lane * kColsPerInvocation;
  var laneSum : vec4<f32> = vec4<f32>(0.0);

  var i : u32 = 0u;
  loop {
    if (i >= kColsPerInvocation) {
      break;
    }
    let col = colStart + i;
    if (col >= kPackedCols) {
      break;
    }

    let v = vectorData[col];
    let base = 4u * (rowBy4 * kPackedCols + col);
    laneSum.x = laneSum.x + dot(matrixData[base + 0u], v);
    laneSum.y = laneSum.y + dot(matrixData[base + 1u], v);
    laneSum.z = laneSum.z + dot(matrixData[base + 2u], v);
    laneSum.w = laneSum.w + dot(matrixData[base + 3u], v);
    i = i + 1u;
  }

  partialSums[lane] = laneSum;
  workgroupBarrier();

  var stride : u32 = kWorkgroupSize / 2u;
  loop {
    if (stride == 0u) {
      break;
    }
    if (lane < stride) {
      partialSums[lane] = partialSums[lane] + partialSums[lane + stride];
    }
    workgroupBarrier();
    stride = stride / 2u;
  }

  if (lane == 0u) {
    outData[rowBy4] = partialSums[0];
  }
}
