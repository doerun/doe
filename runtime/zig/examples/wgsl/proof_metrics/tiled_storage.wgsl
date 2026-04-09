@group(0) @binding(0) var<storage, read_write> data: array<u32>;

@compute @workgroup_size(8)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    let idx = (gid.x / 4u) * 8u + (gid.x % 4u) + 3u;
    data[idx] = 1u;
}
