struct Config {
  path_count: u32,
  samples_per_path: u32,
  bounce_count: u32,
  base_seed: u32,
}

@group(0) @binding(0) var<uniform> config: Config;
@group(0) @binding(1) var<storage, read_write> out_paths: array<vec4<f32>>;

const INV_U24: f32 = 1.0 / 16777216.0;
const WORKGROUP_SIZE: u32 = 64u;

fn scramble_seed(value: u32) -> u32 {
  var x = value * 747796405u + 2891336453u;
  x = ((x >> ((x >> 28u) + 4u)) ^ x) * 277803737u;
  return (x >> 22u) ^ x;
}

fn next_random(state: ptr<function, u32>) -> f32 {
  var x = *state;
  x ^= x << 13u;
  x ^= x >> 17u;
  x ^= x << 5u;
  *state = x;
  return f32(x & 0x00ffffffu) * INV_U24;
}

fn next_signed_random(state: ptr<function, u32>) -> f32 {
  return next_random(state) * 2.0 - 1.0;
}

fn safe_normalize(value: vec3<f32>) -> vec3<f32> {
  let len_sq = max(dot(value, value), 0.000001);
  return value * (1.0 / sqrt(len_sq));
}

@compute @workgroup_size(WORKGROUP_SIZE, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let path_index = gid.x;
  if (path_index >= config.path_count) {
    return;
  }

  let sun_dir = safe_normalize(vec3<f32>(0.35, 0.82, 0.44));
  var state = scramble_seed(config.base_seed ^ path_index);
  var radiance = vec3<f32>(0.0);

  for (var sample_index: u32 = 0u; sample_index < config.samples_per_path; sample_index += 1u) {
    state = scramble_seed(state ^ (sample_index * 747796405u) ^ (path_index * 2891336453u));

    var throughput = vec3<f32>(1.0, 0.92, 0.84);
    var position = vec3<f32>(
      next_signed_random(&state) * 0.5,
      next_signed_random(&state) * 0.5,
      next_random(&state) * 0.25,
    );
    var direction = safe_normalize(vec3<f32>(
      next_signed_random(&state),
      next_signed_random(&state),
      next_random(&state) * 1.5 + 0.25,
    ));
    var contribution = vec3<f32>(0.0);

    for (var bounce_index: u32 = 0u; bounce_index < config.bounce_count; bounce_index += 1u) {
      let scatter = safe_normalize(vec3<f32>(
        next_signed_random(&state) + direction.x * 0.35,
        next_signed_random(&state) + direction.y * 0.35,
        next_random(&state) + direction.z * 0.5,
      ));
      let sky = 0.15 + 0.85 * max(scatter.y * 0.5 + 0.5, 0.0);
      let sun = max(dot(scatter, sun_dir), 0.0);

      contribution += throughput * (
        vec3<f32>(0.08, 0.12, 0.18) * sky +
        vec3<f32>(0.9, 0.78, 0.58) * sun * sun * sun
      );

      let travel = 0.2 + next_random(&state) * 1.8;
      position += scatter * travel + vec3<f32>(0.02 * direction.y, -0.01 * direction.x, 0.03);
      direction = safe_normalize(scatter + position * 0.015);

      let fog = 0.94 - 0.03 * f32(bounce_index);
      throughput *= vec3<f32>(
        0.90 + 0.06 * next_random(&state),
        0.88 + 0.08 * next_random(&state),
        0.86 + 0.10 * next_random(&state),
      ) * fog;
    }

    radiance += contribution;
  }

  let inv_samples = 1.0 / max(f32(config.samples_per_path), 1.0);
  let average = radiance * inv_samples;
  let luminance = dot(average, vec3<f32>(0.2126, 0.7152, 0.0722));
  out_paths[path_index] = vec4<f32>(average, luminance);
}
