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
@group(0) @binding(1) var<storage, read> velocity_in: array<vec2<f32>>;
@group(0) @binding(2) var<storage, read_write> divergence_out: array<f32>;

fn cell_index(x: u32, y: u32) -> u32 {
  return y * config.width + x;
}

fn clamp_xy(coord: vec2<i32>) -> vec2<u32> {
  let max_x = i32(config.width) - 1;
  let max_y = i32(config.height) - 1;
  return vec2<u32>(
    u32(clamp(coord.x, 0, max_x)),
    u32(clamp(coord.y, 0, max_y)),
  );
}

fn read_velocity(coord: vec2<i32>) -> vec2<f32> {
  let clamped = clamp_xy(coord);
  return velocity_in[cell_index(clamped.x, clamped.y)];
}

@compute @workgroup_size(8, 8, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  if (gid.x >= config.width || gid.y >= config.height) {
    return;
  }

  let idx = cell_index(gid.x, gid.y);
  let coord = vec2<i32>(i32(gid.x), i32(gid.y));
  let left = read_velocity(coord + vec2<i32>(-1, 0));
  let right = read_velocity(coord + vec2<i32>(1, 0));
  let bottom = read_velocity(coord + vec2<i32>(0, -1));
  let top = read_velocity(coord + vec2<i32>(0, 1));

  divergence_out[idx] = 0.5 * ((right.x - left.x) + (top.y - bottom.y));
}
