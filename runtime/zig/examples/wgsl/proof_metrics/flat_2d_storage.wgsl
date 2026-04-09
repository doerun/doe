@group(0) @binding(0) var<storage, read_write> data: array<u32>;

@compute @workgroup_size(8, 2, 1)
fn main(
    @builtin(global_invocation_id) gid: vec3u,
    @builtin(num_workgroups) num_wg: vec3u,
) {
    let width = num_wg.x * 8u;
    let idx = gid.y * width + gid.x;
    data[idx] = 1u;
}
