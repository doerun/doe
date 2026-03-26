struct Uniforms {
    size: u32,
    eps: f32,
    _pad0: u32,
    _pad1: u32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> input: array<f32>;
@group(0) @binding(2) var<storage, read> weight: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

var<workgroup> shared_sum: array<f32, 256>;

@compute @workgroup_size(256)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let row_offset = wid.x * u.size;
    let tid = lid.x;

    var partial: f32 = 0.0;
    var i = tid;
    loop {
        if (i >= u.size) { break; }
        let v = input[row_offset + i];
        partial = partial + v * v;
        i = i + 256u;
    }
    shared_sum[tid] = partial;
    workgroupBarrier();

    var stride: u32 = 128u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride) {
            shared_sum[tid] = shared_sum[tid] + shared_sum[tid + stride];
        }
        workgroupBarrier();
        stride = stride / 2u;
    }

    let rms = 1.0 / sqrt(shared_sum[0] / f32(u.size) + u.eps);

    var j = tid;
    loop {
        if (j >= u.size) { break; }
        output[row_offset + j] = input[row_offset + j] * rms * weight[j];
        j = j + 256u;
    }
}
