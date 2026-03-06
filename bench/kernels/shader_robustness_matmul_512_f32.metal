#include <metal_stdlib>
using namespace metal;

constant uint K_TILE_SIZE = 32u;
constant uint K_WORKGROUP_SIZE_X = 8u;
constant uint K_WORKGROUP_SIZE_Y = 8u;
constant uint K_DIM_A_OUTER = 512u;
constant uint K_DIM_INNER = 512u;
constant uint K_DIM_B_OUTER = 512u;
constant uint ROW_PER_THREAD = K_TILE_SIZE / K_WORKGROUP_SIZE_Y;
constant uint COL_PER_THREAD = K_TILE_SIZE / K_WORKGROUP_SIZE_X;
constant uint NUM_TILES = (K_DIM_INNER - 1u) / K_TILE_SIZE + 1u;

static float mm_read_a(device const float* mat, uint row, uint col) {
    return mat[row * K_DIM_INNER + col];
}

static float mm_read_b(device const float* mat, uint row, uint col) {
    return mat[row * K_DIM_B_OUTER + col];
}

[[max_total_threads_per_threadgroup(64)]]
kernel void main_kernel(
    device const float* first_matrix [[buffer(0)]],
    device const float* second_matrix [[buffer(1)]],
    device float* result_matrix [[buffer(2)]],
    uint2 lid [[thread_position_in_threadgroup]],
    uint2 gid [[thread_position_in_grid]])
{
    threadgroup float mm_a_sub[1024];
    threadgroup float mm_b_sub[1024];

    uint tile_row = lid.y * ROW_PER_THREAD;
    uint tile_col = lid.x * COL_PER_THREAD;
    uint global_row = gid.y * ROW_PER_THREAD;
    uint global_col = gid.x * COL_PER_THREAD;

    float acc[ROW_PER_THREAD * COL_PER_THREAD];
    for (uint i = 0u; i < ROW_PER_THREAD * COL_PER_THREAD; i++) { acc[i] = 0.0f; }

    uint col_per_thread_a = K_TILE_SIZE / K_WORKGROUP_SIZE_X;
    uint tile_col_a = lid.x * col_per_thread_a;
    uint row_per_thread_b = K_TILE_SIZE / K_WORKGROUP_SIZE_Y;
    uint tile_row_b = lid.y * row_per_thread_b;

    for (uint t = 0u; t < NUM_TILES; t++) {
        for (uint ir = 0u; ir < ROW_PER_THREAD; ir++) {
            for (uint ic = 0u; ic < col_per_thread_a; ic++) {
                uint in_row = tile_row + ir;
                uint in_col = tile_col_a + ic;
                mm_a_sub[in_row * K_TILE_SIZE + in_col] =
                    mm_read_a(first_matrix, global_row + ir, t * K_TILE_SIZE + in_col);
            }
        }
        for (uint ir = 0u; ir < row_per_thread_b; ir++) {
            for (uint ic = 0u; ic < COL_PER_THREAD; ic++) {
                uint in_row = tile_row_b + ir;
                uint in_col = tile_col + ic;
                mm_b_sub[in_row * K_TILE_SIZE + in_col] =
                    mm_read_b(second_matrix, t * K_TILE_SIZE + in_row, global_col + ic);
            }
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);

        for (uint k = 0u; k < K_TILE_SIZE; k++) {
            float b_cached[COL_PER_THREAD];
            for (uint inner = 0u; inner < COL_PER_THREAD; inner++) {
                b_cached[inner] = mm_b_sub[k * K_TILE_SIZE + tile_col + inner];
            }
            for (uint ir = 0u; ir < ROW_PER_THREAD; ir++) {
                float a_val = mm_a_sub[(tile_row + ir) * K_TILE_SIZE + k];
                for (uint ic = 0u; ic < COL_PER_THREAD; ic++) {
                    acc[ir * COL_PER_THREAD + ic] += a_val * b_cached[ic];
                }
            }
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
    }

    for (uint ir = 0u; ir < ROW_PER_THREAD; ir++) {
        for (uint ic = 0u; ic < COL_PER_THREAD; ic++) {
            uint row = global_row + ir;
            uint col = global_col + ic;
            result_matrix[col + row * K_DIM_B_OUTER] = acc[ir * COL_PER_THREAD + ic];
        }
    }
}
