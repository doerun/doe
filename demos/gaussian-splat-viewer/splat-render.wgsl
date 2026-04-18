// Gaussian splat renderer — EWA projection of a 3D anisotropic Gaussian to a
// 2D conic, rasterized as an instanced billboard with alpha-composited output.
//
// Doe WGSL sema constraints followed below:
//   - scalar broadcast via vec3f(x), not bare x * vec3f
//   - loop increments written i = i + 1 (not i++)
//   - helpers that close over uniforms must be inlined; we do this here
//
// Reference: Kerbl et al. 2023, "3D Gaussian Splatting for Real-Time Radiance
// Field Rendering". The Jacobian and 2D covariance derivation below matches
// their supplementary.

struct Frame {
  view:    mat4x4f,     // world -> camera
  proj:    mat4x4f,     // camera -> clip
  viewport: vec2f,      // (width, height) in pixels
  focal:   vec2f,       // (fx, fy) pixel focal lengths derived from proj + viewport
}

@group(0) @binding(0) var<uniform> frame: Frame;

// Planar splat buffers — separate storage buffers per component keeps each
// read-only and well-typed (uploading as one packed struct would require
// either f32-u32 punning or padding waste).
@group(0) @binding(1) var<storage, read> positions: array<vec3f>;
@group(0) @binding(2) var<storage, read> scales:    array<vec3f>;
@group(0) @binding(3) var<storage, read> rotations: array<vec4f>;  // (w, x, y, z) unit quat
@group(0) @binding(4) var<storage, read> colors:    array<vec4f>;  // rgba in [0, 1], a = opacity
@group(0) @binding(5) var<storage, read> sortOrder: array<u32>;    // back-to-front splat indices

struct VsOut {
  @builtin(position) pos: vec4f,
  @location(0)       offset: vec2f,  // pixel offset from splat center
  @location(1)       conic:  vec3f,  // (Σ2d⁻¹.xx, Σ2d⁻¹.xy, Σ2d⁻¹.yy)
  @location(2)       color:  vec4f,
}

