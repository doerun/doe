#include <metal_stdlib>
using namespace metal;

[[max_total_threads_per_threadgroup(1)]]
kernel void main_kernel(uint3 gid [[thread_position_in_grid]])
{
    (void)gid;
}
