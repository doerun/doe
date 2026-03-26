// Fused GEMV with inline Q4K dequantization.
// Matches Doppler matmul_q4k op pattern.

struct Uniforms {
    rows: u32,
    cols: u32,
    group_size: u32,
    _pad: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> quant_weights: array<u32>;
@group(0) @binding(2) var<storage, read> scales: array<f32>;
@group(0) @binding(3) var<storage, read> input_vec: array<f32>;
@group(0) @binding(4) var<storage, read_write> output: array<f32>;

var<workgroup> shared_partial: array<f32, 256>;

fn dequant_q4(packed: u32, idx: u32) -> f32 {
    let shift = (idx % 8u) * 4u;
    let nibble = (packed >> shift) & 0xFu;
    return f32(nibble) - 8.0;
}

@compute @workgroup_size(256)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let row = wid.x;
    let tid = lid.x;

    if (row >= u.rows) { return; }

    // each thread handles a chunk of the dot product
    var partial: f32 = 0.0;
    var col = tid;
    loop {
        if (col >= u.cols) { break; }

        let group_idx = col / u.group_size;
        let scale = scales[row * ((u.cols + u.group_size - 1u) / u.group_size) + group_idx];

        let packed_idx = (row * u.cols + col) / 8u;
        let w = dequant_q4(quant_weights[packed_idx], col) * scale;
        partial = partial + w * input_vec[col];

        col = col + 256u;
    }

    shared_partial[tid] = partial;
    workgroupBarrier();

    // tree reduction
    var stride: u32 = 128u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride) {
            shared_partial[tid] = shared_partial[tid] + shared_partial[tid + stride];
        }
        workgroupBarrier();
        stride = stride / 2u;
    }

    if (tid == 0u) {
        output[row] = shared_partial[0];
    }
}
