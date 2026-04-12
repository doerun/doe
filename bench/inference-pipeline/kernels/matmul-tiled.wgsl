// Tiled matmul for prefill phase: C = A * B
//
// Keep the same 16x16 output tile contract as the generated plans, but cut
// the workgroup down to 64 threads and let each thread accumulate a 2x2
// register tile. This preserves the row-major A[K] * B[N] semantics while
// reducing barrier and scheduler pressure on Vulkan.

alias ElemT = f32;

const TILE_M: u32 = 16u;
const TILE_N: u32 = 16u;
const TILE_K: u32 = 16u;
const TILE_K_VECS: u32 = TILE_K / 4u;
const WG_X: u32 = 8u;
const WG_Y: u32 = 8u;
const THREAD_TILE_M: u32 = 2u;
const THREAD_TILE_N: u32 = 2u;

struct Dims { M: u32, K: u32, N: u32, _pad: u32, }

@group(0) @binding(0) var<storage, read> a: array<ElemT>;
@group(0) @binding(1) var<storage, read> b: array<ElemT>;
@group(0) @binding(2) var<storage, read_write> c: array<ElemT>;
@group(0) @binding(3) var<uniform> dims: Dims;

var<workgroup> tile_a: array<vec4<ElemT>, TILE_M * TILE_K_VECS>;
var<workgroup> tile_b: array<vec4<ElemT>, TILE_N * TILE_K_VECS>;

fn load_a(tile_row: u32, tile_col: u32, k_base: u32, row_base: u32) -> ElemT {
    let global_row = row_base + tile_row;
    let global_col = k_base + tile_col;
    if (global_row < dims.M && global_col < dims.K) {
        return a[global_row * dims.K + global_col];
    }
    return 0.0;
}

fn load_b(tile_row: u32, tile_col: u32, k_base: u32, col_base: u32) -> ElemT {
    let global_row = k_base + tile_row;
    let global_col = col_base + tile_col;
    if (global_row < dims.K && global_col < dims.N) {
        return b[global_row * dims.N + global_col];
    }
    return 0.0;
}

fn load_a_vec4(tile_row: u32, k_vec: u32, k_base: u32, row_base: u32) -> vec4<ElemT> {
    let tile_col = k_vec * 4u;
    return vec4<ElemT>(
        load_a(tile_row, tile_col + 0u, k_base, row_base),
        load_a(tile_row, tile_col + 1u, k_base, row_base),
        load_a(tile_row, tile_col + 2u, k_base, row_base),
        load_a(tile_row, tile_col + 3u, k_base, row_base),
    );
}

fn load_b_vec4(k_vec: u32, tile_col: u32, k_base: u32, col_base: u32) -> vec4<ElemT> {
    let tile_row = k_vec * 4u;
    return vec4<ElemT>(
        load_b(tile_row + 0u, tile_col, k_base, col_base),
        load_b(tile_row + 1u, tile_col, k_base, col_base),
        load_b(tile_row + 2u, tile_col, k_base, col_base),
        load_b(tile_row + 3u, tile_col, k_base, col_base),
    );
}

@compute @workgroup_size(WG_X, WG_Y, 1)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let lane = lid.y * WG_X + lid.x;
    let row_base = wid.y * TILE_M;
    let col_base = wid.x * TILE_N;
    let out_row0 = row_base + lid.y * THREAD_TILE_M;
    let out_col0 = col_base + lid.x * THREAD_TILE_N;
    let num_tiles = (dims.K + TILE_K - 1u) / TILE_K;

    var acc00: ElemT = 0.0;
    var acc01: ElemT = 0.0;
    var acc10: ElemT = 0.0;
    var acc11: ElemT = 0.0;

    for (var tile: u32 = 0u; tile < num_tiles; tile = tile + 1u) {
        let k_base = tile * TILE_K;
        let a_row = lane / TILE_K_VECS;
        let a_k_vec = lane % TILE_K_VECS;
        tile_a[a_row * TILE_K_VECS + a_k_vec] = load_a_vec4(a_row, a_k_vec, k_base, row_base);

        let b_col = lane / TILE_K_VECS;
        let b_k_vec = lane % TILE_K_VECS;
        tile_b[b_col * TILE_K_VECS + b_k_vec] = load_b_vec4(b_k_vec, b_col, k_base, col_base);

        workgroupBarrier();

        for (var k_vec: u32 = 0u; k_vec < TILE_K_VECS; k_vec = k_vec + 1u) {
            let a_row0 = tile_a[(lid.y * THREAD_TILE_M + 0u) * TILE_K_VECS + k_vec];
            let a_row1 = tile_a[(lid.y * THREAD_TILE_M + 1u) * TILE_K_VECS + k_vec];
            let b_col0 = tile_b[(lid.x * THREAD_TILE_N + 0u) * TILE_K_VECS + k_vec];
            let b_col1 = tile_b[(lid.x * THREAD_TILE_N + 1u) * TILE_K_VECS + k_vec];

            acc00 += dot(a_row0, b_col0);
            acc01 += dot(a_row0, b_col1);
            acc10 += dot(a_row1, b_col0);
            acc11 += dot(a_row1, b_col1);
        }

        workgroupBarrier();
    }

    if (out_row0 + 0u < dims.M && out_col0 + 0u < dims.N) {
        c[(out_row0 + 0u) * dims.N + out_col0 + 0u] = acc00;
    }
    if (out_row0 + 0u < dims.M && out_col0 + 1u < dims.N) {
        c[(out_row0 + 0u) * dims.N + out_col0 + 1u] = acc01;
    }
    if (out_row0 + 1u < dims.M && out_col0 + 0u < dims.N) {
        c[(out_row0 + 1u) * dims.N + out_col0 + 0u] = acc10;
    }
    if (out_row0 + 1u < dims.M && out_col0 + 1u < dims.N) {
        c[(out_row0 + 1u) * dims.N + out_col0 + 1u] = acc11;
    }
}
