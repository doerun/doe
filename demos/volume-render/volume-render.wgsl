// Volume ray marcher — shared by Node.js and browser entry points.
//
// Bindings:
//   0: Camera uniform
//   1: VolumeInfo uniform
//   2: volume texture_3d<f32> (r8unorm, values in [0,1])
//   3: output storage buffer array<u32> (packed RGBA8, row-major)
//
// Note: Doe WGSL sema constraints observed here:
//   - binary ops require same concrete type (no implicit scalar broadcast)
//   - postfix i++ not supported; use i = i + 1
//   - user functions referencing uniform globals must be inlined into the kernel

struct Camera {
  eye:    vec3f,
  _p0:    f32,
  target: vec3f,
  _p1:    f32,
  width:  u32,
  height: u32,
  _p2:    u32,
  _p3:    u32,
}

struct VolumeInfo {
  width:  u32,
  height: u32,
  depth:  u32,
  _p:     u32,
}

@group(0) @binding(0) var<uniform>             cam:    Camera;
@group(0) @binding(1) var<uniform>             vol:    VolumeInfo;
@group(0) @binding(2) var                      vol_tex: texture_3d<f32>;
@group(0) @binding(3) var<storage, read_write> pixels: array<u32>;

fn transfer(d: f32) -> vec4f {
  if (d < 0.06) { return vec4f(0.0); }
  let alpha = min(d * 1.2, 0.9) * 0.04;
  let r = min(d * 3.0,       1.0);
  let g = min(d * 3.0 - 0.8, 1.0) * 0.55;
  let b = min(d * 2.0 - 0.4, 1.0) * 0.25;
  return vec4f(r, max(g, 0.0), max(b, 0.0), alpha);
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

  let fwd    = normalize(cam.target - cam.eye);
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
    pixels[py * cam.width + px] = 0xFF080A10u;
    return;
  }

  let step: f32 = 0.004;
  let t_near  = max(b.x, 0.0);
  let t_far   = b.y;
  let nsteps  = i32((t_far - t_near) / step);
  var accum   = vec4f(0.0);

  let wf = f32(vol.width  - 1u);
  let hf = f32(vol.height - 1u);
  let df = f32(vol.depth  - 1u);

  for (var i = 0; i < nsteps; i = i + 1) {
    if (accum.a >= 0.99) { break; }
    let t   = t_near + f32(i) * step;
    let pos = ro + rd * vec3f(t);
    // inline sample_vol to avoid globals-in-user-function MSL issue
    let p   = clamp(pos, vec3f(0.0), vec3f(1.0));
    let d   = textureLoad(vol_tex, vec3u(u32(p.x * wf), u32(p.y * hf), u32(p.z * df)), 0).r;
    let c   = transfer(d);
    accum = accum + c * vec4f(1.0 - accum.a);
  }

  let bg  = vec3f(0.03, 0.04, 0.06);
  let rgb = accum.rgb + bg * vec3f(1.0 - accum.a);
  let r   = u32(clamp(rgb.r * 255.0, 0.0, 255.0));
  let g   = u32(clamp(rgb.g * 255.0, 0.0, 255.0));
  let b_  = u32(clamp(rgb.b * 255.0, 0.0, 255.0));
  pixels[py * cam.width + px] = r | (g << 8u) | (b_ << 16u) | (0xFFu << 24u);
}
