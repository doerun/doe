alias ElemT = f32;

const TILE_SIZE: u32 = 32u;
const WG_X: u32 = 8u;
const WG_Y: u32 = 8u;
const ROW_PER_THREAD: u32 = TILE_SIZE / WG_Y;
const COL_PER_THREAD: u32 = TILE_SIZE / WG_X;

struct Dims { M: u32, K: u32, N: u32, _pad: u32, }

@group(0) @binding(0) var<storage, read> a: array<ElemT>;
@group(0) @binding(1) var<storage, read> b: array<ElemT>;
@group(0) @binding(2) var<storage, read_write> c: array<ElemT>;
@group(0) @binding(3) var<uniform> dims: Dims;

var<workgroup> tile_a: array<ElemT, TILE_SIZE * TILE_SIZE>;
var<workgroup> tile_b: array<ElemT, TILE_SIZE * TILE_SIZE>;

fn read_a(row: u32, col: u32) -> ElemT {
    if (row < dims.M && col < dims.K) { return a[row * dims.K + col]; }
    return 0.0;
}

fn read_b(row: u32, col: u32) -> ElemT {
    if (row < dims.K && col < dims.N) { return b[row * dims.N + col]; }
    return 0.0;
}

@compute @workgroup_size(WG_X, WG_Y, 1)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(global_invocation_id) gid: vec3u,
) {
    let tile_row = lid.y * ROW_PER_THREAD;
    let tile_col = lid.x * COL_PER_THREAD;
    let global_row = gid.y * ROW_PER_THREAD;
    let global_col = gid.x * COL_PER_THREAD;

    var acc: array<ElemT, ROW_PER_THREAD * COL_PER_THREAD>;
    for (var i: u32 = 0u; i < ROW_PER_THREAD * COL_PER_THREAD; i = i + 1u) {
        acc[i] = 0.0;
    }

    let num_tiles = (dims.K + TILE_SIZE - 1u) / TILE_SIZE;
    let col_per_a = TILE_SIZE / WG_X;
    let tile_col_a = lid.x * col_per_a;
    let row_per_b = TILE_SIZE / WG_Y;
    let tile_row_b = lid.y * row_per_b;

    for (var t: u32 = 0u; t < num_tiles; t = t + 1u) {
        // load tile A
        for (var r: u32 = 0u; r < ROW_PER_THREAD; r = r + 1u) {
            for (var c2: u32 = 0u; c2 < col_per_a; c2 = c2 + 1u) {
                let lr = tile_row + r;
                let lc = tile_col_a + c2;
                tile_a[lr * TILE_SIZE + lc] = read_a(global_row + r, t * TILE_SIZE + lc);
            }
        }
        // load tile B
        for (var r2: u32 = 0u; r2 < row_per_b; r2 = r2 + 1u) {
            for (var c3: u32 = 0u; c3 < COL_PER_THREAD; c3 = c3 + 1u) {
                let lr2 = tile_row_b + r2;
                let lc2 = tile_col + c3;
                tile_b[lr2 * TILE_SIZE + lc2] = read_b(t * TILE_SIZE + lr2, global_col + c3);
            }
        }
        workgroupBarrier();

        // accumulate
        for (var k: u32 = 0u; k < TILE_SIZE; k = k + 1u) {
            for (var r3: u32 = 0u; r3 < ROW_PER_THREAD; r3 = r3 + 1u) {
                let a_val = tile_a[(tile_row + r3) * TILE_SIZE + k];
                for (var c4: u32 = 0u; c4 < COL_PER_THREAD; c4 = c4 + 1u) {
                    let idx = r3 * COL_PER_THREAD + c4;
                    acc[idx] = acc[idx] + a_val * tile_b[k * TILE_SIZE + tile_col + c4];
                }
            }
        }
        workgroupBarrier();
    }

    // write output
    for (var r4: u32 = 0u; r4 < ROW_PER_THREAD; r4 = r4 + 1u) {
        for (var c5: u32 = 0u; c5 < COL_PER_THREAD; c5 = c5 + 1u) {
            let out_row = global_row + r4;
            let out_col = global_col + c5;
            if (out_row < dims.M && out_col < dims.N) {
                c[out_row * dims.N + out_col] = acc[r4 * COL_PER_THREAD + c5];
            }
        }
    }
}
