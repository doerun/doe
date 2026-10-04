// Seeded application state and an independent scalar f32 simulation oracle.
export function initialParticles(count, seed) {
  let state = seed >>> 0;
  function random() {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 4294967296;
  }
  const particles = new Float32Array(count * 4);
  for (let index = 0; index < count; index++) {
    const radius = Math.sqrt(random()) * 0.85;
    const angle = (index % 5) * Math.PI * 2 / 5 + radius * 5 + (random() - 0.5) * 0.45;
    const x = Math.cos(angle) * radius;
    const y = Math.sin(angle) * radius;
    particles.set([x, y, -y * 0.08, x * 0.08], index * 4);
  }
  return particles;
}

export function referenceParticles(initial, steps, dt) {
  const result = initial.slice();
  const f = Math.fround;
  for (let step = 0; step < steps; step++) {
    for (let index = 0; index < result.length / 4; index++) {
      const offset = index * 4;
      const x = result[offset];
      const y = result[offset + 1];
      const centerX = f(f((index % 256) / 128) - 1);
      const centerY = f(f((Math.floor(index / 256) % 256) / 128) - 1);
      const ax = f(f(f(-y * 0.125) - f(x * 0.015625)) + f(centerX * 0.0009765625));
      const ay = f(f(f(x * 0.125) - f(y * 0.015625)) + f(centerY * 0.0009765625));
      const vx = f(f(result[offset + 2] * 0.9990234375) + f(ax * dt));
      const vy = f(f(result[offset + 3] * 0.9990234375) + f(ay * dt));
      result[offset] = f(x + f(vx * dt));
      result[offset + 1] = f(y + f(vy * dt));
      result[offset + 2] = vx;
      result[offset + 3] = vy;
    }
  }
  return result;
}

export function compareParticles(actual, expected, tolerance) {
  if (actual.length !== expected.length) throw new Error('Particle shape mismatch');
  let maxAbsoluteError = 0;
  let maxRelativeError = 0;
  let failures = 0;
  for (let index = 0; index < actual.length; index++) {
    const absolute = Math.abs(actual[index] - expected[index]);
    const relative = absolute / Math.max(Math.abs(expected[index]), tolerance.absolute, Number.MIN_VALUE);
    if (!Number.isFinite(actual[index])
        || absolute > tolerance.absolute + tolerance.relative * Math.abs(expected[index])) failures++;
    maxAbsoluteError = Math.max(maxAbsoluteError, absolute);
    maxRelativeError = Math.max(maxRelativeError, relative);
  }
  return { passed: failures === 0, failures, maxAbsoluteError, maxRelativeError,
    componentsCompared: actual.length };
}

export const renderWGSL = `
struct Particle { position: vec2<f32>, velocity: vec2<f32> }
@group(0) @binding(0) var<storage, read> particles: array<Particle>;
struct Vertex { @builtin(position) position: vec4<f32>, @location(0) color: vec3<f32>,
  @location(1) uv: vec2<f32> }
@vertex fn vertex(@builtin(vertex_index) vertex: u32, @builtin(instance_index) index: u32) -> Vertex {
  var corners = array<vec2<f32>, 6>(vec2(-1., -1.), vec2(1., -1.), vec2(-1., 1.),
    vec2(-1., 1.), vec2(1., -1.), vec2(1., 1.));
  let particle = particles[index];
  let uv = corners[vertex];
  let speed = length(particle.velocity);
  let tint = f32(index % 256u) / 255.;
  var result: Vertex;
  result.position = vec4(particle.position * vec2(0.62, 0.95) + vec2(0.30, 0.) + uv * 0.0024, 0., 1.);
  result.color = mix(vec3(0.06, 0.6, 1.), vec3(0.85, 0.22, 0.8), tint) + speed * 0.4;
  result.uv = uv;
  return result;
}
@fragment fn fragment(input: Vertex) -> @location(0) vec4<f32> {
  let glow = exp(-dot(input.uv, input.uv) * 2.8) * 0.85;
  return vec4(input.color * glow, glow);
}`;
