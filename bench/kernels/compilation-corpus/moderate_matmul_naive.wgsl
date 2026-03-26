struct Dims { M: u32, N: u32, K: u32, }

@group(0) @binding(0) var<storage, read> a: array<f32>;
@group(0) @binding(1) var<storage, read> b: array<f32>;
@group(0) @binding(2) var<storage, read_write> c: array<f32>;
@group(0) @binding(3) var<uniform> dims: Dims;

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    let row = gid.y;
    let col = gid.x;
    if (row >= dims.M) { return; }
    if (col >= dims.N) { return; }

    var acc: f32 = 0.0;
    for (var k: u32 = 0u; k < dims.K; k = k + 1u) {
        acc = acc + a[row * dims.K + k] * b[k * dims.N + col];
    }
    c[row * dims.N + col] = acc;
}
