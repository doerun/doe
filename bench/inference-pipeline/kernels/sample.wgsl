// Argmax sampling over logits vector.

struct Uniforms {
    vocab_size: u32,
    _pad0: u32,
    _pad1: u32,
    _pad2: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> logits: array<f32>;
@group(0) @binding(2) var<storage, read_write> output_token: array<u32>;

var<workgroup> shared_max_val: array<f32, 256>;
var<workgroup> shared_max_idx: array<u32, 256>;

@compute @workgroup_size(256)
fn main(@builtin(local_invocation_id) lid: vec3u) {
    let tid = lid.x;

    var best_val: f32 = -1e30;
    var best_idx: u32 = 0u;

    var i = tid;
    loop {
        if (i >= u.vocab_size) { break; }
        let v = logits[i];
        if (v > best_val) {
            best_val = v;
            best_idx = i;
        }
        i = i + 256u;
    }

    shared_max_val[tid] = best_val;
    shared_max_idx[tid] = best_idx;
    workgroupBarrier();

    var stride: u32 = 128u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride) {
            if (shared_max_val[tid + stride] > shared_max_val[tid]) {
                shared_max_val[tid] = shared_max_val[tid + stride];
                shared_max_idx[tid] = shared_max_idx[tid + stride];
            }
        }
        workgroupBarrier();
        stride = stride / 2u;
    }

    if (tid == 0u) {
        output_token[0] = shared_max_idx[0];
    }
}

@compute @workgroup_size(256)
fn sample_single_pass(@builtin(local_invocation_id) lid: vec3u) {
    let tid = lid.x;

    var best_val: f32 = -1e30;
    var best_idx: u32 = 0u;

    var i = tid;
    loop {
        if (i >= u.vocab_size) { break; }
        let v = logits[i];
        if (v > best_val) {
            best_val = v;
            best_idx = i;
        }
        i = i + 256u;
    }

    shared_max_val[tid] = best_val;
    shared_max_idx[tid] = best_idx;
    workgroupBarrier();

    var stride: u32 = 128u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride) {
            if (shared_max_val[tid + stride] > shared_max_val[tid]) {
                shared_max_val[tid] = shared_max_val[tid + stride];
                shared_max_idx[tid] = shared_max_idx[tid + stride];
            }
        }
        workgroupBarrier();
        stride = stride / 2u;
    }

    if (tid == 0u) {
        output_token[0] = shared_max_idx[0];
    }
}
