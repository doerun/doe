// GEMV decode specialization for workloads where rows are even and cols are a
// multiple of four. This keeps the helper-call proof shape that lets Doe elide
// robustness clamps while reusing vector loads across the two output rows.

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

var<workgroup> partial0: array<f32, 64>;
var<workgroup> partial1: array<f32, 64>;

fn gemv_pair(row0: u32, row1: u32, lane: u32) -> vec2<f32> {
    let base0 = row0 * u.cols;
    let base1 = row1 * u.cols;
    let vec_cols = u.cols & ~3u;
    let lane_width = 64u;
    let vec_stride = lane_width * 4u;
    var c = lane * 4u;
    var acc0 = 0.0;
    var acc1 = 0.0;

    loop {
        if (c >= vec_cols) { break; }
        let v = vec4<f32>(
            vector[c],
            vector[c + 1u],
            vector[c + 2u],
            vector[c + 3u],
        );
        acc0 = acc0 + dot(
            vec4<f32>(
                matrix[base0 + c],
                matrix[base0 + c + 1u],
                matrix[base0 + c + 2u],
                matrix[base0 + c + 3u],
            ),
            v,
        );
        acc1 = acc1 + dot(
            vec4<f32>(
                matrix[base1 + c],
                matrix[base1 + c + 1u],
                matrix[base1 + c + 2u],
                matrix[base1 + c + 3u],
            ),
            v,
        );
        c = c + vec_stride;
    }

    return vec2<f32>(acc0, acc1);
}

@compute @workgroup_size(64)
fn main(
    @builtin(workgroup_id) workgroup_id: vec3u,
    @builtin(local_invocation_id) local_invocation_id: vec3u,
) {
    let row0 = workgroup_id.x * 2u;
    let row1 = row0 + 1u;
    if (row0 >= u.rows) { return; }
    if (row1 >= u.rows) { return; }
    let lane = local_invocation_id.x;
    let pair = gemv_pair(row0, row1, lane);
    partial0[lane] = pair.x;
    partial1[lane] = pair.y;
    workgroupBarrier();

    var stride = 32u;
    loop {
        if (stride == 0u) { break; }
        if (lane < stride) {
            partial0[lane] = partial0[lane] + partial0[lane + stride];
            partial1[lane] = partial1[lane] + partial1[lane + stride];
        }
        workgroupBarrier();
        stride = stride >> 1u;
    }

    if (lane == 0u) {
        output[row0] = partial0[0];
        output[row1] = partial1[0];
    }
}
