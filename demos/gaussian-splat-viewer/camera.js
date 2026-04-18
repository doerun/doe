// Orbit camera with mouse + wheel controls.
//
// View matrix is a right-handed look-at from `eye` to `target` with world up.
// Projection is a standard infinite-reverse-Z-free perspective in clip space
// convention matching WebGPU's default (-1..1 x/y, 0..1 z).

const MIN_DIST = 0.1;
const MAX_DIST = 1000;

export function createOrbitCamera() {
  const state = {
    target: [0, 0, 0],
    // spherical: azimuth (theta around world Y), elevation (phi from equator), radius
    theta: 0,
    phi: 0.3,
    radius: 4,
    fov: (60 * Math.PI) / 180,
    near: 0.05,
    far: 500,
  };

  function eye() {
    const cosP = Math.cos(state.phi);
    const x = state.target[0] + state.radius * Math.sin(state.theta) * cosP;
    const y = state.target[1] + state.radius * Math.sin(state.phi);
    const z = state.target[2] + state.radius * Math.cos(state.theta) * cosP;
    return [x, y, z];
  }

  function viewMatrix() {
    const e = eye();
    return lookAt(e, state.target, [0, 1, 0]);
  }

  function projectionMatrix(aspect) {
    return perspective(state.fov, aspect, state.near, state.far);
  }

  function attach(canvas) {
    let dragging = false;
    let pan = false;
    let lx = 0;
    let ly = 0;

    canvas.addEventListener("pointerdown", (e) => {
      dragging = true;
      pan = e.shiftKey;
      lx = e.clientX;
      ly = e.clientY;
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointerup", (e) => {
      dragging = false;
      canvas.releasePointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const dx = e.clientX - lx;
      const dy = e.clientY - ly;
      lx = e.clientX;
      ly = e.clientY;
      if (pan) {
        // pan in the camera's screen-space basis
        const s = 0.002 * state.radius;
        const right = cross(sub(eye(), state.target), [0, 1, 0]);
        normalize(right);
        const up = cross(right, sub(eye(), state.target));
        normalize(up);
        state.target[0] = state.target[0] - right[0] * dx * s + up[0] * dy * s;
        state.target[1] = state.target[1] - right[1] * dx * s + up[1] * dy * s;
        state.target[2] = state.target[2] - right[2] * dx * s + up[2] * dy * s;
      } else {
        state.theta = state.theta - dx * 0.005;
        state.phi = clamp(state.phi + dy * 0.005, -1.55, 1.55);
      }
    });
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const scale = Math.exp(e.deltaY * 0.001);
      state.radius = clamp(state.radius * scale, MIN_DIST, MAX_DIST);
    }, { passive: false });
  }

  function recenter(centroid, radius) {
    state.target = [centroid[0], centroid[1], centroid[2]];
    state.radius = Math.max(radius * 2.5, MIN_DIST);
  }

  return {
    state,
    eye,
    viewMatrix,
    projectionMatrix,
    attach,
    recenter,
  };
}

// --- minimal column-major 4x4 math ---

function clamp(x, lo, hi) {
  return x < lo ? lo : x > hi ? hi : x;
}

function sub(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function normalize(v) {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  v[0] = v[0] / l;
  v[1] = v[1] / l;
  v[2] = v[2] / l;
}

function lookAt(eye, target, up) {
  const f = sub(target, eye);
  normalize(f);
  const s = cross(f, up);
  normalize(s);
  const u = cross(s, f);
  const m = new Float32Array(16);
  m[0] = s[0]; m[1] = u[0]; m[2] = -f[0]; m[3] = 0;
  m[4] = s[1]; m[5] = u[1]; m[6] = -f[1]; m[7] = 0;
  m[8] = s[2]; m[9] = u[2]; m[10] = -f[2]; m[11] = 0;
  m[12] = -(s[0] * eye[0] + s[1] * eye[1] + s[2] * eye[2]);
  m[13] = -(u[0] * eye[0] + u[1] * eye[1] + u[2] * eye[2]);
  m[14] = f[0] * eye[0] + f[1] * eye[1] + f[2] * eye[2];
  m[15] = 1;
  return m;
}

function perspective(fovY, aspect, near, far) {
  const f = 1 / Math.tan(fovY * 0.5);
  const m = new Float32Array(16);
  m[0] = f / aspect;
  m[5] = f;
  m[10] = far / (near - far);
  m[11] = -1;
  m[14] = (near * far) / (near - far);
  return m;
}

export function multiply4x4(a, b) {
  const out = new Float32Array(16);
  for (let c = 0; c < 4; c = c + 1) {
    for (let r = 0; r < 4; r = r + 1) {
      let s = 0;
      for (let k = 0; k < 4; k = k + 1) {
        s = s + a[k * 4 + r] * b[c * 4 + k];
      }
      out[c * 4 + r] = s;
    }
  }
  return out;
}
