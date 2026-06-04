struct Params {
  pixel_count: u32,
  _pad0: u32,
  _pad1: u32,
  _pad2: u32,
}

@group(0) @binding(0) var<uniform> params: Params;
@group(0) @binding(1) var<storage, read> input_pixels: array<u32>;
@group(0) @binding(2) var<storage, read_write> output_pixels: array<u32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let index = gid.x;
  if (index >= params.pixel_count) {
    return;
  }
  output_pixels[index] = input_pixels[index] ^ 0x00ffffffu;
}
