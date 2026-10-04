struct Particle { position: vec2<f32>, velocity: vec2<f32> }
struct Settings { dt: f32 }
@group(0) @binding(0) var<storage, read> source: array<Particle>;
@group(0) @binding(1) var<storage, read_write> destination: array<Particle>;
@group(0) @binding(2) var<uniform> settings: Settings;

@compute @workgroup_size(128)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let index = gid.x;
  if (index >= arrayLength(&source)) { return; }
  // Each band follows a different point in a tiled attraction field.
  let band = index / 256u;
  let lane = index % 256u;
  let row = band % 256u;
  let center = vec2<f32>(f32(lane) / 128.0 - 1.0, f32(row) / 128.0 - 1.0);
  let particle = source[index];
  let spin = vec2<f32>(-particle.position.y, particle.position.x) * 0.125;
  let spring = particle.position * 0.015625;
  let attraction = center * 0.0009765625;
  let acceleration = spin - spring + attraction;
  let velocity = particle.velocity * 0.9990234375 + acceleration * settings.dt;
  destination[index] = Particle(particle.position + velocity * settings.dt, velocity);
}
