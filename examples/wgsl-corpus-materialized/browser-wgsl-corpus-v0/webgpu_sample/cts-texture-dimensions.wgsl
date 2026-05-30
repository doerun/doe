@group(0) @binding(0) var tex: texture_2d<f32>;
@group(0) @binding(1) var<storage, read_write> out: array<u32>;

@compute @workgroup_size(1)
fn main() {
  let dims = textureDimensions(tex);
  out[0] = dims.x;
  out[1] = dims.y;
}
