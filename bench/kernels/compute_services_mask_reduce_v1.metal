#include <metal_stdlib>
using namespace metal;

kernel void main_kernel(device uint *dst [[buffer(0)]],
                        uint3 gid [[thread_position_in_grid]]) {
    if (gid.x == 0 && gid.y == 0 && gid.z == 0) {
        dst[0] = 2;
    }
}
