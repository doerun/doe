struct Uniforms {
    num_heads: u32,
    head_dim: u32,
    kv_len: u32,
    scale: f32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> q: array<f32>;
@group(0) @binding(2) var<storage, read> k_cache: array<f32>;
@group(0) @binding(3) var<storage, read> v_cache: array<f32>;
@group(0) @binding(4) var<storage, read_write> output: array<f32>;

var<workgroup> shared_scores: array<f32, 2048>;
var<workgroup> shared_max: array<f32, 64>;
var<workgroup> shared_sum: array<f32, 64>;

fn safe_exp(x: f32) -> f32 {
    return exp(clamp(x, -30.0, 30.0));
}

@compute @workgroup_size(64)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let head = wid.x;
    let tid = lid.x;

    if (head >= u.num_heads) { return; }

    let q_offset = head * u.head_dim;
    let kv_head_stride = u.head_dim * u.kv_len;

    // compute attention scores: dot(q, k[t]) for each t
    var t = tid;
    loop {
        if (t >= u.kv_len) { break; }
        var score: f32 = 0.0;
        for (var d: u32 = 0u; d < u.head_dim; d = d + 1u) {
            score = score + q[q_offset + d] * k_cache[head * kv_head_stride + t * u.head_dim + d];
        }
        shared_scores[t] = score * u.scale;
        t = t + 64u;
    }
    workgroupBarrier();

    // find max for numerical stability
    var local_max: f32 = -1e30;
    var s = tid;
    loop {
        if (s >= u.kv_len) { break; }
        local_max = max(local_max, shared_scores[s]);
        s = s + 64u;
    }
    shared_max[tid] = local_max;
    workgroupBarrier();

    // tree reduce max
    var stride: u32 = 32u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride && tid + stride < 64u) {
            shared_max[tid] = max(shared_max[tid], shared_max[tid + stride]);
        }
        workgroupBarrier();
        stride = stride / 2u;
    }
    let row_max = shared_max[0];
    workgroupBarrier();

    // softmax: exp and sum
    var local_sum: f32 = 0.0;
    s = tid;
    loop {
        if (s >= u.kv_len) { break; }
        let e = safe_exp(shared_scores[s] - row_max);
        shared_scores[s] = e;
        local_sum = local_sum + e;
        s = s + 64u;
    }
    shared_sum[tid] = local_sum;
    workgroupBarrier();

    // tree reduce sum
    stride = 32u;
    loop {
        if (stride == 0u) { break; }
        if (tid < stride && tid + stride < 64u) {
            shared_sum[tid] = shared_sum[tid] + shared_sum[tid + stride];
        }
        workgroupBarrier();
        stride = stride / 2u;
    }
    let total = shared_sum[0];
    workgroupBarrier();

    // normalize scores
    s = tid;
    loop {
        if (s >= u.kv_len) { break; }
        shared_scores[s] = shared_scores[s] / total;
        s = s + 64u;
    }
    workgroupBarrier();

    // weighted sum of values
    var d = tid;
    loop {
        if (d >= u.head_dim) { break; }
        var acc: f32 = 0.0;
        for (var t2: u32 = 0u; t2 < u.kv_len; t2 = t2 + 1u) {
            acc = acc + shared_scores[t2] * v_cache[head * kv_head_stride + t2 * u.head_dim + d];
        }
        output[head * u.head_dim + d] = acc;
        d = d + 64u;
    }
}
