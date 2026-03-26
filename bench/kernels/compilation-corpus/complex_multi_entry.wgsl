// Multi-entry-point shader with multiple binding groups and branching.
// Stresses the full compiler pipeline: sema, IR, binding extraction, emit.

struct Params {
    size: u32,
    scale: f32,
    bias: f32,
    mode: u32,
}

@group(0) @binding(0) var<uniform> params: Params;
@group(0) @binding(1) var<storage, read> input_a: array<f32>;
@group(0) @binding(2) var<storage, read> input_b: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;

@group(1) @binding(0) var<storage, read> weights: array<f32>;
@group(1) @binding(1) var<storage, read_write> scratch: array<f32>;

fn silu(x: f32) -> f32 {
    return x / (1.0 + exp(-clamp(x, -30.0, 30.0)));
}

fn gelu(x: f32) -> f32 {
    let inner = 0.7978845608 * (x + 0.044715 * x * x * x);
    return 0.5 * x * (1.0 + tanh(clamp(inner, -15.0, 15.0)));
}

@compute @workgroup_size(256)
fn fused_gate_up(@builtin(global_invocation_id) gid: vec3u) {
    let idx = gid.x;
    if (idx >= params.size) { return; }

    let gate_val = input_a[idx] * weights[idx] * params.scale + params.bias;
    let up_val = input_b[idx] * weights[params.size + idx];

    var activated: f32;
    if (params.mode == 0u) {
        activated = silu(gate_val);
    } else if (params.mode == 1u) {
        activated = gelu(gate_val);
    } else {
        activated = max(gate_val, 0.0);
    }

    output[idx] = activated * up_val;
}

@compute @workgroup_size(256)
fn elementwise_add(@builtin(global_invocation_id) gid: vec3u) {
    let idx = gid.x;
    if (idx >= params.size) { return; }
    output[idx] = input_a[idx] + input_b[idx];
}

@compute @workgroup_size(256)
fn scale_bias(@builtin(global_invocation_id) gid: vec3u) {
    let idx = gid.x;
    if (idx >= params.size) { return; }
    output[idx] = input_a[idx] * params.scale + params.bias;
}
