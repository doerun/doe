// Pinned WGSL snapshot for the bootstrap catalog.
// Minimal single-token RMSNorm. Not the production Doppler RMSNorm
// (which uses workgroup reductions, subgroup ops, optional residual
// fusion, f16/bf16 variants, and a variety of override constants);
// the snapshot here is the simplest arithmetic shape that exercises
// the same compiler decisions: elementwise square before reduction,
// scalar-tail arithmetic (divide, add eps, sqrt, reciprocal),
// elementwise multiply chain after reduction.

struct Uniforms {
    hidden_size: u32,
    eps: f32,
};

@group(0) @binding(0) var<storage, read> input: array<f32>;
@group(0) @binding(1) var<storage, read> weight: array<f32>;
@group(0) @binding(2) var<storage, read_write> output: array<f32>;
@group(0) @binding(3) var<uniform> u: Uniforms;

@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let d: u32 = gid.x;
    if (d >= u.hidden_size) {
        return;
    }

    // Sum of squares across hidden_size elements.
    var sum_sq: f32 = 0.0;
    for (var i: u32 = 0u; i < u.hidden_size; i = i + 1u) {
        let v = input[i];
        sum_sq = sum_sq + v * v;
    }

    // Scalar tail: mean, add eps, sqrt, reciprocal.
    let mean_sq = sum_sq / f32(u.hidden_size);
    let inv_rms = 1.0 / sqrt(mean_sq + u.eps);

    // Normalize and scale by per-element weight.
    output[d] = input[d] * inv_rms * weight[d];
}
