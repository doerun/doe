// Simplified prefill attention: Q * K^T -> softmax -> * V
// Single-head per workgroup, iterates over sequence dimension.

struct Uniforms {
    seq_len: u32,
    head_dim: u32,
    num_heads: u32,
    scale: f32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var<storage, read> q: array<f32>;
@group(0) @binding(2) var<storage, read> k: array<f32>;
@group(0) @binding(3) var<storage, read> v: array<f32>;
@group(0) @binding(4) var<storage, read_write> output: array<f32>;

var<workgroup> scores: array<f32, 512>;

@compute @workgroup_size(64)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let head = wid.y;
    let q_row = wid.x;
    let tid = lid.x;

    if (head >= u.num_heads) { return; }
    if (q_row >= u.seq_len) { return; }

    let head_offset = head * u.seq_len * u.head_dim;
    let q_base = head_offset + q_row * u.head_dim;

    // compute Q[row] dot K[col] for each col
    var col = tid;
    loop {
        if (col >= u.seq_len) { break; }
        // causal mask
        if (col > q_row) {
            scores[col] = -1e30;
        } else {
            let k_base = head_offset + col * u.head_dim;
            var dot: f32 = 0.0;
            for (var d: u32 = 0u; d < u.head_dim; d = d + 1u) {
                dot = dot + q[q_base + d] * k[k_base + d];
            }
            scores[col] = dot * u.scale;
        }
        col = col + 64u;
    }
    workgroupBarrier();

    // softmax (simplified: single-pass for short sequences)
    var max_val: f32 = -1e30;
    var i = tid;
    loop {
        if (i >= u.seq_len) { break; }
        max_val = max(max_val, scores[i]);
        i = i + 64u;
    }
    // use scores[256..319] as temp for reduction
    if (tid < 64u) { scores[256u + tid] = max_val; }
    workgroupBarrier();
    if (tid == 0u) {
        var m: f32 = scores[256];
        for (var j: u32 = 1u; j < 64u; j = j + 1u) {
            m = max(m, scores[256u + j]);
        }
        scores[320] = m;
    }
    workgroupBarrier();
    let row_max = scores[320];

    var exp_sum: f32 = 0.0;
    i = tid;
    loop {
        if (i >= u.seq_len) { break; }
        let e = exp(clamp(scores[i] - row_max, -30.0, 30.0));
        scores[i] = e;
        exp_sum = exp_sum + e;
        i = i + 64u;
    }
    if (tid < 64u) { scores[256u + tid] = exp_sum; }
    workgroupBarrier();
    if (tid == 0u) {
        var s: f32 = 0.0;
        for (var j2: u32 = 0u; j2 < 64u; j2 = j2 + 1u) { s = s + scores[256u + j2]; }
        scores[321] = s;
    }
    workgroupBarrier();
    let total = scores[321];

    i = tid;
    loop {
        if (i >= u.seq_len) { break; }
        scores[i] = scores[i] / total;
        i = i + 64u;
    }
    workgroupBarrier();

    // weighted sum of V
    var d = tid;
    loop {
        if (d >= u.head_dim) { break; }
        var acc: f32 = 0.0;
        for (var t: u32 = 0u; t < u.seq_len; t = t + 1u) {
            acc = acc + scores[t] * v[head_offset + t * u.head_dim + d];
        }
        output[head_offset + q_row * u.head_dim + d] = acc;
        d = d + 64u;
    }
}
