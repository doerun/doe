// Embedding lookup — maps token IDs to embedding vectors.

struct Uniforms {
    seq_len: u32,
    embed_dim: u32,
    _pad0: u32,
    _pad1: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> token_ids: array<u32>;
@group(0) @binding(2) var<storage, read> embed_table: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    let seq_idx = gid.y;
    let dim_idx = gid.x;
    if (seq_idx >= u.seq_len) { return; }
    if (dim_idx >= u.embed_dim) { return; }

    let token = token_ids[seq_idx];
    output[seq_idx * u.embed_dim + dim_idx] = embed_table[token * u.embed_dim + dim_idx];
}
