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
@group(0) @binding(1) var<storage, read> dye_in: array<f32>;
@group(0) @binding(2) var<storage, read> velocity_in: array<vec2<f32>>;
@group(0) @binding(3) var<storage, read_write> dye_out: array<f32>;

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

fn read_dye(coord: vec2<i32>) -> f32 {
  let clamped = clamp_xy(coord);
  return dye_in[cell_index(clamped.x, clamped.y)];
}

fn sample_dye(position: vec2<f32>) -> f32 {
  let clamped = clamp(
    position,
    vec2<f32>(0.0, 0.0),
    vec2<f32>(f32(config.width - 1u), f32(config.height - 1u)),
  );
  let base = floor(clamped);
  let frac = clamped - base;
  let origin = vec2<i32>(i32(base.x), i32(base.y));

  let s00 = read_dye(origin);
  let s10 = read_dye(origin + vec2<i32>(1, 0));
  let s01 = read_dye(origin + vec2<i32>(0, 1));
  let s11 = read_dye(origin + vec2<i32>(1, 1));

  let sx0 = s00 + (s10 - s00) * frac.x;
  let sx1 = s01 + (s11 - s01) * frac.x;
  return sx0 + (sx1 - sx0) * frac.y;
}

@compute @workgroup_size(8, 8, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  if (gid.x >= config.width || gid.y >= config.height) {
    return;
  }

  let idx = cell_index(gid.x, gid.y);
  let velocity = velocity_in[idx];
  let backtrace = vec2<f32>(f32(gid.x), f32(gid.y)) - velocity * config.dt * 12.0;
  let uv = vec2<f32>(
    (f32(gid.x) + 0.5) / f32(config.width),
    (f32(gid.y) + 0.5) / f32(config.height),
  );
  let centered = uv * 2.0 - vec2<f32>(1.0, 1.0);
  let source = max(0.0, 1.0 - 8.0 * dot(centered, centered)) * 0.02;

  dye_out[idx] = sample_dye(backtrace) * config.dye_dissipation + source;
}
