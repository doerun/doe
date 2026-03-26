struct Uniforms {
    seq_len: u32,
    head_dim: u32,
    num_heads: u32,
    position_offset: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read_write> q: array<f32>;
@group(0) @binding(2) var<storage, read> freq_cis: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    let half_dim = u.head_dim / 2u;
    let head_idx = gid.y;
    let pair_idx = gid.x;

    if (head_idx >= u.num_heads) { return; }
    if (pair_idx >= half_dim) { return; }

    let seq_idx = gid.z;
    if (seq_idx >= u.seq_len) { return; }

    let pos = seq_idx + u.position_offset;
    let base_idx = (seq_idx * u.num_heads + head_idx) * u.head_dim;

    let x0 = q[base_idx + pair_idx];
    let x1 = q[base_idx + pair_idx + half_dim];

    let freq_idx = pos * half_dim + pair_idx;
    let cos_val = freq_cis[freq_idx * 2u];
    let sin_val = freq_cis[freq_idx * 2u + 1u];

    q[base_idx + pair_idx] = x0 * cos_val - x1 * sin_val;
    q[base_idx + pair_idx + half_dim] = x0 * sin_val + x1 * cos_val;
}
