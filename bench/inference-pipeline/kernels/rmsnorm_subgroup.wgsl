// Subgroup-accelerated RMSNorm: replaces the workgroup tree reduction with a
// subgroupAdd plus a single cross-subgroup merge. Functionally equivalent to
// rmsnorm.wgsl but uses ~log2(workgroup_size) fewer barriers and ~workgroup_size
// fewer shared-memory writes.

enable subgroups;

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

const WG_SIZE: u32 = 256u;
const MAX_SUBGROUPS: u32 = 32u;

var<workgroup> subgroup_partials: array<f32, MAX_SUBGROUPS>;

@compute @workgroup_size(256)
fn main(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
    @builtin(subgroup_invocation_id) sid: u32,
    @builtin(subgroup_size) sg_size: u32,
) {
    let row_offset = wid.x * u.size;
    let tid = lid.x;

    var partial: f32 = 0.0;
    var i = tid;
    loop {
        if (i >= u.size) { break; }
        let v = input[row_offset + i];
        partial = partial + v * v;
        i = i + WG_SIZE;
    }

    let subgroup_sum = subgroupAdd(partial);
    let subgroup_id = tid / sg_size;
    if (sid == 0u) {
        subgroup_partials[subgroup_id] = subgroup_sum;
    }
    workgroupBarrier();

    if (tid == 0u) {
        let num_subgroups = WG_SIZE / sg_size;
        var total: f32 = 0.0;
        var k: u32 = 0u;
        loop {
            if (k >= num_subgroups) { break; }
            total = total + subgroup_partials[k];
            k = k + 1u;
        }
        subgroup_partials[0] = total;
    }
    workgroupBarrier();

    let rms = 1.0 / sqrt(subgroup_partials[0] / f32(u.size) + u.eps);

    var j = tid;
    loop {
        if (j >= u.size) { break; }
        let scale = weight[j];
        output[row_offset + j] = input[row_offset + j] * rms * scale;
        j = j + WG_SIZE;
    }
}

@compute @workgroup_size(256)
fn main_weight_offset(
    @builtin(local_invocation_id) lid: vec3u,
    @builtin(workgroup_id) wid: vec3u,
    @builtin(subgroup_invocation_id) sid: u32,
    @builtin(subgroup_size) sg_size: u32,
) {
    let row_offset = wid.x * u.size;
    let tid = lid.x;

    var partial: f32 = 0.0;
    var i = tid;
    loop {
        if (i >= u.size) { break; }
        let v = input[row_offset + i];
        partial = partial + v * v;
        i = i + WG_SIZE;
    }

    let subgroup_sum = subgroupAdd(partial);
    let subgroup_id = tid / sg_size;
    if (sid == 0u) {
        subgroup_partials[subgroup_id] = subgroup_sum;
    }
    workgroupBarrier();

    if (tid == 0u) {
        let num_subgroups = WG_SIZE / sg_size;
        var total: f32 = 0.0;
        var k: u32 = 0u;
        loop {
            if (k >= num_subgroups) { break; }
            total = total + subgroup_partials[k];
            k = k + 1u;
        }
        subgroup_partials[0] = total;
    }
    workgroupBarrier();

    let rms = 1.0 / sqrt(subgroup_partials[0] / f32(u.size) + u.eps);

    var j = tid;
    loop {
        if (j >= u.size) { break; }
        let scale = 1.0 + weight[j];
        output[row_offset + j] = input[row_offset + j] * rms * scale;
        j = j + WG_SIZE;
    }
}
