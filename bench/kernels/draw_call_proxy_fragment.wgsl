// Default fragment shader for render-draw proxy benchmarks.
//
// Used by Doe's Vulkan render pipeline as the fallback fragment shader when a
// render-draw command does not reference an explicit fragment shader. Outputs
// a fixed color so the render pipeline produces visible output even when the
// benchmark focuses on encode/draw-call throughput rather than shading.
@fragment
fn main(@builtin(position) pos: vec4f) -> @location(0) vec4f {
    return vec4f(0.25, 0.5, 0.75, 1.0);
}
