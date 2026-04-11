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
@group(0) @binding(1) var<storage, read_write> velocity: array<vec2<f32>>;
@group(0) @binding(2) var<storage, read_write> dye: array<f32>;
@group(0) @binding(3) var<storage, read_write> pressure_a: array<f32>;
@group(0) @binding(4) var<storage, read_write> pressure_b: array<f32>;

const INV_U24: f32 = 1.0 / 16777216.0;

fn cell_index(x: u32, y: u32) -> u32 {
  return y * config.width + x;
}

fn scramble_seed(value: u32) -> u32 {
  var x = value * 747796405u + 2891336453u;
  x = ((x >> ((x >> 28u) + 4u)) ^ x) * 277803737u;
  return (x >> 22u) ^ x;
}

fn noise(x: u32, y: u32) -> f32 {
  let mixed = scramble_seed(config.seed ^ cell_index(x, y));
  return f32(mixed & 0x00ffffffu) * INV_U24;
}

@compute @workgroup_size(8, 8, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  if (gid.x >= config.width || gid.y >= config.height) {
    return;
  }

  let idx = cell_index(gid.x, gid.y);
  let uv = vec2<f32>(
    (f32(gid.x) + 0.5) / f32(config.width),
    (f32(gid.y) + 0.5) / f32(config.height),
  );
  let centered = uv * 2.0 - vec2<f32>(1.0, 1.0);
  let radius_sq = dot(centered, centered);
  let sample = noise(gid.x, gid.y) - 0.5;
  let vortex = config.force_scale / (1.0 + 10.0 * radius_sq);

  velocity[idx] = vec2<f32>(
    -centered.y * vortex + sample * 0.02,
    centered.x * vortex - sample * 0.02,
  );
  dye[idx] = max(0.0, 1.0 - 2.5 * radius_sq) + (sample + 0.5) * 0.05;
  pressure_a[idx] = 0.0;
  pressure_b[idx] = 0.0;
}