@vertex
fn vs_main(@builtin(instance_index) inst: u32,
           @builtin(vertex_index)   vid:  u32) -> VsOut {
  // sortOrder[inst] gives the splat id for this billboard, ordered back-to-front.
  let splat_id: u32 = sortOrder[inst];

  let p_world: vec3f = positions[splat_id];
  let s:       vec3f = scales[splat_id];
  let q:       vec4f = rotations[splat_id];  // (w, x, y, z)
  let col:     vec4f = colors[splat_id];

  // World-space covariance: Σ = R · diag(s)² · Rᵀ.
  // Build R from quaternion (right-handed).
  let qw = q.x;
  let qx = q.y;
  let qy = q.z;
  let qz = q.w;
  let r00 = 1.0 - 2.0 * (qy * qy + qz * qz);
  let r01 = 2.0 * (qx * qy - qw * qz);
  let r02 = 2.0 * (qx * qz + qw * qy);
  let r10 = 2.0 * (qx * qy + qw * qz);
  let r11 = 1.0 - 2.0 * (qx * qx + qz * qz);
  let r12 = 2.0 * (qy * qz - qw * qx);
  let r20 = 2.0 * (qx * qz - qw * qy);
  let r21 = 2.0 * (qy * qz + qw * qx);
  let r22 = 1.0 - 2.0 * (qx * qx + qy * qy);

  // M = R · diag(s). Σ_world = M · Mᵀ.
  let m00 = r00 * s.x;
  let m01 = r01 * s.y;
  let m02 = r02 * s.z;
  let m10 = r10 * s.x;
  let m11 = r11 * s.y;
  let m12 = r12 * s.z;
  let m20 = r20 * s.x;
  let m21 = r21 * s.y;
  let m22 = r22 * s.z;

  let c00 = m00 * m00 + m01 * m01 + m02 * m02;
  let c01 = m00 * m10 + m01 * m11 + m02 * m12;
  let c02 = m00 * m20 + m01 * m21 + m02 * m22;
  let c11 = m10 * m10 + m11 * m11 + m12 * m12;
  let c12 = m10 * m20 + m11 * m21 + m12 * m22;
  let c22 = m20 * m20 + m21 * m21 + m22 * m22;

  // View-space center.
  let p_view4: vec4f = frame.view * vec4f(p_world, 1.0);
  let p_view:  vec3f = p_view4.xyz;

  // Near-plane cull via degenerate vertex when behind (or very close to) the
  // camera. Emitting a zero-w position makes WebGPU clip the triangle.
  if (p_view.z >= -0.01) {
    var dead: VsOut;
    dead.pos = vec4f(2.0, 2.0, 2.0, 0.0);
    dead.offset = vec2f(0.0, 0.0);
    dead.conic = vec3f(0.0, 0.0, 0.0);
    dead.color = vec4f(0.0, 0.0, 0.0, 0.0);
    return dead;
  }

  // Jacobian of perspective projection at p_view (screen-pixel units).
  // J = [[fx/-z, 0,       fx*x/z²],
  //      [0,     fy/-z,   fy*y/z²],
  //      [0,     0,       0      ]]
  // (The "-" on z flips for our right-handed negative-z-forward convention.)
  let fx = frame.focal.x;
  let fy = frame.focal.y;
  let z_inv = 1.0 / -p_view.z;
  let z_inv2 = z_inv * z_inv;

  let j00 = fx * z_inv;
  let j02 = fx * p_view.x * z_inv2;
  let j11 = fy * z_inv;
  let j12 = fy * p_view.y * z_inv2;

  // T = J · W where W is the 3x3 upper-left of the view matrix.
  let w00 = frame.view[0][0]; let w01 = frame.view[1][0]; let w02 = frame.view[2][0];
  let w10 = frame.view[0][1]; let w11 = frame.view[1][1]; let w12 = frame.view[2][1];
  let w20 = frame.view[0][2]; let w21 = frame.view[1][2]; let w22 = frame.view[2][2];

  let t00 = j00 * w00 + j02 * w20;
  let t01 = j00 * w01 + j02 * w21;
  let t02 = j00 * w02 + j02 * w22;
  let t10 = j11 * w10 + j12 * w20;
  let t11 = j11 * w11 + j12 * w21;
  let t12 = j11 * w12 + j12 * w22;

  // Σ_2d = T · Σ_world · Tᵀ (keep 2x2 top-left of the result).
  // Intermediate: Σ_world · Tᵀ = U (3x2).
  let u00 = c00 * t00 + c01 * t01 + c02 * t02;
  let u01 = c00 * t10 + c01 * t11 + c02 * t12;
  let u10 = c01 * t00 + c11 * t01 + c12 * t02;
  let u11 = c01 * t10 + c11 * t11 + c12 * t12;
  let u20 = c02 * t00 + c12 * t01 + c22 * t02;
  let u21 = c02 * t10 + c12 * t11 + c22 * t12;

  // Σ_2d = T · U.
  var s2d00 = t00 * u00 + t01 * u10 + t02 * u20;
  let s2d01 = t00 * u01 + t01 * u11 + t02 * u21;
  var s2d11 = t10 * u01 + t11 * u11 + t12 * u21;

  // Regularize: add a 0.3-pixel isotropic blur so under-sampled splats still
  // draw at least a pixel-sized footprint (Kerbl et al. supplementary §C).
  s2d00 = s2d00 + 0.3;
  s2d11 = s2d11 + 0.3;

  // Invert 2x2 covariance → conic form.
  let det = s2d00 * s2d11 - s2d01 * s2d01;
  if (det <= 0.0) {
    var dead: VsOut;
    dead.pos = vec4f(2.0, 2.0, 2.0, 0.0);
    dead.offset = vec2f(0.0, 0.0);
    dead.conic = vec3f(0.0, 0.0, 0.0);
    dead.color = vec4f(0.0, 0.0, 0.0, 0.0);
    return dead;
  }
  let det_inv = 1.0 / det;
  let conic = vec3f(s2d11 * det_inv, -s2d01 * det_inv, s2d00 * det_inv);

  // Eigenvalues of Σ_2d give major/minor axis lengths; 3σ bounds the visible
  // footprint of the Gaussian to >99% of its energy.
  let mid = 0.5 * (s2d00 + s2d11);
  let disc = sqrt(max(mid * mid - det, 0.1));
  let lambda1 = mid + disc;
  let lambda2 = max(mid - disc, 0.1);
  let radius_pixels = ceil(3.0 * sqrt(max(lambda1, lambda2)));

  // Billboard corner offset in pixels from the splat center.
  // vertex_index goes 0..3 via triangle-strip: (-1,-1) (1,-1) (-1,1) (1,1)
  let corner = vec2f(
    f32((vid & 1u)) * 2.0 - 1.0,
    f32((vid >> 1u) & 1u) * 2.0 - 1.0,
  );
  let offset_pixels = corner * radius_pixels;

  // Project splat center to clip space, then shift corner in NDC.
  let center_clip: vec4f = frame.proj * p_view4;
  let ndc_shift = 2.0 * offset_pixels / frame.viewport;
  let pos_clip = vec4f(
    center_clip.x + ndc_shift.x * center_clip.w,
    center_clip.y - ndc_shift.y * center_clip.w,  // y flip for screen coords
    center_clip.z,
    center_clip.w,
  );

  var out: VsOut;
  out.pos = pos_clip;
  out.offset = offset_pixels;
  out.conic = conic;
  out.color = col;
  return out;
}

@fragment
fn fs_main(in: VsOut) -> @location(0) vec4f {
  // Evaluate the 2D Gaussian at this fragment's pixel offset from center.
  //   power = -0.5 * [dx dy] · Σ⁻¹ · [dx dy]ᵀ
  let dx = in.offset.x;
  let dy = in.offset.y;
  let power = -0.5 * (in.conic.x * dx * dx + in.conic.z * dy * dy) - in.conic.y * dx * dy;
  if (power > 0.0) {
    discard;
  }
  let alpha = min(0.999, in.color.a * exp(power));
  if (alpha < (1.0 / 255.0)) {
    discard;
  }
  // Premultiplied alpha output. Host side pipeline is configured with
  // (src_color, src_alpha) = (src.rgb * src.a, src.a) blending against dst
  // so back-to-front order produces correct alpha composite.
  return vec4f(in.color.rgb * alpha, alpha);
}
