struct Uniforms {
    size: u32,
    eps: f32,
    _pad0: u32,
    _pad1: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> input: array<f32>;
@group(0) @binding(2) var<storage, read> gamma: array<f32>;
@group(0) @binding(3) var<storage, read> beta: array<f32>;
@group(0) @binding(4) var<storage, read_write> output: array<f32>;

var<workgroup> shared_val: array<f32, 256>;

@compute @workgroup_size(256)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let row_offset = wid.x * u.size;
    let tid = lid.x;

    // compute mean
    var partial_sum: f32 = 0.0;
    var i = tid;
    loop {
        if (i >= u.size) { break; }
        partial_sum = partial_sum + input[row_offset + i];
        i = i + 256u;
    }
    shared_val[tid] = partial_sum;
    workgroupBarrier();

    var stride: u32 = 128u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride) {
            shared_val[tid] = shared_val[tid] + shared_val[tid + stride];
        }
        workgroupBarrier();
        stride = stride / 2u;
    }
    let mean = shared_val[0] / f32(u.size);
    workgroupBarrier();

    // compute variance
    var partial_var: f32 = 0.0;
    i = tid;
    loop {
        if (i >= u.size) { break; }
        let diff = input[row_offset + i] - mean;
        partial_var = partial_var + diff * diff;
        i = i + 256u;
    }
    shared_val[tid] = partial_var;
    workgroupBarrier();

    stride = 128u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride) {
            shared_val[tid] = shared_val[tid] + shared_val[tid + stride];
        }
        workgroupBarrier();
        stride = stride / 2u;
    }
    let inv_std = 1.0 / sqrt(shared_val[0] / f32(u.size) + u.eps);
    workgroupBarrier();

    // normalize with affine
    i = tid;
    loop {
        if (i >= u.size) { break; }
        output[row_offset + i] = (input[row_offset + i] - mean) * inv_std * gamma[i] + beta[i];
        i = i + 256u;
    }
}
