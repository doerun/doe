// Single-subgroup GEMV for decode workloads whose input width is validated as a
// multiple of 4. One workgroup computes one output row.

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

const WG_SIZE: u32 = 32u;

fn gemv_partial(row: u32, lane: u32) -> f32 {
    let base = row * u.cols;
    let lane_width = WG_SIZE;
    let vec_stride = lane_width * 4u;
    var c = lane * 4u;
    var acc = 0.0;

    loop {
        if (c >= u.cols) { break; }
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

    return acc;
}

@compute @workgroup_size(32)
fn main_vec4(
    @builtin(workgroup_id) workgroup_id: vec3u,
    @builtin(local_invocation_id) local_invocation_id: vec3u,
    @builtin(subgroup_invocation_id) sid: u32,
) {
    let row = workgroup_id.x;
    if (row >= u.rows) { return; }

    let partial = gemv_partial(row, local_invocation_id.x);
    let total = subgroupAdd(partial);
    if (sid == 0u) {
        output[row] = total;
    }
}

@compute @workgroup_size(32)
fn main_multicol(
    @builtin(workgroup_id) workgroup_id: vec3u,
    @builtin(local_invocation_id) local_invocation_id: vec3u,
    @builtin(subgroup_invocation_id) sid: u32,
) {
    let row = workgroup_id.x;
    if (row >= u.rows) { return; }

    let partial = gemv_partial(row, local_invocation_id.x);
    let total = subgroupAdd(partial);
    if (sid == 0u) {
        output[row] = total;
    }
}
