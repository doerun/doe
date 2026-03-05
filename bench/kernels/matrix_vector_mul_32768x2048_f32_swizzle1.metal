#include <metal_stdlib>
using namespace metal;

constant uint kRows = 32768u;
constant uint kPackedCols = 512u;

kernel void main_kernel(
    device const float4* matrixData [[buffer(0)]],
    device const float4* vectorData [[buffer(1)]],
    device float4* outData [[buffer(2)]],
    uint gid [[thread_position_in_grid]])
{
    if (gid >= (kRows / 4u)) return;

    float4 sum = float4(0.0f);
    for (uint col = 0u; col < kPackedCols; col++) {
        float4 v = vectorData[col];
        uint base = 4u * (gid * kPackedCols + col);
        sum.x += dot(matrixData[base + 0u], v);
        sum.y += dot(matrixData[base + 1u], v);
        sum.z += dot(matrixData[base + 2u], v);
        sum.w += dot(matrixData[base + 3u], v);
    }
    outData[gid] = sum;
}
