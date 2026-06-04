// GEMV decode specialization for workloads where rows and cols are multiples of
// four. One workgroup computes four rows and reuses each vector vec4 load.

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
var<workgroup> partial2: array<f32, 64>;
var<workgroup> partial3: array<f32, 64>;

@compute @workgroup_size(64)
fn main(
    @builtin(workgroup_id) workgroup_id: vec3u,
    @builtin(local_invocation_id) local_invocation_id: vec3u,
) {
    let row0 = workgroup_id.x * 4u;
    let row1 = row0 + 1u;
    let row2 = row0 + 2u;
    let row3 = row0 + 3u;
    let lane = local_invocation_id.x;
    let lane_width = 64u;
    let vec_stride = lane_width * 4u;
    let base0 = row0 * u.cols;
    let base1 = row1 * u.cols;
    let base2 = row2 * u.cols;
    let base3 = row3 * u.cols;
    var acc0 = 0.0;
    var acc1 = 0.0;
    var acc2 = 0.0;
    var acc3 = 0.0;
    var c = lane * 4u;

    loop {
        if (c >= u.cols) { break; }
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
        acc2 = acc2 + dot(
            vec4<f32>(
                matrix[base2 + c],
                matrix[base2 + c + 1u],
                matrix[base2 + c + 2u],
                matrix[base2 + c + 3u],
            ),
            v,
        );
        acc3 = acc3 + dot(
            vec4<f32>(
                matrix[base3 + c],
                matrix[base3 + c + 1u],
                matrix[base3 + c + 2u],
                matrix[base3 + c + 3u],
            ),
            v,
        );
        c = c + vec_stride;
    }

    partial0[lane] = acc0;
    partial1[lane] = acc1;
    partial2[lane] = acc2;
    partial3[lane] = acc3;
    workgroupBarrier();

    var stride = 32u;
    loop {
        if (stride == 0u) { break; }
        if (lane < stride) {
            partial0[lane] = partial0[lane] + partial0[lane + stride];
            partial1[lane] = partial1[lane] + partial1[lane + stride];
            partial2[lane] = partial2[lane] + partial2[lane + stride];
            partial3[lane] = partial3[lane] + partial3[lane + stride];
        }
        workgroupBarrier();
        stride = stride >> 1u;
    }

    if (lane == 0u) {
        output[row0] = partial0[0];
        output[row1] = partial1[0];
        output[row2] = partial2[0];
        output[row3] = partial3[0];
    }
}
