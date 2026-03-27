// Doe-owned production-style stand-in for the decode GEMV and multicol LM-head path.

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
fn main_vec4(@builtin(global_invocation_id) gid: vec3u) {
    let row = gid.x;
    if (row >= u.rows) { return; }
    let base = row * u.cols;
    var acc: f32 = 0.0;
    for (var col: u32 = 0u; col < u.cols; col = col + 1u) {
        acc = acc + matrix[base + col] * vector[col];
    }
    output[row] = acc;
}

@compute @workgroup_size(64)
fn main_multicol(@builtin(global_invocation_id) gid: vec3u) {
    let row = gid.x;
    if (row >= u.rows) { return; }
    let base = row * u.cols;
    var acc: f32 = 0.0;
    for (var col: u32 = 0u; col < u.cols; col = col + 1u) {
        acc = acc + matrix[base + col] * vector[col];
    }
    output[row] = acc;
}
