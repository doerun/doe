#include <metal_stdlib>
using namespace metal;

kernel void main_kernel(uint gid [[thread_position_in_grid]])
{
    float x = float(gid + 1u);
    float y = 0.0f;
    for (uint i = 0u; i < 4096u; i++) {
        x = fract(sin(x * 1.6180339f + float(i)) * 43758.5453f);
        y = y + x;
    }
    if (y < -1.0f) {
        x = y;
    }
    (void)x;
}
