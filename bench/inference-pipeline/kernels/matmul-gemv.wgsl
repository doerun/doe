// GEMV for decode phase: output[row] = dot(matrix[row], vector)

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

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    let row = gid.x;
    if (row >= u.rows) { return; }

    let base = row * u.cols;
    var acc: f32 = 0.0;
    for (var c: u32 = 0u; c < u.cols; c = c + 1u) {
        acc = acc + matrix[base + c] * vector[c];
    }
    output[row] = acc;
}
