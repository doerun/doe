// Subgroup-accelerated GEMV: replaces the workgroup tree reduction with a
// subgroupAdd plus a single cross-subgroup merge. The original
// matmul_gemv_subgroup.wgsl is named "subgroup" but uses workgroup shared memory
// + tree reduction; this variant actually uses subgroupAdd. Functionally
// equivalent output, ~workgroup_size fewer shared-memory writes per row, and
// log2(workgroup_size / subgroup_size) instead of log2(workgroup_size) barriers.

enable subgroups;

struct Uniforms {
    rows: u32,
    cols: u32,
    _pad0: u32,
    _pad1: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> matrix: array<f32>;
@group(0) @binding(2) var<storage, read> vector: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

const WG_SIZE: u32 = 64u;
const MAX_SUBGROUPS: u32 = 8u;

var<workgroup> subgroup_partials: array<f32, MAX_SUBGROUPS>;

fn gemv_partial(row: u32, lane: u32) -> f32 {
    let base = row * u.cols;
    let vec_cols = u.cols & ~3u;
    let lane_width = WG_SIZE;
    let vec_stride = lane_width * 4u;
    var c = lane * 4u;
    var acc = 0.0;

    loop {
        if (c >= vec_cols) { break; }
        acc = acc + dot(
            vec4<f32>(
            matrix[base + c],
            matrix[base + c + 1u],
            matrix[base + c + 2u],
            matrix[base + c + 3u],
            ),
            vec4<f32>(
            vector[c],
            vector[c + 1u],
            vector[c + 2u],
            vector[c + 3u],
            ),
        );
        c = c + vec_stride;
    }

    c = vec_cols + lane;
    loop {
        if (c >= u.cols) { break; }
        acc = acc + matrix[base + c] * vector[c];
        c = c + lane_width;
    }
    return acc;
}

@compute @workgroup_size(64)
fn main_vec4(
    @builtin(workgroup_id) workgroup_id: vec3u,
    @builtin(local_invocation_id) local_invocation_id: vec3u,
    @builtin(subgroup_invocation_id) sid: u32,
    @builtin(subgroup_size) sg_size: u32,
) {
    let row = workgroup_id.x;
    if (row >= u.rows) { return; }
    let lane = local_invocation_id.x;

    let partial = gemv_partial(row, lane);
    let subgroup_sum = subgroupAdd(partial);
    let subgroup_id = lane / sg_size;
    if (sid == 0u) {
        subgroup_partials[subgroup_id] = subgroup_sum;
    }
    workgroupBarrier();

    if (lane == 0u) {
        let num_subgroups = WG_SIZE / sg_size;
        var total: f32 = 0.0;
        var k: u32 = 0u;
        loop {
            if (k >= num_subgroups) { break; }
            total = total + subgroup_partials[k];
            k = k + 1u;
        }
        output[row] = total;
    }
}

@compute @workgroup_size(64)
fn main_multicol(
    @builtin(workgroup_id) workgroup_id: vec3u,
    @builtin(local_invocation_id) local_invocation_id: vec3u,
    @builtin(subgroup_invocation_id) sid: u32,
    @builtin(subgroup_size) sg_size: u32,
) {
    let row = workgroup_id.x;
    if (row >= u.rows) { return; }
    let lane = local_invocation_id.x;

    let partial = gemv_partial(row, lane);
    let subgroup_sum = subgroupAdd(partial);
    let subgroup_id = lane / sg_size;
    if (sid == 0u) {
        subgroup_partials[subgroup_id] = subgroup_sum;
    }
    workgroupBarrier();

    if (lane == 0u) {
        let num_subgroups = WG_SIZE / sg_size;
        var total: f32 = 0.0;
        var k: u32 = 0u;
        loop {
            if (k >= num_subgroups) { break; }
            total = total + subgroup_partials[k];
            k = k + 1u;
        }
        output[row] = total;
    }
}
