struct Config {
  width: u32,
  height: u32,
  seed: u32,
  _pad0: u32,
  dt: f32,
  velocity_dissipation: f32,
  dye_dissipation: f32,
  force_scale: f32,
}

@group(0) @binding(0) var<uniform> config: Config;
@group(0) @binding(1) var<storage, read> src: array<f32>;
@group(0) @binding(2) var<storage, read_write> dst: array<f32>;

fn cell_index(x: u32, y: u32) -> u32 {
  return y * config.width + x;
}

@compute @workgroup_size(8, 8, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  if (gid.x >= config.width || gid.y >= config.height) {
    return;
  }

  let idx = cell_index(gid.x, gid.y);
  dst[idx] = src[idx];
}
