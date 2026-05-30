struct VertexOut {
  @builtin(position) position: vec4f,
  @location(0) uv: vec2f,
};

@fragment
fn main(input: VertexOut) -> @location(0) vec4f {
  return vec4f(input.uv, 0.25, 1.0);
}
