// Tiled matmul for prefill phase: C = A * B

alias ElemT = f32;
const TILE: u32 = 16u;

struct Dims { M: u32, K: u32, N: u32, _pad: u32, }

@group(0) @binding(0) var<storage, read> a: array<ElemT>;
@group(0) @binding(1) var<storage, read> b: array<ElemT>;
@group(0) @binding(2) var<storage, read_write> c: array<ElemT>;
@group(0) @binding(3) var<uniform> dims: Dims;

var<workgroup> tile_a: array<ElemT, TILE * TILE>;
var<workgroup> tile_b: array<ElemT, TILE * TILE>;

@compute @workgroup_size(TILE, TILE, 1)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let row = wid.y * TILE + lid.y;
    let col = wid.x * TILE + lid.x;
    let num_tiles = (dims.K + TILE - 1u) / TILE;

    var acc: ElemT = 0.0;

    for (var t: u32 = 0u; t < num_tiles; t = t + 1u) {
        let a_col = t * TILE + lid.x;
        let b_row = t * TILE + lid.y;

        if (row < dims.M && a_col < dims.K) {
            tile_a[lid.y * TILE + lid.x] = a[row * dims.K + a_col];
        } else {
            tile_a[lid.y * TILE + lid.x] = 0.0;
        }

        if (b_row < dims.K && col < dims.N) {
            tile_b[lid.y * TILE + lid.x] = b[b_row * dims.N + col];
        } else {
            tile_b[lid.y * TILE + lid.x] = 0.0;
        }

        workgroupBarrier();

        for (var k: u32 = 0u; k < TILE; k = k + 1u) {
            acc = acc + tile_a[lid.y * TILE + k] * tile_b[k * TILE + lid.x];
        }

        workgroupBarrier();
    }

    if (row < dims.M && col < dims.N) {
        c[row * dims.N + col] = acc;
    }
}
