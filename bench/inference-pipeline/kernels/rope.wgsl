struct Uniforms {
    seq_len: u32,
    head_dim: u32,
    num_heads: u32,
    position_offset: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read_write> qk: array<f32>;
@group(0) @binding(2) var<storage, read> freq_cis: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    let half_dim = u.head_dim / 2u;
    let pair_idx = gid.x;
    let head_idx = gid.y;
    let seq_idx = gid.z;

    if (pair_idx >= half_dim) { return; }
    if (head_idx >= u.num_heads) { return; }
    if (seq_idx >= u.seq_len) { return; }

    let pos = seq_idx + u.position_offset;
    let base = (seq_idx * u.num_heads + head_idx) * u.head_dim;

    let x0 = qk[base + pair_idx];
    let x1 = qk[base + pair_idx + half_dim];

    let freq = pos * half_dim + pair_idx;
    let cos_v = freq_cis[freq * 2u];
    let sin_v = freq_cis[freq * 2u + 1u];

    qk[base + pair_idx] = x0 * cos_v - x1 * sin_v;
    qk[base + pair_idx + half_dim] = x0 * sin_v + x1 * cos_v;
}
