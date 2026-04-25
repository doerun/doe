// Pinned WGSL snapshot for the bootstrap catalog.
// Intentionally minimal so the TSIR hand-sketch stays small.
// This is not the production Doppler fused-GEMV path; that lives in
// `../../../../doppler/src/gpu/kernels/` and uses Q4K weights with
// subgroup reductions and checkerboard PE distribution. The snapshot
// here is the simplest shape that exercises the same compiler
// decisions: 2-D matrix × 1-D vector → 1-D output, fused
// multiply-then-sum per output row.

struct Uniforms {
    M: u32,
    K: u32,
};

@group(0) @binding(0) var<storage, read> W: array<f32>;
@group(0) @binding(1) var<storage, read> x: array<f32>;
@group(0) @binding(2) var<storage, read_write> y: array<f32>;
@group(0) @binding(3) var<uniform> u: Uniforms;

@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i: u32 = gid.x;
    if (i >= u.M) {
        return;
    }
    var acc: f32 = 0.0;
    for (var k: u32 = 0u; k < u.K; k = k + 1u) {
        acc = acc + W[i * u.K + k] * x[k];
    }
    y[i] = acc;
}
