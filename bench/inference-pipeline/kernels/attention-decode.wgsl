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

var<workgroup> scores: array<f32, 2048>;
var<workgroup> s_max: array<f32, 64>;
var<workgroup> s_sum: array<f32, 64>;

fn dot_qk(head: u32, token: u32) -> f32 {
    let q_off = head * u.head_dim;
    let kv_off = head * u.head_dim * u.kv_len + token * u.head_dim;
    let vec_dim = u.head_dim & ~3u;

    var acc: f32 = 0.0;
    for (var d: u32 = 0u; d < vec_dim; d = d + 4u) {
        acc += dot(
            vec4<f32>(
                q[q_off + d + 0u],
                q[q_off + d + 1u],
                q[q_off + d + 2u],
                q[q_off + d + 3u],
            ),
            vec4<f32>(
                k_cache[kv_off + d + 0u],
                k_cache[kv_off + d + 1u],
                k_cache[kv_off + d + 2u],
                k_cache[kv_off + d + 3u],
            ),
        );
    }
    for (var d: u32 = vec_dim; d < u.head_dim; d = d + 1u) {
        acc += q[q_off + d] * k_cache[kv_off + d];
    }
    return acc;
}

@compute @workgroup_size(64)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
) {
    let head = wid.x;
    let tid = lid.x;
    if (head >= u.num_heads) { return; }

    let q_off = head * u.head_dim;
    let kv_stride = u.head_dim * u.kv_len;

    var t = tid;
    loop {
        if (t >= u.kv_len) { break; }
        scores[t] = dot_qk(head, t) * u.scale;
        t = t + 64u;
    }
    workgroupBarrier();

    var lm: f32 = -1e30;
    var s2 = tid;
    loop {
        if (s2 >= u.kv_len) { break; }
        lm = max(lm, scores[s2]);
        s2 = s2 + 64u;
    }
    s_max[tid] = lm;
    workgroupBarrier();

    var st: u32 = 32u;
    loop {
        if (st == 0u) { break; }
        if (tid < st && tid + st < 64u) { s_max[tid] = max(s_max[tid], s_max[tid + st]); }
        workgroupBarrier();
        st = st / 2u;
    }
    let rm = s_max[0];
    workgroupBarrier();

    var ls: f32 = 0.0;
    var s3 = tid;
    loop {
        if (s3 >= u.kv_len) { break; }
        let e = exp(clamp(scores[s3] - rm, -30.0, 30.0));
        scores[s3] = e;
        ls = ls + e;
        s3 = s3 + 64u;
    }
    s_sum[tid] = ls;
    workgroupBarrier();

    st = 32u;
    loop {
        if (st == 0u) { break; }
        if (tid < st && tid + st < 64u) { s_sum[tid] = s_sum[tid] + s_sum[tid + st]; }
        workgroupBarrier();
        st = st / 2u;
    }
    let total = s_sum[0];
    workgroupBarrier();

    var s4 = tid;
    loop {
        if (s4 >= u.kv_len) { break; }
        scores[s4] = scores[s4] / total;
        s4 = s4 + 64u;
    }
    workgroupBarrier();

    var d2 = tid * 2u;
    loop {
        if (d2 >= u.head_dim) { break; }
        let d3 = d2 + 1u;
        var acc0: f32 = 0.0;
        var acc1: f32 = 0.0;
        for (var t2: u32 = 0u; t2 < u.kv_len; t2 = t2 + 1u) {
            let value_base = head * kv_stride + t2 * u.head_dim + d2;
            let weight = scores[t2];
            acc0 += weight * v_cache[value_base];
            if (d3 < u.head_dim) {
                acc1 += weight * v_cache[value_base + 1u];
            }
        }
        output[head * u.head_dim + d2] = acc0;
        if (d3 < u.head_dim) {
            output[head * u.head_dim + d3] = acc1;
        }
        d2 = d2 + 128u;
    }
}
