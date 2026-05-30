@group(0) @binding(0) var src_tex: texture_2d<f32>;
@group(0) @binding(1) var src_sampler: sampler;

struct VertexOut {
  @builtin(position) position: vec4f,
  @location(0) uv: vec2f,
};

@fragment
fn main(input: VertexOut) -> @location(0) vec4f {
  let color = textureSample(src_tex, src_sampler, input.uv);
  return vec4f(color.rgb * color.a, color.a);
}
