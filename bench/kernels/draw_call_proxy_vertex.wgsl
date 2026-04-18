// Default vertex shader for render-draw proxy benchmarks.
//
// Used by Doe's Vulkan render pipeline as the fallback vertex shader when a
// render-draw command does not reference an explicit vertex shader. Generates
// a fullscreen triangle from @builtin(vertex_index) so draws can proceed
// without vertex buffer bindings.
//
// For index values 0..2 the output positions form a single triangle that
// covers the entire NDC viewport. Values outside that range wrap via mod 3
// so draw calls with larger vertexCount/indexCount still produce valid
// geometry; the rasterizer will clip duplicate triangles.
@vertex
fn main(@builtin(vertex_index) idx: u32) -> @builtin(position) vec4f {
    var positions = array<vec2f, 3>(
        vec2f(-1.0, -1.0),
        vec2f( 3.0, -1.0),
        vec2f(-1.0,  3.0),
    );
    return vec4f(positions[idx % 3u], 0.0, 1.0);
}
