// Pinned WGSL snapshot for the bootstrap catalog.
// Minimal embedding-table gather. Not the production Doppler embed
// kernel (which handles large vocab sizes, q4k-quantized tables,
// chunked streaming, and multi-token prompts); the snapshot here is
// the simplest shape that exercises the same compiler decision:
// indirect indexed addressing, where one buffer's values are indices
// into another buffer.
//
// output[t, h] = table[indices[t], h]

struct Uniforms {
    num_tokens: u32,
    hidden: u32,
    vocab: u32,
};

@group(0) @binding(0) var<storage, read> indices: array<u32>;
@group(0) @binding(1) var<storage, read> table: array<f32>;
@group(0) @binding(2) var<storage, read_write> output: array<f32>;
@group(0) @binding(3) var<uniform> u: Uniforms;

@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let t: u32 = gid.y;
    let h: u32 = gid.x;
    if (t >= u.num_tokens) {
        return;
    }
    if (h >= u.hidden) {
        return;
    }

    // Indirect lookup: read one u32 index from `indices`, use it as
    // the row index into `table`.
    let row: u32 = indices[t];
    // Bounds-guard the lookup against a rogue index.
    if (row >= u.vocab) {
        output[t * u.hidden + h] = 0.0;
        return;
    }

    output[t * u.hidden + h] = table[row * u.hidden + h];
}
