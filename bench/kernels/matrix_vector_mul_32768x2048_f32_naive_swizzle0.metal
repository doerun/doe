#include <metal_stdlib>
using namespace metal;

constant uint kRows = 32768u;
constant uint kPackedCols = 512u;

[[max_total_threads_per_threadgroup(64)]]
kernel void main_kernel(
    device const float4* matrixData [[buffer(0)]],
    device const float4* vectorData [[buffer(1)]],
    device float4* outData [[buffer(2)]],
    uint gid [[thread_position_in_grid]])
{
    uint rowBy4 = gid;
    if (rowBy4 >= (kRows / 4u)) return;

    float4 sum = float4(0.0f);
    for (uint col = 0u; col < kPackedCols; col++) {
        float4 v = vectorData[col];
        sum.x += dot(matrixData[(4u * rowBy4 + 0u) * kPackedCols + col], v);
        sum.y += dot(matrixData[(4u * rowBy4 + 1u) * kPackedCols + col], v);
        sum.z += dot(matrixData[(4u * rowBy4 + 2u) * kPackedCols + col], v);
        sum.w += dot(matrixData[(4u * rowBy4 + 3u) * kPackedCols + col], v);
    }
    outData[rowBy4] = sum;
}
