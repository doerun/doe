// Doe-owned production-style stand-in for the decode attention path with past+current KV inputs.

struct Uniforms {
    num_heads: u32,
    head_dim: u32,
    past_tokens: u32,
    scale_bits: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> q: array<f32>;
@group(0) @binding(2) var<storage, read> current_k: array<f32>;
@group(0) @binding(3) var<storage, read> current_v: array<f32>;
@group(0) @binding(4) var<storage, read> past_k: array<f32>;
@group(0) @binding(5) var<storage, read> past_v: array<f32>;
@group(0) @binding(6) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    let dim = gid.x;
    let head = gid.y;
    if (head >= u.num_heads || dim >= u.head_dim) { return; }

    let head_base = head * u.head_dim;
    let scale = bitcast<f32>(u.scale_bits);
    var weighted_sum: f32 = 0.0;
    var weight_acc: f32 = 0.0;

    for (var token: u32 = 0u; token < u.past_tokens; token = token + 1u) {
        let token_base = token * u.num_heads * u.head_dim + head_base;
        var score: f32 = 0.0;
        for (var inner: u32 = 0u; inner < u.head_dim; inner = inner + 1u) {
            score = score + q[head_base + inner] * past_k[token_base + inner];
        }
        let weight = max(score * scale, 0.0);
        weighted_sum = weighted_sum + weight * past_v[token_base + dim];
        weight_acc = weight_acc + weight;
    }

    var current_score: f32 = 0.0;
    for (var inner: u32 = 0u; inner < u.head_dim; inner = inner + 1u) {
        current_score = current_score + q[head_base + inner] * current_k[head_base + inner];
    }
    let current_weight = max(current_score * scale, 0.0);
    weighted_sum = weighted_sum + current_weight * current_v[head_base + dim];
    weight_acc = weight_acc + current_weight;

    var denom = 1.0;
    if (weight_acc > 0.0) {
        denom = weight_acc;
    }
    output[head_base + dim] = weighted_sum / denom;
}
