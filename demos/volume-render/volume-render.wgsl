// Volume ray marcher — shared by Node.js and browser entry points.
//
// Compositing matches open-scivis-datasets reference (dvr.js):
//   accum.rgb += (1 - accum.a) * c.a * c.rgb   (pre-multiplied alpha)
//   accum.a   += (1 - accum.a) * c.a
// Step size: DDA = 1 / max(width, height, depth)
//
// Note: Doe WGSL sema constraints:
//   - binary ops require same concrete type; use vec3f(scalar) for vec*scalar
//   - postfix i++ unsupported; use i = i + 1
//   - user functions referencing uniform globals must be inlined into the kernel

struct Camera {
  eye:     vec3f,
  _p0:     f32,
  look_at: vec3f,
  _p1:     f32,
  width:   u32,
  height:  u32,
  _p2:     u32,
  _p3:     u32,
}

struct VolumeInfo {
  width:  u32,
  height: u32,
  depth:  u32,
  mode:   u32,  // 0=grayscale 1=fire 2=hot 3=viridis 4=cool
}

@group(0) @binding(0) var<uniform>             cam:    Camera;
@group(0) @binding(1) var<uniform>             vol:    VolumeInfo;
@group(0) @binding(2) var                      vol_tex: texture_3d<f32>;
@group(0) @binding(3) var<storage, read_write> pixels: array<u32>;

// mode 1: fire
fn transfer_fire(d: f32) -> vec4f {
  if (d < 0.02) { return vec4f(0.0); }
  let alpha = clamp(d * 4.0, 0.0, 1.0) * 0.5;
  let r = clamp(d * 3.0,       0.0, 1.0);
  let g = clamp(d * 3.0 - 0.6, 0.0, 1.0) * 0.7;
  let b = clamp(d * 5.0 - 3.5, 0.0, 1.0);
  return vec4f(r, g, b, alpha);
}

// mode 2: hot — black→red→yellow→white
fn transfer_hot(d: f32) -> vec4f {
  if (d < 0.01) { return vec4f(0.0); }
  let r = clamp(d * 3.0,       0.0, 1.0);
  let g = clamp(d * 3.0 - 1.0, 0.0, 1.0);
  let b = clamp(d * 3.0 - 2.0, 0.0, 1.0);
  return vec4f(r, g, b, d * 0.8);
}

// mode 3: viridis (piecewise linear approximation, colorblind-friendly)
fn transfer_viridis(d: f32) -> vec4f {
  if (d < 0.01) { return vec4f(0.0); }
  var rgb: vec3f;
  if (d < 0.25) {
    let t = d * 4.0;
    rgb = mix(vec3f(0.267, 0.004, 0.329), vec3f(0.282, 0.305, 0.682), t);
  } else if (d < 0.5) {
    let t = (d - 0.25) * 4.0;
    rgb = mix(vec3f(0.282, 0.305, 0.682), vec3f(0.163, 0.553, 0.627), t);
  } else if (d < 0.75) {
    let t = (d - 0.5) * 4.0;
    rgb = mix(vec3f(0.163, 0.553, 0.627), vec3f(0.478, 0.821, 0.318), t);
  } else {
    let t = (d - 0.75) * 4.0;
    rgb = mix(vec3f(0.478, 0.821, 0.318), vec3f(0.993, 0.906, 0.144), t);
  }
  return vec4f(rgb, d * 0.8);
}

// mode 4: cool — cyan→magenta, colorblind-friendly
fn transfer_cool(d: f32) -> vec4f {
  if (d < 0.01) { return vec4f(0.0); }
  let r = d;
  let g = clamp(1.0 - d * 1.5, 0.0, 1.0);
  let b = 1.0;
  return vec4f(r, g, b, d * 0.8);
}

// matches dvr.js linear_to_srgb — compositing is in linear space; output must be sRGB
fn linear_to_srgb(v: f32) -> f32 {
  if (v <= 0.0031308) { return 12.92 * v; }
  return 1.055 * pow(v, 1.0 / 2.4) - 0.055;
}

