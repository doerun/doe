struct Uniforms {
    size: u32,
    _pad0: u32,
    _pad1: u32,
    _pad2: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> input: array<f32>;
@group(0) @binding(2) var<storage, read_write> output: array<f32>;

var<workgroup> shared_max: array<f32, 256>;
var<workgroup> shared_sum: array<f32, 256>;

@compute @workgroup_size(256)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let row_offset = wid.x * u.size;
    let tid = lid.x;

    // find max
    var local_max: f32 = -1e30;
    var i = tid;
    loop {
        if (i >= u.size) { break; }
        local_max = max(local_max, input[row_offset + i]);
        i = i + 256u;
    }
    shared_max[tid] = local_max;
    workgroupBarrier();

    var stride: u32 = 128u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride) {
            shared_max[tid] = max(shared_max[tid], shared_max[tid + stride]);
        }
        workgroupBarrier();
        stride = stride / 2u;
    }
    let row_max = shared_max[0];
    workgroupBarrier();

    // exp and sum
    var local_sum: f32 = 0.0;
    i = tid;
    loop {
        if (i >= u.size) { break; }
        let e = exp(clamp(input[row_offset + i] - row_max, -30.0, 30.0));
        output[row_offset + i] = e;
        local_sum = local_sum + e;
        i = i + 256u;
    }
    shared_sum[tid] = local_sum;
    workgroupBarrier();

    stride = 128u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride) {
            shared_sum[tid] = shared_sum[tid] + shared_sum[tid + stride];
        }
        workgroupBarrier();
        stride = stride / 2u;
    }
    let total = shared_sum[0];
    workgroupBarrier();

    // normalize
    i = tid;
    loop {
        if (i >= u.size) { break; }
        output[row_offset + i] = output[row_offset + i] / total;
        i = i + 256u;
    }
}
