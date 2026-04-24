// Pinned WGSL snapshot for the first real-kernel TSIR fixture.
//
// Gemma-family production embedding-table gather, lifted from
// Doppler's `src/gpu/kernels/gather.wgsl`. At this shape the kernel is
// still an embedding lookup — the same compiler decision the
// bootstrap `gather.wgsl` snapshot exercises — but at Gemma 4 E2B
// manifest scale (see the companion `embed.notes.md` for dimensions).
//
// The goal of this fixture is NOT to introduce a new body op; the
// body is still `gather`. What differs from bootstrap is the target
// realization: per-PE memory budget at manifest scale forces
// pe_sliced output + fabric_streamed table instead of the bootstrap's
// pe_replicated-everywhere realization. See
// `embed.tsir-realization.wse3.json` for the target residency plan
// and `embed.notes.md` for the per-PE budget math.

override WORKGROUP_SIZE_MAIN: u32 = 256u;

struct Uniforms {
    num_tokens: u32,
    hidden_size: u32,
    vocab_size: u32,
    transpose: u32,
    index_offset: u32,
    input_hidden_size: u32,
    hidden_offset: u32,
    _pad0: u32,
    _pad1: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> indices: array<u32>;
@group(0) @binding(2) var<storage, read> embeddings: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(WORKGROUP_SIZE_MAIN, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let tid = gid.x;
    let total_elements = u.num_tokens * u.hidden_size;

    if (tid >= total_elements) {
        return;
    }

    let token_idx = tid / u.hidden_size;
    let dim_idx = tid % u.hidden_size;
    let token_id = indices[token_idx + u.index_offset];

    if (token_id >= u.vocab_size) {
        output[tid] = 0.0;
        return;
    }

    var embed_offset: u32;
    let source_dim = u.hidden_offset + dim_idx;
    if (u.transpose == 1u) {
        embed_offset = source_dim * u.vocab_size + token_id;
    } else {
        embed_offset = token_id * u.input_hidden_size + source_dim;
    }
    output[tid] = embeddings[embed_offset];
}
