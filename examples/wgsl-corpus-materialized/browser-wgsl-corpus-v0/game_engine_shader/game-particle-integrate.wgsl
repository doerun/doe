struct Particle {
  position: vec2f,
  velocity: vec2f,
};

@group(0) @binding(0) var<storage, read_write> particles: array<Particle>;

override dt: f32 = 0.016;

@compute @workgroup_size(128)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  let index = gid.x;
  var particle = particles[index];
  particle.position = particle.position + particle.velocity * dt;
  particles[index] = particle;
}
