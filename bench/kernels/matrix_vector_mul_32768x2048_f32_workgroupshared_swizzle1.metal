#include <metal_stdlib>
using namespace metal;

constant uint kRows = 32768u;
constant uint kPackedCols = 512u;
constant uint kWorkgroupSize = 64u;
constant uint kColsPerInvocation = (kPackedCols + kWorkgroupSize - 1u) / kWorkgroupSize;

kernel void main_kernel(
    device const float4* matrixData [[buffer(0)]],
    device const float4* vectorData [[buffer(1)]],
    device float4* outData [[buffer(2)]],
    uint workgroupId [[threadgroup_position_in_grid]],
    uint lane [[thread_position_in_threadgroup]])
{
    threadgroup float4 partialSums[64];

    uint rowBy4 = workgroupId;
    if (rowBy4 >= (kRows / 4u)) return;

    uint colStart = lane * kColsPerInvocation;
    float4 laneSum = float4(0.0f);

    for (uint i = 0u; i < kColsPerInvocation; i++) {
        uint col = colStart + i;
        if (col >= kPackedCols) break;
        float4 v = vectorData[col];
        uint base = 4u * (rowBy4 * kPackedCols + col);
        laneSum.x += dot(matrixData[base + 0u], v);
        laneSum.y += dot(matrixData[base + 1u], v);
        laneSum.z += dot(matrixData[base + 2u], v);
        laneSum.w += dot(matrixData[base + 3u], v);
    }

    partialSums[lane] = laneSum;
    threadgroup_barrier(mem_flags::mem_threadgroup);

    for (uint stride = kWorkgroupSize / 2u; stride > 0u; stride >>= 1u) {
        if (lane < stride) {
            partialSums[lane] += partialSums[lane + stride];
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
    }

    if (lane == 0u) {
        outData[rowBy4] = partialSums[0];
    }
}
