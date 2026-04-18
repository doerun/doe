// Canvas stress renderer — 10k+ animated rounded rectangles with SDF antialiasing.
//
// Doe WGSL sema: scalar broadcast via vec2f(x); i = i + 1 not i++; inline any
// helper that closes over module-scope uniforms.

struct Frame {
  viewport: vec2f,
  time:     f32,
  count:    u32,
}

struct Instance {
  seed:   vec2f,   // persistent per-primitive deterministic seed
  size:   vec2f,   // base size in NDC
  corner: f32,     // corner radius in NDC
  hue:    f32,     // base hue [0, 1]
  _pad0:  vec2f,
}

@group(0) @binding(0) var<uniform> frame: Frame;
@group(0) @binding(1) var<storage, read> instances: array<Instance>;

struct VsOut {
  @builtin(position) pos: vec4f,
  @location(0)       local:  vec2f,   // primitive-local coordinate in [-size, size]
  @location(1)       size:   vec2f,
  @location(2)       corner: f32,
  @location(3)       color:  vec4f,
}

@vertex
fn vs_main(@builtin(instance_index) inst: u32,
           @builtin(vertex_index)   vid:  u32) -> VsOut {
  let I = instances[inst];

  // Stable low-frequency advection: each primitive follows a Lissajous curve
  // parameterized by its seed, so neighbors diverge but every primitive's
  // motion is smooth.
  let t = frame.time;
  let sx = I.seed.x * 6.2831853;
  let sy = I.seed.y * 6.2831853;
  let ax = 0.45 * sin(t * 0.31 + sx) + 0.35 * sin(t * 0.13 + sy * 1.7);
  let ay = 0.45 * cos(t * 0.27 + sy) + 0.35 * cos(t * 0.17 + sx * 1.3);
  let rot = 0.5 * sin(t * 0.21 + sx + sy);

  // Four billboard corners.
  let corner_uv = vec2f(
    f32((vid & 1u)) * 2.0 - 1.0,
    f32((vid >> 1u) & 1u) * 2.0 - 1.0,
  );
  let local = corner_uv * I.size;

  // Rotate the quad corner.
  let c = cos(rot);
  let s = sin(rot);
  let rotated = vec2f(local.x * c - local.y * s, local.x * s + local.y * c);
  let center = vec2f(ax, ay);
  let ndc = center + rotated;

  // Aspect correction so primitives stay visually square regardless of viewport.
  let aspect = frame.viewport.x / frame.viewport.y;
  let pos_clip = vec4f(ndc.x / aspect, ndc.y, 0.0, 1.0);

  // HSL → RGB (hue advances over time so the scene breathes).
  let hue = fract(I.hue + t * 0.04);
  let col = hsl_to_rgb(hue, 0.65, 0.55);
  let opacity = 0.85;

  var out: VsOut;
  out.pos = pos_clip;
  out.local = local;
  out.size = I.size;
  out.corner = I.corner;
  out.color = vec4f(col, opacity);
  return out;
}

// Inlined helper (no uniform capture, so standalone fn is fine, but kept
// pure for clarity).
fn hsl_to_rgb(h: f32, s: f32, l: f32) -> vec3f {
  let c = (1.0 - abs(2.0 * l - 1.0)) * s;
  let hp = h * 6.0;
  let x = c * (1.0 - abs(fract(hp * 0.5) * 2.0 - 1.0));
  var rgb: vec3f;
  if (hp < 1.0)      { rgb = vec3f(c, x, 0.0); }
  else if (hp < 2.0) { rgb = vec3f(x, c, 0.0); }
  else if (hp < 3.0) { rgb = vec3f(0.0, c, x); }
  else if (hp < 4.0) { rgb = vec3f(0.0, x, c); }
  else if (hp < 5.0) { rgb = vec3f(x, 0.0, c); }
  else               { rgb = vec3f(c, 0.0, x); }
  return rgb + vec3f(l - 0.5 * c);
}

@fragment
fn fs_main(in: VsOut) -> @location(0) vec4f {
  // Rounded-rectangle SDF. `q` is distance-from-inner-core in each axis;
  // max(q, 0) handles the straight edges, and the length() term rounds the
  // corners. Classic Inigo Quilez formulation.
  let q = abs(in.local) - (in.size - vec2f(in.corner));
  let d = length(max(q, vec2f(0.0))) + min(max(q.x, q.y), 0.0) - in.corner;

  // Antialiased edge: fade from full alpha inside to zero just outside.
  let aa = fwidth(d) * 0.75 + 1e-6;
  let alpha_mask = 1.0 - smoothstep(-aa, aa, d);
  let alpha = in.color.a * alpha_mask;
  if (alpha < (1.0 / 255.0)) {
    discard;
  }
  return vec4f(in.color.rgb * alpha, alpha);
}
