// Q4K SUMMA smoke fixture for the fused-dequant wedge.
//
// Drives the classifier into `tiled_matmul_q4k_dequant_b` (struct
// storage + 2 workgroup tiles + barriers + loops + no QKV). Same shape
// as the Wedge 4 unit-test fixture; lifted out so it can be a real
// pinned WGSL file feeding doe-emit-csl.
//
// Logical operation:  C[m, n] = sum_k A[m, k] * dequantize(B_q4k)[n, k]
// PE program: 2-D tile + barrier loop. The classifier matches on
// structure, not on the inner expression — Wedge 4 routes this WGSL
// to the q4k SUMMA emitter.

struct Q4KBlock {
    d_dmin: u32,
    scales: array<u32, 3>,
    qs: array<u32, 32>,
}

@group(0) @binding(0) var<storage, read> a: array<f32>;
@group(0) @binding(1) var<storage, read> b_q4k: array<Q4KBlock>;
@group(0) @binding(2) var<storage, read_write> c: array<f32>;

var<workgroup> a_tile: array<f32, 256>;
var<workgroup> b_tile: array<f32, 256>;

@compute @workgroup_size(16, 16)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(global_invocation_id) gid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    var acc: f32 = 0.0;
    let tile_count: u32 = 4u;
    for (var t: u32 = 0u; t < tile_count; t = t + 1u) {
        let block_idx = t * 16u + lid.y;
        let block = b_q4k[block_idx];
        let lo: u32 = block.d_dmin & 0xFFFFu;
        let dq = f32(block.qs[lid.x] & 0xFu) * f32(lo);
        a_tile[lid.y * 16u + lid.x] = a[gid.y * 64u + t * 16u + lid.x];
        b_tile[lid.y * 16u + lid.x] = dq;
        workgroupBarrier();
        for (var k: u32 = 0u; k < 16u; k = k + 1u) {
            acc = acc + a_tile[lid.y * 16u + k] * b_tile[k * 16u + lid.x];
        }
        workgroupBarrier();
    }
    c[gid.y * 64u + gid.x] = acc;
}