fn ray_aabb(ro: vec3f, rd: vec3f) -> vec2f {
  let inv  = vec3f(1.0) / rd;
  let t0   = vec3f(0.0) - ro * inv;
  let t1   = (vec3f(1.0) - ro) * inv;
  let tmin = max(max(min(t0.x, t1.x), min(t0.y, t1.y)), min(t0.z, t1.z));
  let tmax = min(min(max(t0.x, t1.x), max(t0.y, t1.y)), max(t0.z, t1.z));
  return vec2f(tmin, tmax);
}

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  let px = gid.x;
  let py = gid.y;
  if (px >= cam.width || py >= cam.height) { return; }

  let fwd    = normalize(cam.look_at - cam.eye);
  let right  = normalize(cross(fwd, vec3f(0.0, 1.0, 0.0)));
  let up_cam = cross(right, fwd);
  let aspect = f32(cam.width) / f32(cam.height);
  let fov: f32 = 0.6;
  let uv = vec2f(
    (f32(px) + 0.5) / f32(cam.width)  * 2.0 - 1.0,
    (f32(py) + 0.5) / f32(cam.height) * 2.0 - 1.0,
  );
  let rd = normalize(fwd + right * vec3f(uv.x * aspect * fov) - up_cam * vec3f(uv.y * fov));
  let ro = cam.eye;

  let b = ray_aabb(ro, rd);
  if (b.x >= b.y || b.y < 0.0) {
    let bg  = vec3f(0.03, 0.04, 0.06);
    let r_  = u32(clamp(linear_to_srgb(bg.r) * 255.0, 0.0, 255.0));
    let g_  = u32(clamp(linear_to_srgb(bg.g) * 255.0, 0.0, 255.0));
    let b__ = u32(clamp(linear_to_srgb(bg.b) * 255.0, 0.0, 255.0));
    pixels[py * cam.width + px] = r_ | (g_ << 8u) | (b__ << 16u) | (0xFFu << 24u);
    return;
  }

  // DDA step: 1 voxel advance per step along dominant axis (matches reference)
  let max_dim = max(max(vol.width, vol.height), vol.depth);
  let step: f32 = 1.0 / f32(max_dim);

  let t_near = max(b.x, 0.0);
  let t_far  = b.y;
  let nsteps = i32((t_far - t_near) / step);
  var accum  = vec4f(0.0);

  let wf = f32(vol.width  - 1u);
  let hf = f32(vol.height - 1u);
  let df = f32(vol.depth  - 1u);

  for (var i = 0; i < nsteps; i = i + 1) {
    if (accum.a >= 0.95) { break; }
    let t   = t_near + f32(i) * step;
    let pos = ro + rd * vec3f(t);
    let p   = clamp(pos, vec3f(0.0), vec3f(1.0));
    let d   = textureLoad(vol_tex, vec3u(u32(p.x * wf), u32(p.y * hf), u32(p.z * df)), 0).r;
    var c: vec4f;
    if (vol.mode == 1u) {
      c = transfer_fire(d);
    } else if (vol.mode == 2u) {
      c = transfer_hot(d);
    } else if (vol.mode == 3u) {
      c = transfer_viridis(d);
    } else if (vol.mode == 4u) {
      c = transfer_cool(d);
    } else {
      c = vec4f(d, d, d, d);  // mode 0: grayscale (default)
    }
    // correct pre-multiplied alpha compositing (matches reference dvr.js)
    let w = c.a * (1.0 - accum.a);
    accum = vec4f(accum.rgb + c.rgb * vec3f(w), accum.a + w);
  }

  let bg  = vec3f(0.03, 0.04, 0.06);
  let rgb = accum.rgb + bg * vec3f(1.0 - accum.a);
  let r   = u32(clamp(linear_to_srgb(rgb.r) * 255.0, 0.0, 255.0));
  let g   = u32(clamp(linear_to_srgb(rgb.g) * 255.0, 0.0, 255.0));
  let b_  = u32(clamp(linear_to_srgb(rgb.b) * 255.0, 0.0, 255.0));
  pixels[py * cam.width + px] = r | (g << 8u) | (b_ << 16u) | (0xFFu << 24u);
}
