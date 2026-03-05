#include <metal_stdlib>
using namespace metal;

constant uint kRows = 32768u;
constant uint kCols = 2048u;

kernel void main_kernel(
    device const float* matrixData [[buffer(0)]],
    device const float* vectorData [[buffer(1)]],
    device float* outData [[buffer(2)]],
    uint gid [[thread_position_in_grid]])
{
    if (gid >= kRows) return;

    uint base = gid * kCols;
    float accum = 0.0f;
    for (uint col = 0u; col < kCols; col++) {
        accum += matrixData[base + col] * vectorData[col];
    }
    outData[gid] = accum;
}
