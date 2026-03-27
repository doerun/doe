// Doe-owned production-style stand-in for the small prefill attention path.

struct Uniforms {
    seq_len: u32,
    head_dim: u32,
    num_heads: u32,
    scale_bits: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> q: array<f32>;
@group(0) @binding(2) var<storage, read> k: array<f32>;
@group(0) @binding(3) var<storage, read> v: array<f32>;
@group(0) @binding(4) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(64)
fn main(
    @builtin(global_invocation_id) gid: vec3u,
) {
    let dim = gid.x;
    let token = gid.y;
    let head = gid.z;
    if (token >= u.seq_len || head >= u.num_heads || dim >= u.head_dim) { return; }

    let token_stride = u.num_heads * u.head_dim;
    let head_offset = head * u.head_dim;
    let q_index = token * token_stride + head_offset + dim;
    let scale = bitcast<f32>(u.scale_bits);

    var weighted_sum: f32 = 0.0;
    var weight_acc: f32 = 0.0;
    for (var past: u32 = 0u; past <= token; past = past + 1u) {
        var score: f32 = 0.0;
        let past_base = past * token_stride + head_offset;
        let q_base = token * token_stride + head_offset;
        for (var inner: u32 = 0u; inner < u.head_dim; inner = inner + 1u) {
            score = score + q[q_base + inner] * k[past_base + inner];
        }
        let weight = max(score * scale, 0.0);
        weighted_sum = weighted_sum + weight * v[past_base + dim];
        weight_acc = weight_acc + weight;
    }

    var denom = 1.0;
    if (weight_acc > 0.0) {
        denom = weight_acc;
    }
    output[q_index] = weighted_sum / denom;
}
