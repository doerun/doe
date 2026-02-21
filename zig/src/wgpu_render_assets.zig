pub const RENDER_DRAW_SHADER_SOURCE =
    \\@group(0) @binding(0) var<uniform> color: vec3f;
    \\@group(0) @binding(1) var sampled_tex: texture_2d<f32>;
    \\@group(0) @binding(2) var sampled_sampler: sampler;
    \\struct VsOut {
    \\  @builtin(position) pos: vec4f,
    \\  @location(0) uv: vec2f,
    \\};
    \\@vertex
    \\fn vs_main(@location(0) pos: vec4f) -> VsOut {
    \\  var out: VsOut;
    \\  out.pos = pos;
    \\  out.uv = vec2f(pos.x * 0.5 + 0.5, (0.5 - pos.y * 0.5));
    \\  return out;
    \\}
    \\@fragment
    \\fn fs_main(in: VsOut) -> @location(0) vec4f {
    \\  let sampled = textureSample(sampled_tex, sampled_sampler, in.uv);
    \\  return vec4f(sampled.rgb + color * (1.0 / 5000.0), sampled.a);
    \\}
;

pub const RENDER_DRAW_VERTEX_DATA = [12]f32{
    0.0,  0.5,  0.0, 1.0,
    -0.5, -0.5, 0.0, 1.0,
    0.5,  -0.5, 0.0, 1.0,
};

pub const RENDER_DRAW_UNIFORM_COLOR = [3]f32{ 0.0, 0.0, 0.0 };

pub const RENDER_DRAW_TEXTURE_WIDTH: u32 = 2;
pub const RENDER_DRAW_TEXTURE_HEIGHT: u32 = 2;
pub const RENDER_DRAW_TEXTURE_BYTES_PER_ROW: u32 = RENDER_DRAW_TEXTURE_WIDTH * 4;
pub const RENDER_DRAW_TEXTURE_DATA = [RENDER_DRAW_TEXTURE_WIDTH * RENDER_DRAW_TEXTURE_HEIGHT * 4]u8{
    255, 0,   0,   255,
    0,   255, 0,   255,
    0,   0,   255, 255,
    255, 255, 0,   255,
};
