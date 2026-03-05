#include <metal_stdlib>
using namespace metal;

constant uint K_WORKGROUP_SIZE = 256u;
constant uint K_WORKGROUP_ARRAY_SIZE = 2048u;
constant uint K_LOOP_LENGTH = K_WORKGROUP_ARRAY_SIZE / K_WORKGROUP_SIZE;

kernel void main_kernel(
    device float* dst [[buffer(0)]],
    uint lid [[thread_position_in_threadgroup]])
{
    threadgroup float wg[2048];

    for (uint k = 0u; k < K_LOOP_LENGTH; k++) {
        uint index = K_LOOP_LENGTH * lid + k;
        dst[index] = wg[index];
    }
}
