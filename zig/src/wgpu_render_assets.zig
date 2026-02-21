pub const RENDER_DRAW_SHADER_SOURCE =
    \\@group(0) @binding(0) var<uniform> color: vec3f;
    \\@vertex
    \\fn vs_main(@location(0) pos: vec4f) -> @builtin(position) vec4f {
    \\  return pos;
    \\}
    \\@fragment
    \\fn fs_main() -> @location(0) vec4f {
    \\  return vec4f(color * (1.0 / 5000.0), 1.0);
    \\}
;

pub const RENDER_DRAW_VERTEX_DATA = [12]f32{
    0.0, 0.5, 0.0, 1.0,
    -0.5, -0.5, 0.0, 1.0,
    0.5, -0.5, 0.0, 1.0,
};

pub const RENDER_DRAW_UNIFORM_COLOR = [3]f32{ 0.0, 0.0, 0.0 };
