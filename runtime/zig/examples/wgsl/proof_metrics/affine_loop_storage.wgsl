@group(0) @binding(0) var<storage, read_write> data: array<u32>;

@compute @workgroup_size(8)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    for (var i: u32 = 1u; i <= 4u; i = i + 2u) {
        data[gid.x * 2u + i * 3u + 1u] = 1u;
    }
}
