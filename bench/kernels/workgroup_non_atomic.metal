#include <metal_stdlib>
using namespace metal;

constant uint kWorkgroupSize = 256u;

kernel void main_kernel(
    device uint* outVal [[buffer(0)]],
    uint lid [[thread_position_in_threadgroup]],
    uint gid [[thread_position_in_grid]])
{
    threadgroup uint wg[256];

    uint accum = outVal[gid];
    wg[lid] = accum + gid;
    threadgroup_barrier(mem_flags::mem_threadgroup);

    for (uint i = 0u; i < kWorkgroupSize; i++) {
        accum = wg[(i + accum) % kWorkgroupSize];
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    outVal[gid] = accum;
}
