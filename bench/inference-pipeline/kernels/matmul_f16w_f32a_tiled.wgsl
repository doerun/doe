// Doe-owned production-style stand-in for the tiled prefill path.
// This keeps the benchmark synthetic, but follows the production register-tiled
// compute shape much more closely than the scalar one-output-per-thread stand-in.

const TILE_M: u32 = 64u;
const TILE_N: u32 = 64u;
const TILE_K: u32 = 16u;
const THREAD_M: u32 = 4u;
const THREAD_N: u32 = 4u;
const WG_M: u32 = 16u;
const WG_N: u32 = 16u;

struct Uniforms {
    rows: u32,
    cols: u32,
    out_cols: u32,
    _pad0: u32,
}

@group(0) @binding(0) var<storage, read> activations: array<f32>;
@group(0) @binding(1) var<storage, read> weights_bt: array<f32>;
@group(0) @binding(2) var<storage, read_write> output: array<f32>;
@group(0) @binding(3) var<uniform> u: Uniforms;

var<workgroup> tile_a: array<f32, TILE_M * TILE_K>;
var<workgroup> tile_b: array<f32, TILE_N * TILE_K>;

@compute @workgroup_size(WG_N, WG_M, 1)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let tx = lid.x;
    let ty = lid.y;
    let tid = ty * WG_N + tx;

    let row_base = wid.y * TILE_M + ty * THREAD_M;
    let col_base = wid.x * TILE_N + tx * THREAD_N;

    var acc00: f32 = 0.0; var acc01: f32 = 0.0; var acc02: f32 = 0.0; var acc03: f32 = 0.0;
    var acc10: f32 = 0.0; var acc11: f32 = 0.0; var acc12: f32 = 0.0; var acc13: f32 = 0.0;
    var acc20: f32 = 0.0; var acc21: f32 = 0.0; var acc22: f32 = 0.0; var acc23: f32 = 0.0;
    var acc30: f32 = 0.0; var acc31: f32 = 0.0; var acc32: f32 = 0.0; var acc33: f32 = 0.0;

    let num_tiles = (u.cols + TILE_K - 1u) / TILE_K;
    for (var tile: u32 = 0u; tile < num_tiles; tile = tile + 1u) {
        let k_offset = tile * TILE_K;

        let load_base = tid * 4u;
        for (var i: u32 = 0u; i < 4u; i = i + 1u) {
            let elem_idx = load_base + i;
            let load_row = elem_idx / TILE_K;
            let load_col = elem_idx % TILE_K;

            let global_row = wid.y * TILE_M + load_row;
            let global_col = k_offset + load_col;
            if (global_row < u.rows && global_col < u.cols) {
                tile_a[elem_idx] = activations[global_row * u.cols + global_col];
            } else {
                tile_a[elem_idx] = 0.0;
            }

            let global_out_col = wid.x * TILE_N + load_row;
            if (global_out_col < u.out_cols && global_col < u.cols) {
                tile_b[elem_idx] = weights_bt[global_out_col * u.cols + global_col];
            } else {
                tile_b[elem_idx] = 0.0;
            }
        }

        workgroupBarrier();

        for (var k: u32 = 0u; k < TILE_K; k = k + 1u) {
            let a0 = tile_a[(ty * THREAD_M + 0u) * TILE_K + k];
            let a1 = tile_a[(ty * THREAD_M + 1u) * TILE_K + k];
            let a2 = tile_a[(ty * THREAD_M + 2u) * TILE_K + k];
            let a3 = tile_a[(ty * THREAD_M + 3u) * TILE_K + k];

            let b0 = tile_b[(tx * THREAD_N + 0u) * TILE_K + k];
            let b1 = tile_b[(tx * THREAD_N + 1u) * TILE_K + k];
            let b2 = tile_b[(tx * THREAD_N + 2u) * TILE_K + k];
            let b3 = tile_b[(tx * THREAD_N + 3u) * TILE_K + k];

            acc00 += a0 * b0; acc01 += a0 * b1; acc02 += a0 * b2; acc03 += a0 * b3;
            acc10 += a1 * b0; acc11 += a1 * b1; acc12 += a1 * b2; acc13 += a1 * b3;
            acc20 += a2 * b0; acc21 += a2 * b1; acc22 += a2 * b2; acc23 += a2 * b3;
            acc30 += a3 * b0; acc31 += a3 * b1; acc32 += a3 * b2; acc33 += a3 * b3;
        }

        workgroupBarrier();
    }

    if (row_base + 0u < u.rows && col_base + 0u < u.out_cols) { output[(row_base + 0u) * u.out_cols + col_base + 0u] = acc00; }
    if (row_base + 0u < u.rows && col_base + 1u < u.out_cols) { output[(row_base + 0u) * u.out_cols + col_base + 1u] = acc01; }
    if (row_base + 0u < u.rows && col_base + 2u < u.out_cols) { output[(row_base + 0u) * u.out_cols + col_base + 2u] = acc02; }
    if (row_base + 0u < u.rows && col_base + 3u < u.out_cols) { output[(row_base + 0u) * u.out_cols + col_base + 3u] = acc03; }
    if (row_base + 1u < u.rows && col_base + 0u < u.out_cols) { output[(row_base + 1u) * u.out_cols + col_base + 0u] = acc10; }
    if (row_base + 1u < u.rows && col_base + 1u < u.out_cols) { output[(row_base + 1u) * u.out_cols + col_base + 1u] = acc11; }
    if (row_base + 1u < u.rows && col_base + 2u < u.out_cols) { output[(row_base + 1u) * u.out_cols + col_base + 2u] = acc12; }
    if (row_base + 1u < u.rows && col_base + 3u < u.out_cols) { output[(row_base + 1u) * u.out_cols + col_base + 3u] = acc13; }
    if (row_base + 2u < u.rows && col_base + 0u < u.out_cols) { output[(row_base + 2u) * u.out_cols + col_base + 0u] = acc20; }
    if (row_base + 2u < u.rows && col_base + 1u < u.out_cols) { output[(row_base + 2u) * u.out_cols + col_base + 1u] = acc21; }
    if (row_base + 2u < u.rows && col_base + 2u < u.out_cols) { output[(row_base + 2u) * u.out_cols + col_base + 2u] = acc22; }
    if (row_base + 2u < u.rows && col_base + 3u < u.out_cols) { output[(row_base + 2u) * u.out_cols + col_base + 3u] = acc23; }
    if (row_base + 3u < u.rows && col_base + 0u < u.out_cols) { output[(row_base + 3u) * u.out_cols + col_base + 0u] = acc30; }
    if (row_base + 3u < u.rows && col_base + 1u < u.out_cols) { output[(row_base + 3u) * u.out_cols + col_base + 1u] = acc31; }
    if (row_base + 3u < u.rows && col_base + 2u < u.out_cols) { output[(row_base + 3u) * u.out_cols + col_base + 2u] = acc32; }
    if (row_base + 3u < u.rows && col_base + 3u < u.out_cols) { output[(row_base + 3u) * u.out_cols + col_base + 3u] = acc33; }
}
