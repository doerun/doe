// Stress test: many bindings across two bind groups.
// Tests sema binding extraction and emit-stage layout handling.

struct Config {
    size: u32,
    alpha: f32,
    beta: f32,
    gamma: f32,
}

@group(0) @binding(0) var<uniform> config: Config;
@group(0) @binding(1) var<storage, read> src_a: array<f32>;
@group(0) @binding(2) var<storage, read> src_b: array<f32>;
@group(0) @binding(3) var<storage, read> src_c: array<f32>;
@group(0) @binding(4) var<storage, read> src_d: array<f32>;
@group(0) @binding(5) var<storage, read_write> dst_a: array<f32>;
@group(0) @binding(6) var<storage, read_write> dst_b: array<f32>;

@group(1) @binding(0) var<storage, read> weights_0: array<f32>;
@group(1) @binding(1) var<storage, read> weights_1: array<f32>;
@group(1) @binding(2) var<storage, read> weights_2: array<f32>;
@group(1) @binding(3) var<storage, read_write> aux_out: array<f32>;

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    let idx = gid.x;
    if (idx >= config.size) { return; }

    let a = src_a[idx] * weights_0[idx];
    let b = src_b[idx] * weights_1[idx];
    let c = src_c[idx] * weights_2[idx];
    let d = src_d[idx];

    let combined = a * config.alpha + b * config.beta + c * config.gamma + d;
    dst_a[idx] = combined;
    dst_b[idx] = combined * combined;
    aux_out[idx] = a + b + c;
}
